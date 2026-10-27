// Componentes compartidos
import { api, query } from './api.js';
import { store } from './store.js';
import { descargarBlob, miles, peso, debounce, conUnidad } from './util.js';

const { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } = Vue;

// ───────────────────────── Íconos (trazo, estilo Lucide) ─────────────────────────
const ICONOS = {
  caja: '<rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/><path d="M6 12h.01M18 12h.01"/>',
  carrito: '<circle cx="9" cy="20" r="1.5"/><circle cx="18" cy="20" r="1.5"/><path d="M2 3h3l2.7 12.4a2 2 0 0 0 2 1.6h8.2a2 2 0 0 0 2-1.5L21.5 8H6"/>',
  caja_prod: '<path d="M21 8 12 3 3 8v8l9 5 9-5V8z"/><path d="m3 8 9 5 9-5M12 13v8"/>',
  camion: '<path d="M1 6h13v10H1z"/><path d="M14 9h4l4 4v3h-8z"/><circle cx="6" cy="18" r="2"/><circle cx="18" cy="18" r="2"/>',
  conteo: '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V3h6v1M9 13l2 2 4-4"/>',
  grafico: '<path d="M4 20V10M10 20V4M16 20v-8M22 20H2"/>',
  tablero: '<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
  informe: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>',
  ajustes: '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
  candado: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
  salir: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
  buscar: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  mas: '<path d="M12 5v14M5 12h14"/>', menos: '<path d="M5 12h14"/>', x: '<path d="M6 6l12 12M18 6 6 18"/>',
  check: '<path d="m5 12 5 5 9-10"/>',
  alerta: '<path d="M12 3 2 20h20z"/><path d="M12 10v5M12 18h.01"/>',
  basura: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
  pausa: '<path d="M8 5v14M16 5v14"/>', play: '<path d="M7 4v16l13-8z"/>',
  billetes: '<rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/><path d="M6 12h.01M18 12h.01"/>',
  tarjeta: '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20M6 15h4"/>',
  celular: '<rect x="7" y="2" width="10" height="20" rx="2"/><path d="M11 18h2"/>',
  impresora: '<path d="M7 9V3h10v6M7 17H5a2 2 0 0 1-2-2v-4a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2h-2"/><rect x="7" y="14" width="10" height="7"/>',
  bajar: '<path d="M12 4v11M7 11l5 5 5-5M5 20h14"/>', subir: '<path d="M12 16V5M7 9l5-5 5 5M5 20h14"/>',
  lapiz: '<path d="M4 20l1-4L16 5l3 3L8 19z"/>',
  ojo: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  refrescar: '<path d="M20 11a8 8 0 0 0-14-4M4 5v4h4M4 13a8 8 0 0 0 14 4M20 19v-4h-4"/>',
  luna: '<path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z"/>',
  sol: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M19 5l-1.5 1.5M6.5 17.5 5 19"/>',
  usuario: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  usuarios: '<circle cx="9" cy="8" r="3.5"/><path d="M2 20a7 7 0 0 1 14 0M16 4.5a3.5 3.5 0 0 1 0 7M22 20a6 6 0 0 0-4-5.6"/>',
  der: '<path d="m9 6 6 6-6 6"/>', izq: '<path d="m15 6-6 6 6 6"/>', abajo: '<path d="m6 9 6 6 6-6"/>',
  calendario: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
  etiqueta: '<path d="M3 12V4h8l10 10-8 8z"/><circle cx="7.5" cy="8.5" r="1"/>',
  porcentaje: '<path d="M19 5 5 19"/><circle cx="7" cy="7" r="2"/><circle cx="17" cy="17" r="2"/>',
  barras: '<path d="M4 5v14M7 5v14M11 5v14M14 5v14M18 5v14M20 5v14"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5h.01"/>',
  base: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
  reloj: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  escudo: '<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z"/>',
  recibo: '<path d="M5 3h14v18l-3-2-2 2-2-2-2 2-2-2-3 2z"/><path d="M9 8h6M9 12h6"/>',
  deshacer: '<path d="M4 9h11a5 5 0 0 1 0 10H8M4 9l4-4M4 9l4 4"/>',
  prohibido: '<circle cx="12" cy="12" r="9"/><path d="m5.6 5.6 12.8 12.8"/>',
  lista: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
  filtro: '<path d="M3 5h18l-7 8v6l-4 2v-8z"/>',
  tendencia: '<path d="M3 17 9 11l4 4 8-8M15 7h6v6"/>',
  tienda: '<path d="M3 9l1.5-5h15L21 9M3 9v11h18V9M3 9c0 1.7 1.3 3 3 3s3-1.3 3-3c0 1.7 1.3 3 3 3s3-1.3 3-3c0 1.7 1.3 3 3 3s3-1.3 3-3M9 20v-5h6v5"/>',
  panel: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/>',
};

export const Icono = {
  props: { n: { type: String, required: true } },
  setup(p) { return { svg: computed(() => ICONOS[p.n] || ICONOS.info) }; },
  template: `<svg class="ico" viewBox="0 0 24 24" aria-hidden="true" v-html="svg"></svg>`,
};

// ───────────────────────── Modal ─────────────────────────
const pila = [];
let idModal = 0;
export const Modal = {
  props: { titulo: String, ancho: { type: String, default: '' }, cerrable: { type: Boolean, default: true } },
  emits: ['cerrar'],
  setup(p, { emit }) {
    const id = ++idModal;
    const alTecla = e => { if (e.key === 'Escape' && p.cerrable && pila[pila.length - 1] === id) { e.stopPropagation(); emit('cerrar'); } };
    onMounted(() => { pila.push(id); window.addEventListener('keydown', alTecla, true); });
    onBeforeUnmount(() => { pila.splice(pila.indexOf(id), 1); window.removeEventListener('keydown', alTecla, true); });
    const fondo = e => { if (e.target === e.currentTarget && p.cerrable) emit('cerrar'); };
    return { fondo };
  },
  template: `
    <div class="overlay" @mousedown="fondo">
      <div class="modal" :class="ancho" role="dialog" aria-modal="true">
        <div class="modal-head" v-if="titulo || $slots.cabecera">
          <h2><slot name="cabecera">{{ titulo }}</slot></h2>
          <button class="btn ghost icon sm" v-if="cerrable" @click="$emit('cerrar')" title="Cerrar (Esc)"><Icono n="x"/></button>
        </div>
        <div class="modal-body"><slot/></div>
        <div class="modal-foot" v-if="$slots.pie"><slot name="pie"/></div>
      </div>
    </div>`,
};

// ───────────────────────── Campo de dinero (con puntos de miles) ─────────────────────────
export const InputDinero = {
  props: { modelValue: { type: Number, default: null }, grande: Boolean, placeholder: String, disabled: Boolean, maximo: Number },
  emits: ['update:modelValue', 'enter'],
  setup(p, { emit, expose }) {
    const el = ref(null);
    const texto = computed(() => (p.modelValue === null || p.modelValue === undefined ? '' : miles(p.modelValue)));
    function alEscribir(e) {
      const digitos = e.target.value.replace(/\D/g, '').slice(0, 12);
      let v = digitos === '' ? null : parseInt(digitos, 10);
      if (v !== null && p.maximo !== undefined && v > p.maximo) v = p.maximo;
      emit('update:modelValue', v);
      e.target.value = v === null ? '' : miles(v);
    }
    expose({ focus: () => { el.value?.focus(); el.value?.select(); } });
    return { el, texto, alEscribir };
  },
  template: `<input ref="el" class="input num" :class="{ 'money-lg': grande }" inputmode="numeric" autocomplete="off"
      :value="texto" :placeholder="placeholder" :disabled="disabled" @input="alEscribir" @keydown.enter="$emit('enter')" @focus="$event.target.select()">`,
};

// ───────────────────────── Campo de cantidad con decimales (kilos) ─────────────────────────
// Acepta «1,25» o «1.25»; máximo 3 decimales (gramos). Emite un número o null.
export const InputPeso = {
  props: { modelValue: { type: Number, default: null }, grande: Boolean, placeholder: String, maximo: { type: Number, default: 1000 }, decimales: { type: Number, default: 3 } },
  emits: ['update:modelValue', 'enter'],
  setup(p, { emit, expose }) {
    const el = ref(null);
    const aTexto = v => (v === null || v === undefined ? '' : String(v).replace('.', ','));
    const analizar = t => { const n = parseFloat(String(t).replace(',', '.')); return Number.isFinite(n) ? n : null; };
    const texto = ref(aTexto(p.modelValue));
    watch(() => p.modelValue, v => { if (analizar(texto.value) !== v) texto.value = aTexto(v); });
    function alEscribir(e) {
      let t = e.target.value.replace(/[^\d.,]/g, '');
      const i = t.search(/[.,]/);
      if (i >= 0) t = t.slice(0, i).slice(0, 5) + ',' + t.slice(i + 1).replace(/[.,]/g, '').slice(0, p.decimales);
      else t = t.slice(0, 5);
      let v = analizar(t);
      if (v !== null && v > p.maximo) { v = p.maximo; t = aTexto(v); }
      texto.value = t; e.target.value = t;
      emit('update:modelValue', v);
    }
    expose({ focus: () => { el.value?.focus(); el.value?.select(); } });
    return { el, texto, alEscribir };
  },
  template: `<input ref="el" class="input num" :class="{ 'money-lg': grande }" inputmode="decimal" autocomplete="off"
      :value="texto" :placeholder="placeholder" @input="alEscribir" @keydown.enter="$emit('enter')" @focus="$event.target.select()">`,
};

// ───────────────────────── Buscador de producto con sugerencias ─────────────────────────
export const BuscaProducto = {
  props: { placeholder: { type: String, default: 'Buscar producto por nombre o código…' }, limpiar: { type: Boolean, default: true } },
  emits: ['elegir'],
  setup(p, { emit, expose }) {
    const q = ref(''), items = ref([]), abierto = ref(false), activo = ref(0), el = ref(null);
    const buscar = debounce(async () => {
      if (!q.value.trim()) { items.value = []; return; }
      try { items.value = (await api.get('/api/productos' + query({ q: q.value, limite: 8 }))).productos; activo.value = 0; abierto.value = true; }
      catch (e) { items.value = []; }
    }, 180);
    watch(q, buscar);
    function elegir(prod) { emit('elegir', prod); abierto.value = false; if (p.limpiar) q.value = ''; else q.value = prod.nombre; items.value = []; }
    async function enter() {
      const t = q.value.trim();
      if (/^\d{6,}$/.test(t)) {   // parece un código de barras: búsqueda exacta primero
        try { const r = await api.get('/api/productos/codigo/' + encodeURIComponent(t)); return elegir(r); } catch (e) { /* sigue a la lista */ }
      }
      if (items.value[activo.value]) elegir(items.value[activo.value]);
    }
    function tecla(e) {
      if (e.key === 'ArrowDown') { e.preventDefault(); activo.value = Math.min(activo.value + 1, items.value.length - 1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); activo.value = Math.max(activo.value - 1, 0); }
      else if (e.key === 'Escape' && abierto.value) { e.stopPropagation(); abierto.value = false; }
    }
    const cerrarLuego = () => setTimeout(() => { abierto.value = false; }, 150);
    expose({ focus: () => el.value?.focus(), limpiar: () => { q.value = ''; items.value = []; } });
    return { q, items, abierto, activo, el, elegir, enter, tecla, peso, cerrarLuego, conUnidad };
  },
  template: `
    <div style="position:relative">
      <input ref="el" class="input" v-model="q" :placeholder="placeholder" autocomplete="off" @keydown.enter.prevent="enter" @keydown="tecla"
             @focus="abierto = items.length > 0" @blur="cerrarLuego">
      <div class="suggest" v-if="abierto && items.length">
        <button v-for="(it, i) in items" :key="it.id" :class="{ on: i === activo }" @mousedown.prevent="elegir(it)">
          <span><b>{{ it.nombre }}</b><br><span class="xs muted">{{ it.codigos[0] ? it.codigos[0].codigo : (it.codigo_interno || 'sin código') }}</span></span>
          <span class="right nowrap"><b class="num">{{ peso(it.precio_venta) }}<span v-if="it.unidad === 'kg'" class="xs muted">/kg</span></b><br><span class="xs muted">stock {{ conUnidad(it.stock_actual, it.unidad) }}</span></span>
        </button>
      </div>
    </div>`,
};

// ───────────────────────── Gráfico (ECharts) ─────────────────────────
export const Grafico = {
  props: { opcion: { type: Object, required: true }, alto: { type: String, default: '' } },
  emits: ['clic'],
  setup(p, { emit }) {
    const el = ref(null); let chart = null, ro = null;
    const pintar = () => { if (chart) chart.setOption(p.opcion, true); };
    onMounted(() => {
      chart = echarts.init(el.value, null, { renderer: 'canvas' });
      chart.on('click', e => emit('clic', e));
      pintar();
      ro = new ResizeObserver(() => chart && chart.resize()); ro.observe(el.value);
    });
    watch(() => p.opcion, pintar, { deep: true });
    onBeforeUnmount(() => { ro && ro.disconnect(); chart && chart.dispose(); });
    return { el };
  },
  template: `<div ref="el" class="chart" :class="alto"></div>`,
};

// ───────────────────────── Diálogo de PIN de administrador ─────────────────────────
export const DialogoPin = {
  setup() {
    const pin = ref(''), el = ref(null);
    watch(() => store.pin.abierto, a => { if (a) { pin.value = ''; nextTick(() => el.value?.focus()); } });
    function cerrar(valor) { const r = store.pin.resolver; store.pin = { abierto: false, detalle: '', incorrecto: false, resolver: null }; r && r(valor); }
    function aceptar() { if (pin.value.length >= 4) cerrar(pin.value); }
    return { store, pin, el, cerrar, aceptar };
  },
  template: `
    <Modal v-if="store.pin.abierto" titulo="Autorización del administrador" ancho="sm" @cerrar="cerrar(null)">
      <div class="stack">
        <p class="muted">{{ store.pin.detalle }}</p>
        <div class="field">
          <label>PIN del administrador</label>
          <input ref="el" class="input lg center" type="password" inputmode="numeric" maxlength="6" v-model="pin" autocomplete="off"
                 placeholder="••••" @keydown.enter="aceptar" style="letter-spacing:.4em">
          <span class="err-text" v-if="store.pin.incorrecto">El PIN no es correcto. Intente de nuevo.</span>
        </div>
      </div>
      <template #pie>
        <button class="btn" @click="cerrar(null)">Cancelar</button>
        <button class="btn primary" :disabled="pin.length < 4" @click="aceptar">Autorizar</button>
      </template>
    </Modal>`,
};

// ───────────────────────── Confirmación ─────────────────────────
export const DialogoConfirmar = {
  setup() {
    function cerrar(v) { const r = store.confirmacion.resolver; store.confirmacion = null; r(v); }
    return { store, cerrar };
  },
  template: `
    <Modal v-if="store.confirmacion" :titulo="store.confirmacion.titulo" ancho="sm" @cerrar="cerrar(false)">
      <p style="white-space:pre-line">{{ store.confirmacion.mensaje }}</p>
      <template #pie>
        <button class="btn" @click="cerrar(false)">{{ store.confirmacion.textoNo }}</button>
        <button class="btn" :class="store.confirmacion.peligro ? 'danger' : 'primary'" @click="cerrar(true)">{{ store.confirmacion.textoOk }}</button>
      </template>
    </Modal>`,
};

// ───────────────────────── Pregunta de texto (reemplaza window.prompt) ─────────────────────────
export const DialogoTexto = {
  setup() {
    const v = ref(''), el = ref(null);
    watch(() => store.pregunta, q => { if (q) { v.value = q.valor || ''; nextTick(() => el.value?.focus()); } });
    function cerrar(ok) {
      const q = store.pregunta; store.pregunta = null;
      q.resolver(ok ? v.value.trim() : null);
    }
    const valido = computed(() => !store.pregunta?.obligatorio || v.value.trim().length > 0);
    return { store, v, el, cerrar, valido };
  },
  template: `
    <Modal v-if="store.pregunta" :titulo="store.pregunta.titulo" ancho="sm" @cerrar="cerrar(false)">
      <div class="field"><label>{{ store.pregunta.etiqueta }}</label>
        <textarea v-if="store.pregunta.multilinea" ref="el" class="input" v-model="v"></textarea>
        <input v-else ref="el" class="input lg" :type="store.pregunta.secreto ? 'password' : 'text'" v-model="v" @keydown.enter="valido && cerrar(true)" autocomplete="off">
        <span class="hint" v-if="store.pregunta.ayuda">{{ store.pregunta.ayuda }}</span></div>
      <template #pie><button class="btn" @click="cerrar(false)">Cancelar</button>
        <button class="btn primary" :disabled="!valido" @click="cerrar(true)">{{ store.pregunta.textoOk }}</button></template>
    </Modal>`,
};

// ───────────────────────── Visor de PDF ─────────────────────────
export const VisorPdf = {
  setup() {
    const marco = ref(null);
    function cerrar() { if (store.visor?.url) URL.revokeObjectURL(store.visor.url); store.visor = null; }
    function imprimir() { try { marco.value.contentWindow.focus(); marco.value.contentWindow.print(); } catch (e) { window.print(); } }
    function bajar() { descargarBlob(store.visor.blob, (store.visor.titulo || 'documento').replace(/[^\w-]+/g, '_') + '.pdf'); }
    return { store, marco, cerrar, imprimir, bajar };
  },
  template: `
    <Modal v-if="store.visor" :titulo="store.visor.titulo" ancho="lg" @cerrar="cerrar">
      <div v-if="store.visor.cargando" class="empty">Preparando documento…</div>
      <iframe v-else ref="marco" :src="store.visor.url" style="width:100%;height:68vh;border:1px solid var(--border);border-radius:10px;background:#fff"></iframe>
      <template #pie>
        <button class="btn" @click="bajar" :disabled="store.visor.cargando"><Icono n="bajar"/> Descargar</button>
        <button class="btn primary" @click="imprimir" :disabled="store.visor.cargando"><Icono n="impresora"/> Imprimir</button>
      </template>
    </Modal>`,
};

export const Avisos = {
  setup() { return { store }; },
  template: `
    <div class="toasts">
      <div v-for="t in store.toasts" :key="t.id" class="toast" :class="t.tipo">
        <Icono :n="t.tipo === 'error' ? 'alerta' : t.tipo === 'ok' ? 'check' : 'info'"/>
        <span style="white-space:pre-line">{{ t.mensaje }}</span>
      </div>
    </div>`,
};

// Cabecera de columna ordenable: se usa con la función `ordenar` de la vista
export function ordenarPor(filas, clave, asc) {
  const dir = asc ? 1 : -1;
  return [...filas].sort((a, b) => {
    const x = a[clave], y = b[clave];
    if (x === y) return 0;
    if (x === null || x === undefined) return 1;
    if (y === null || y === undefined) return -1;
    return (typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y), 'es', { numeric: true })) * dir;
  });
}

export function registrar(app) {
  app.component('Icono', Icono).component('Modal', Modal).component('InputDinero', InputDinero).component('InputPeso', InputPeso)
    .component('BuscaProducto', BuscaProducto).component('Grafico', Grafico)
    .component('DialogoPin', DialogoPin).component('DialogoConfirmar', DialogoConfirmar)
    .component('VisorPdf', VisorPdf).component('DialogoTexto', DialogoTexto).component('Avisos', Avisos);
}
