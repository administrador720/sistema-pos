// Piezas compartidas: íconos, pantalla con barra superior, hoja inferior, avisos y buscador de productos
import { estado, get, consulta } from './api.js';
import { escanear, hayCamara } from './escaner.js';
import { aNumero, debounce, peso, pitido, conUnidad } from './util.js';

const { ref, reactive, watch, onMounted } = Vue;

// ───────────────────────── Avisos ─────────────────────────
export const ui = reactive({ avisos: [] });
let n = 0;
export function aviso(mensaje, tipo = 'info', ms = 3800) {
  const id = ++n; ui.avisos.push({ id, mensaje, tipo });
  setTimeout(() => { ui.avisos = ui.avisos.filter(a => a.id !== id); }, ms);
}
export const avisoError = e => { pitido('error'); aviso(e && e.message ? e.message : 'Ocurrió un error.', 'error', 6000); };

// ───────────────────────── Íconos (trazo) ─────────────────────────
const ICONOS = {
  buscar: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  camara: '<path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="3.5"/>',
  conteo: '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V3h6v1M9 13l2 2 4-4"/>',
  factura: '<path d="M5 3h14v18l-3-2-2 2-2-2-2 2-2-2-3 2z"/><path d="M9 8h6M9 12h6"/>',
  carrito: '<circle cx="9" cy="20" r="1.5"/><circle cx="18" cy="20" r="1.5"/><path d="M2 3h3l2.7 12.4a2 2 0 0 0 2 1.6h8.2a2 2 0 0 0 2-1.5L21.5 8H6"/>',
  panel: '<path d="M4 20V10M10 20V4M16 20v-8M22 20H2"/>',
  atras: '<path d="m15 6-6 6 6 6"/>', salir: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
  mas: '<path d="M12 5v14M5 12h14"/>', x: '<path d="M6 6l12 12M18 6 6 18"/>', check: '<path d="m5 12 5 5 9-10"/>',
  basura: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>', deshacer: '<path d="M4 9h11a5 5 0 0 1 0 10H8M4 9l4-4M4 9l4 4"/>',
  tienda: '<path d="M3 9l1.5-5h15L21 9M3 9v11h18V9M3 9c0 1.7 1.3 3 3 3s3-1.3 3-3c0 1.7 1.3 3 3 3s3-1.3 3-3c0 1.7 1.3 3 3 3s3-1.3 3-3M9 20v-5h6v5"/>',
  barras: '<path d="M4 5v14M7 5v14M11 5v14M14 5v14M18 5v14M20 5v14"/>', candado: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
  alerta: '<path d="M12 3 2 20h20z"/><path d="M12 10v5M12 18h.01"/>',
};
export const Icono = {
  props: { n: String },
  template: `<svg class="ico" viewBox="0 0 24 24" aria-hidden="true" v-html="ICONOS[n] || ''"></svg>`,
  setup() { return { ICONOS }; },
};

// ───────────────────────── Pantalla con barra superior ─────────────────────────
export const Pantalla = {
  props: { titulo: String, atras: { type: String, default: '#/' } },
  template: `
    <div class="pantalla">
      <header class="barra">
        <a v-if="atras" :href="atras" class="btn icono" aria-label="Volver"><Icono n="atras"/></a>
        <h1>{{ titulo }}</h1>
        <slot name="acciones"/>
      </header>
      <main class="contenido"><slot/></main>
      <footer class="pie" v-if="$slots.pie"><slot name="pie"/></footer>
    </div>`,
};

export const Hoja = {
  emits: ['cerrar'],
  template: `<div class="velo" @click.self="$emit('cerrar')"><div class="hoja" role="dialog"><slot/></div></div>`,
};

// ───────────────────────── Buscador de productos: escribir, lector Bluetooth o cámara ─────────────────────────
export const BuscarProducto = {
  props: { placeholder: { type: String, default: 'Código o nombre del producto' }, continuo: Boolean, autoenfocar: { type: Boolean, default: true } },
  emits: ['elegir'],
  setup(p, { emit, expose }) {
    const q = ref(''), lista = ref([]), el = ref(null), camara = hayCamara();

    async function porCodigo(codigo, { silencioso = false } = {}) {
      try {
        const prod = await get('/api/productos/codigo/' + encodeURIComponent(codigo));
        lista.value = []; q.value = '';
        emit('elegir', { ...prod, _codigo: codigo });
        return true;
      } catch (e) {
        if (e.codigo === 'CODIGO_NO_EXISTE') { if (!silencioso) { pitido('error'); aviso(`El código ${codigo} no existe en el sistema.`, 'warn'); } return false; }
        avisoError(e); return false;
      }
    }
    async function porTexto(t) {
      try { lista.value = (await get('/api/productos' + consulta({ q: t, limite: 12 }), { silencioso: true })).productos; } catch (e) { lista.value = []; }
    }
    async function enter() {
      const t = q.value.trim(); if (!t) return;
      if (/^[\w-]+$/.test(t) && /\d/.test(t)) { if (await porCodigo(t, { silencioso: true })) return; }   // parece un código
      await porTexto(t);
      if (!lista.value.length) { pitido('error'); aviso('No se encontró ningún producto.', 'warn'); }
    }
    watch(q, debounce(t => { t = t.trim(); if (t.length >= 2 && !/^\d{7,}$/.test(t)) porTexto(t); else if (!t) lista.value = []; }, 280));
    function elegir(prod) { lista.value = []; q.value = ''; emit('elegir', { ...prod }); }

    async function abrirCamara() {
      try {
        const c = await escanear();
        if (!c) return;
        const ok = await porCodigo(c);
        if (ok && p.continuo) setTimeout(abrirCamara, 450);   // escaneo seguido: el lector se vuelve a abrir solo
      } catch (e) { avisoError(e); }
    }
    onMounted(() => { if (p.autoenfocar && !camara) el.value?.focus(); });
    expose({ enfocar: () => el.value?.focus(), abrirCamara });
    return { q, lista, el, camara, enter, elegir, abrirCamara, peso, conUnidad, estado };
  },
  template: `
    <div class="pila">
      <div class="fila">
        <input ref="el" class="input" v-model="q" :placeholder="placeholder" enterkeyhint="search" autocomplete="off" autocapitalize="off" spellcheck="false" @keydown.enter.prevent="enter">
        <button v-if="camara" class="btn primario icono" @click="abrirCamara" aria-label="Escanear con la cámara"><Icono n="camara"/></button>
        <button v-else class="btn icono" @click="enter" aria-label="Buscar"><Icono n="buscar"/></button>
      </div>
      <div class="lista" v-if="lista.length">
        <button v-for="x in lista" :key="x.id" class="item" @click="elegir(x)">
          <span class="crece"><b>{{ x.nombre }}</b><br><span class="xs muted">{{ x.codigos && x.codigos[0] ? x.codigos[0].codigo : (x.codigo_interno || 'sin código') }} · stock {{ conUnidad(x.stock_actual, x.unidad) }}</span></span>
          <b class="num nowrap">{{ peso(x.precio_venta) }}{{ x.unidad === 'kg' ? ' /kg' : '' }}</b>
        </button>
      </div>
      <div class="xs muted" v-if="!camara && !lista.length">Escriba el código o el nombre, o use un lector Bluetooth.</div>
    </div>`,
};

// Cantidad con − / + (enteros para unidades; con coma y hasta 3 decimales para kilos)
export const Paso = {
  props: { modelValue: { type: Number, default: null }, decimal: Boolean, paso: { type: Number, default: 1 }, min: { type: Number, default: undefined } },
  emits: ['update:modelValue', 'enter'],
  setup(p, { emit }) {
    const mostrar = v => (v === null || v === undefined ? '' : String(v).replace('.', ','));
    const txt = ref(mostrar(p.modelValue));
    watch(() => p.modelValue, v => { if (aNumero(txt.value) !== v) txt.value = mostrar(v); });
    function sumar(d) {
      const v = Math.round(((p.modelValue || 0) + d) * 1000) / 1000;
      emit('update:modelValue', Math.max(p.min !== undefined ? p.min : (p.decimal ? 0 : 1), v));
    }
    function escribir(e) {
      let t = e.target.value.replace(/[^\d.,]/g, '');
      if (p.decimal) { const i = t.search(/[.,]/); if (i >= 0) t = t.slice(0, i) + ',' + t.slice(i + 1).replace(/[.,]/g, '').slice(0, 3); }
      else t = t.replace(/[.,]/g, '');
      txt.value = t; e.target.value = t;
      emit('update:modelValue', aNumero(t));
    }
    return { txt, sumar, escribir };
  },
  template: `
    <div class="paso">
      <button type="button" @click="sumar(-paso)" aria-label="Menos">−</button>
      <input :value="txt" :inputmode="decimal ? 'decimal' : 'numeric'" @input="escribir" @keydown.enter="$emit('enter')" @focus="$event.target.select()">
      <button type="button" @click="sumar(paso)" aria-label="Más">+</button>
    </div>`,
};

export const Avisos = {
  setup() { return { ui, estado }; },
  template: `
    <div class="cargando" v-if="estado.cargando > 0"></div>
    <div class="avisos"><div v-for="a in ui.avisos" :key="a.id" class="aviso-flotante" :class="a.tipo">{{ a.mensaje }}</div></div>`,
};

export function registrar(app) {
  app.component('Icono', Icono).component('Pantalla', Pantalla).component('Hoja', Hoja)
    .component('BuscarProducto', BuscarProducto).component('Paso', Paso).component('Avisos', Avisos);
}
