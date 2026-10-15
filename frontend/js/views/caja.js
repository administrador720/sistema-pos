// Pantalla de caja: escaneo, carrito, cobro (efectivo / banco / mixto), suspendidas, devoluciones
import { api, query } from '../api.js';
import { store, esAdmin, errorToast, toast, refrescarTurno, confirmar, pedirPin, pedirTexto, verPdf } from '../store.js';
import { peso, miles, beep, hora, fechaHora, debounce } from '../util.js';

const { ref, reactive, computed, onMounted, onBeforeUnmount, nextTick, watch } = Vue;

const BILLETES = [1000, 2000, 5000, 10000, 20000, 50000, 100000];
const ICONO_MEDIO = n => /transfer|qr|nequi|davi/i.test(n) ? 'celular' : 'tarjeta';

// ───────────────────────── Cobro ─────────────────────────
const Cobro = {
  props: { total: Number, modoInicial: String },
  emits: ['confirmar', 'cerrar'],
  setup(p, { emit }) {
    const modo = ref(p.modoInicial || 'efectivo');
    const medios = computed(() => store.cat.medios_pago.filter(m => m.activo));
    const efectivo = computed(() => medios.value.find(m => m.tipo === 'efectivo'));
    const bancos = computed(() => medios.value.filter(m => m.tipo === 'banco'));
    const recibido = ref(null), bancoMedio = ref(null), referencia = ref(''), bancoMonto = ref(null), enviando = ref(false);
    const inEf = ref(null), inRef = ref(null), inBanco = ref(null);
    bancoMedio.value = bancos.value[0]?.id ?? null;

    const montoEfectivo = computed(() => modo.value === 'efectivo' ? p.total : modo.value === 'mixto' ? Math.max(0, p.total - (bancoMonto.value || 0)) : 0);
    const montoBanco = computed(() => modo.value === 'banco' ? p.total : modo.value === 'mixto' ? (bancoMonto.value || 0) : 0);
    const recibidoEf = computed(() => recibido.value === null ? montoEfectivo.value : recibido.value);
    const devuelta = computed(() => Math.max(0, recibidoEf.value - montoEfectivo.value));
    const faltante = computed(() => Math.max(0, montoEfectivo.value - recibidoEf.value));
    const medioBanco = computed(() => bancos.value.find(b => b.id === bancoMedio.value));
    const sugeridos = computed(() => {
      const t = montoEfectivo.value, s = new Set();
      for (const b of BILLETES) if (b > t && s.size < 3) s.add(b);
      for (const paso of [5000, 10000, 50000]) { const r = Math.ceil(t / paso) * paso; if (r > t) s.add(r); }
      return [...s].sort((a, b) => a - b).slice(0, 4);
    });
    const puedeConfirmar = computed(() => {
      if (enviando.value || p.total <= 0) return false;
      if (modo.value === 'efectivo') return recibidoEf.value >= p.total;
      if (modo.value === 'banco') return !!medioBanco.value && (!medioBanco.value.requiere_referencia || referencia.value.trim());
      return montoBanco.value > 0 && montoBanco.value < p.total && !!medioBanco.value && recibidoEf.value >= montoEfectivo.value
        && (!medioBanco.value.requiere_referencia || referencia.value.trim());
    });
    function confirmar() {
      if (!puedeConfirmar.value) return;
      const pagos = [];
      if (montoEfectivo.value > 0) pagos.push({ medio_pago_id: efectivo.value.id, monto: montoEfectivo.value, recibido: recibidoEf.value });
      if (montoBanco.value > 0) pagos.push({ medio_pago_id: bancoMedio.value, monto: montoBanco.value, referencia: referencia.value.trim() || null });
      enviando.value = true; emit('confirmar', pagos);
    }
    function enfocar() { nextTick(() => { if (modo.value === 'banco') (medioBanco.value?.requiere_referencia ? inRef : null)?.value?.focus?.(); else if (modo.value === 'efectivo') inEf.value?.focus(); else inBanco.value?.focus(); }); }
    watch(modo, () => { recibido.value = null; enfocar(); });
    onMounted(enfocar);
    function tecla(e) {
      if (e.key === 'F9') { e.preventDefault(); modo.value = 'efectivo'; }
      else if (e.key === 'F10') { e.preventDefault(); modo.value = 'banco'; }
      else if (e.key === 'F11') { e.preventDefault(); modo.value = 'mixto'; }
      else if (e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); confirmar(); }   // Enter siempre confirma, esté donde esté el foco
    }
    onMounted(() => window.addEventListener('keydown', tecla, true));
    onBeforeUnmount(() => window.removeEventListener('keydown', tecla, true));
    return { modo, medios, efectivo, bancos, recibido, bancoMedio, referencia, bancoMonto, enviando, montoEfectivo, montoBanco, recibidoEf, devuelta, faltante,
      medioBanco, sugeridos, puedeConfirmar, confirmar, inEf, inRef, inBanco, peso, miles, ICONO_MEDIO };
  },
  template: `
    <Modal ancho="" @cerrar="$emit('cerrar')" :cerrable="!enviando">
      <template #cabecera>Cobrar</template>
      <div class="stack">
        <div class="seg" style="align-self:stretch;display:grid;grid-template-columns:repeat(3,1fr)">
          <button :class="{ on: modo === 'efectivo' }" @click="modo = 'efectivo'">Efectivo <span class="kbd">F9</span></button>
          <button :class="{ on: modo === 'banco' }" @click="modo = 'banco'">Banco <span class="kbd">F10</span></button>
          <button :class="{ on: modo === 'mixto' }" @click="modo = 'mixto'">Mixto <span class="kbd">F11</span></button>
        </div>
        <div class="center"><div class="lbl muted small" style="text-transform:uppercase;letter-spacing:.08em">Total a pagar</div>
          <div class="num" style="font-size:46px;font-weight:700;letter-spacing:-.02em">{{ peso(total) }}</div></div>

        <!-- Efectivo -->
        <template v-if="modo === 'efectivo'">
          <div class="field"><label>Efectivo recibido</label>
            <InputDinero ref="inEf" v-model="recibido" grande :placeholder="miles(total)" @enter="confirmar"/></div>
          <div class="quick"><button class="btn sm" @click="recibido = total; inEf.focus()">Exacto</button>
            <button class="btn sm" v-for="s in sugeridos" :key="s" @click="recibido = s; inEf.focus()">{{ peso(s) }}</button></div>
          <div class="change-box" :class="{ bad: faltante > 0 }">
            <div v-if="faltante > 0"><div class="small">Falta</div><div class="big">{{ peso(faltante) }}</div></div>
            <div v-else><div class="small">Devuelta</div><div class="big">{{ peso(devuelta) }}</div></div>
          </div>
        </template>

        <!-- Banco -->
        <template v-else-if="modo === 'banco'">
          <div class="grid" :style="{ gridTemplateColumns: 'repeat(' + Math.min(bancos.length, 3) + ', 1fr)' }">
            <button v-for="b in bancos" :key="b.id" class="btn lg" :class="{ primary: bancoMedio === b.id }" style="flex-direction:column;height:84px;gap:4px" @click="bancoMedio = b.id">
              <Icono :n="ICONO_MEDIO(b.nombre)" class="ico lg"/><span style="font-size:14px">{{ b.nombre }}</span></button>
          </div>
          <div class="field"><label>Número de aprobación / referencia {{ medioBanco && medioBanco.requiere_referencia ? '' : '(opcional)' }}</label>
            <input ref="inRef" class="input lg" v-model="referencia" @keydown.enter="confirmar" autocomplete="off"></div>
          <p class="hint">El valor es exacto: con banco no hay devuelta.</p>
        </template>

        <!-- Mixto -->
        <template v-else>
          <div class="card soft stack sm">
            <h3>Parte con banco</h3>
            <div class="row"><select class="input" v-model="bancoMedio" style="flex:1"><option v-for="b in bancos" :key="b.id" :value="b.id">{{ b.nombre }}</option></select>
              <InputDinero ref="inBanco" v-model="bancoMonto" placeholder="Monto" style="flex:1"/></div>
            <input class="input" v-model="referencia" placeholder="Referencia / aprobación" autocomplete="off">
          </div>
          <div class="card soft stack sm">
            <div class="row between"><h3>Parte en efectivo</h3><b class="num">{{ peso(montoEfectivo) }}</b></div>
            <InputDinero v-model="recibido" :placeholder="'Recibido: ' + miles(montoEfectivo)" @enter="confirmar"/>
            <div class="change-box" :class="{ bad: faltante > 0 }" style="padding:10px"><b class="num" style="font-size:22px">{{ faltante > 0 ? 'Falta ' + peso(faltante) : 'Devuelta ' + peso(devuelta) }}</b></div>
          </div>
        </template>
      </div>
      <template #pie>
        <button class="btn" @click="$emit('cerrar')" :disabled="enviando">Volver</button>
        <button class="btn primary lg" :disabled="!puedeConfirmar" @click="confirmar" style="min-width:220px"><Icono n="check"/> {{ enviando ? 'Registrando…' : 'Confirmar pago' }} <span class="kbd">Enter</span></button>
      </template>
    </Modal>`,
};

// ───────────────────────── Resultado de la venta ─────────────────────────
const Resultado = {
  props: { venta: Object },
  emits: ['cerrar', 'recibo'],
  setup(p, { emit }) {
    const devuelta = computed(() => p.venta.pagos.reduce((s, x) => s + (x.devuelta || 0), 0));
    function tecla(e) { if (e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); emit('cerrar'); } }
    onMounted(() => window.addEventListener('keydown', tecla, true));
    onBeforeUnmount(() => window.removeEventListener('keydown', tecla, true));
    return { devuelta, peso };
  },
  template: `
    <Modal ancho="sm" @cerrar="$emit('cerrar')">
      <div class="stack center">
        <div style="width:56px;height:56px;border-radius:50%;background:var(--ok-soft);color:var(--ok);display:grid;place-items:center;margin:0 auto"><Icono n="check" class="ico xl" style="width:30px;height:30px"/></div>
        <h2>Venta registrada</h2>
        <div class="muted">{{ venta.numero }} · {{ peso(venta.total) }}</div>
        <div v-for="p in venta.pagos" :key="p.medio" class="small muted">{{ p.medio }}: {{ peso(p.monto) }}</div>
        <div class="change-box" v-if="devuelta > 0"><div class="small">Entregue de devuelta</div><div class="big">{{ peso(devuelta) }}</div></div>
        <div class="alert" v-if="venta.cajon && !venta.cajon.ok"><Icono n="alerta"/>No se pudo abrir el cajón: {{ venta.cajon.mensaje }}</div>
      </div>
      <template #pie>
        <button class="btn" @click="$emit('recibo')"><Icono n="recibo"/> Ver recibo</button>
        <button class="btn primary lg" @click="$emit('cerrar')">Nueva venta <span class="kbd">Enter</span></button>
      </template>
    </Modal>`,
};

// ───────────────────────── Búsqueda por nombre (F2) ─────────────────────────
const Buscador = {
  props: { inicial: { type: String, default: '' } },
  emits: ['elegir', 'cerrar'],
  setup(p, { emit }) {
    const q = ref(p.inicial), items = ref([]), activo = ref(0), el = ref(null);
    const buscar = debounce(async () => {
      try { items.value = (await api.get('/api/productos' + query({ q: q.value, limite: 30 }))).productos; activo.value = 0; } catch (e) { errorToast(e); }
    }, 160);
    watch(q, buscar); onMounted(() => { el.value?.focus(); if (q.value) buscar(); });
    function tecla(e) {
      if (e.key === 'ArrowDown') { e.preventDefault(); activo.value = Math.min(activo.value + 1, items.value.length - 1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); activo.value = Math.max(activo.value - 1, 0); }
      else if (e.key === 'Enter' && items.value[activo.value]) { e.preventDefault(); emit('elegir', items.value[activo.value]); }
      nextTick(() => document.querySelector('.res-fila.on')?.scrollIntoView({ block: 'nearest' }));
    }
    return { q, items, activo, el, tecla, peso };
  },
  template: `
    <Modal titulo="Buscar producto" ancho="md" @cerrar="$emit('cerrar')">
      <div class="stack">
        <input ref="el" class="input lg" v-model="q" placeholder="Nombre, marca o código…" @keydown="tecla" autocomplete="off">
        <div class="table-wrap" style="max-height:52vh">
          <table class="t compact"><tbody>
            <tr v-for="(it, i) in items" :key="it.id" class="clickable res-fila" :class="{ on: i === activo, sel: i === activo }" @click="$emit('elegir', it)">
              <td><b>{{ it.nombre }}</b><br><span class="xs muted">{{ it.codigos[0] ? it.codigos[0].codigo : 'sin código' }} · {{ it.categoria || 'Sin categoría' }}</span></td>
              <td class="num"><b>{{ peso(it.precio_venta) }}</b><br><span class="xs" :class="it.stock_actual <= 0 ? 'danger' : 'muted'">stock {{ it.stock_actual }}</span></td>
            </tr>
            <tr v-if="!items.length"><td class="empty">{{ q ? 'Sin resultados.' : 'Escriba para buscar.' }}</td></tr>
          </tbody></table>
        </div>
        <p class="hint">↑ ↓ para moverse · Enter para agregar · Esc para cerrar</p>
      </div>
    </Modal>`,
};

// ───────────────────────── Modales pequeños ─────────────────────────
const ModalCantidad = {
  props: { item: Object },
  emits: ['aceptar', 'cerrar'],
  setup(p, { emit }) {
    const v = ref(p.item.cantidad), el = ref(null);
    onMounted(() => el.value?.focus());
    return { v, el, aceptar: () => v.value >= 1 && emit('aceptar', v.value) };
  },
  template: `<Modal titulo="Cambiar cantidad" ancho="sm" @cerrar="$emit('cerrar')">
      <div class="stack"><b>{{ item.nombre }}</b><InputDinero ref="el" v-model="v" grande @enter="aceptar"/></div>
      <template #pie><button class="btn" @click="$emit('cerrar')">Cancelar</button><button class="btn primary" :disabled="!(v >= 1)" @click="aceptar">Aceptar</button></template></Modal>`,
};

const ModalDescuento = {
  props: { item: Object, bruto: Number },
  emits: ['aplicar', 'cerrar'],
  setup(p, { emit }) {
    const destino = ref(p.item ? 'linea' : 'total'), tipo = ref('pct'), valor = ref(null), el = ref(null);
    const base = computed(() => destino.value === 'linea' ? p.item.precio * p.item.cantidad : p.bruto);
    const monto = computed(() => { const v = valor.value || 0; return Math.min(base.value, tipo.value === 'pct' ? Math.round(base.value * Math.min(v, 100) / 100) : v); });
    const pct = computed(() => base.value ? monto.value * 100 / base.value : 0);
    const limite = parseInt(store.config.descuento_max_pct_cajero || '0', 10);
    onMounted(() => el.value?.focus());
    return { destino, tipo, valor, el, monto, pct, limite, esAdmin, peso, aplicar: () => emit('aplicar', { destino: destino.value, monto: monto.value }) };
  },
  template: `<Modal titulo="Descuento" ancho="sm" @cerrar="$emit('cerrar')">
      <div class="stack">
        <div class="seg" v-if="item"><button :class="{ on: destino === 'linea' }" @click="destino = 'linea'">Al producto</button><button :class="{ on: destino === 'total' }" @click="destino = 'total'">A toda la venta</button></div>
        <p class="small muted" v-if="destino === 'linea' && item">{{ item.nombre }} · {{ peso(item.precio * item.cantidad) }}</p>
        <div class="seg"><button :class="{ on: tipo === 'pct' }" @click="tipo = 'pct'">Porcentaje %</button><button :class="{ on: tipo === 'valor' }" @click="tipo = 'valor'">Valor $</button></div>
        <InputDinero ref="el" v-model="valor" grande :placeholder="tipo === 'pct' ? '10' : '0'" @enter="aplicar"/>
        <div class="row between"><span class="muted">Descuento</span><b class="num">{{ peso(monto) }} ({{ pct.toFixed(1) }} %)</b></div>
        <div class="alert" v-if="!esAdmin() && pct > limite"><Icono n="alerta"/>Más del {{ limite }}% necesita el PIN del administrador al cobrar.</div>
      </div>
      <template #pie><button class="btn" @click="$emit('aplicar', { destino, monto: 0 })">Quitar descuento</button><button class="btn primary" :disabled="!valor" @click="aplicar">Aplicar</button></template></Modal>`,
};

const ModalEtiqueta = {
  emits: ['aceptar', 'cerrar'],
  setup(p, { emit }) { const v = ref(''), el = ref(null); onMounted(() => el.value?.focus()); return { v, el }; },
  template: `<Modal titulo="Suspender venta" ancho="sm" @cerrar="$emit('cerrar')">
      <div class="field"><label>¿Cómo identificar esta venta? (opcional)</label><input ref="el" class="input lg" v-model="v" placeholder="Ej.: señora de rojo" @keydown.enter="$emit('aceptar', v)"></div>
      <template #pie><button class="btn" @click="$emit('cerrar')">Cancelar</button><button class="btn primary" @click="$emit('aceptar', v)">Suspender</button></template></Modal>`,
};

const ModalSuspendidas = {
  emits: ['retomar', 'cerrar'],
  setup(p, { emit }) {
    const lista = ref([]), cargando = ref(true);
    async function cargar() { try { lista.value = await api.get('/api/ventas-suspendidas'); } catch (e) { errorToast(e); } cargando.value = false; }
    async function descartar(s) { if (await confirmar('¿Descartar esta venta?', `${s.etiqueta || 'Venta'} por ${peso(s.total)} se perderá.`, { peligro: true, textoOk: 'Descartar' })) { try { await api.del('/api/ventas-suspendidas/' + s.id); cargar(); } catch (e) { errorToast(e); } } }
    onMounted(cargar);
    return { lista, cargando, descartar, peso, hora };
  },
  template: `<Modal titulo="Ventas suspendidas" ancho="md" @cerrar="$emit('cerrar')">
      <div class="empty" v-if="!cargando && !lista.length">No hay ventas suspendidas.</div>
      <table class="t" v-else><thead><tr><th>Venta</th><th>Hora</th><th class="num">Artículos</th><th class="num">Total</th><th></th></tr></thead><tbody>
        <tr v-for="s in lista" :key="s.id"><td><b>{{ s.etiqueta || 'Venta #' + s.id }}</b></td><td>{{ hora(s.creado_en) }}</td><td class="num">{{ s.items }}</td><td class="num">{{ peso(s.total) }}</td>
          <td class="actions"><button class="btn sm ghost" @click="descartar(s)"><Icono n="basura"/></button><button class="btn sm primary" @click="$emit('retomar', s)">Retomar</button></td></tr>
      </tbody></table></Modal>`,
};

const ModalCrearRapido = {
  props: { codigo: String },
  emits: ['creado', 'cerrar'],
  setup(p, { emit }) {
    const f = reactive({ nombre: '', precio: null, costo: null, impuesto_id: store.cat.impuestos.find(i => i.tarifa_pct === 19)?.id ?? store.cat.impuestos[0]?.id, stock: null });
    const el = ref(null), cargando = ref(false); onMounted(() => el.value?.focus());
    async function crear() {
      cargando.value = true;
      try {
        const prod = await api.post('/api/productos', { nombre: f.nombre, precio_venta: f.precio || 0, costo_promedio: f.costo || 0, impuesto_id: f.impuesto_id,
          stock_inicial: f.stock || 0, codigos: [{ codigo: p.codigo, unidades: 1 }] });
        emit('creado', prod);
      } catch (e) { errorToast(e); } finally { cargando.value = false; }
    }
    return { f, el, cargando, crear, store };
  },
  template: `<Modal titulo="Producto nuevo" ancho="md" @cerrar="$emit('cerrar')">
      <div class="stack"><div class="alert info"><Icono n="barras"/>El código <b>{{ codigo }}</b> no existe. Créelo ahora para venderlo.</div>
        <div class="field"><label>Nombre</label><input ref="el" class="input" v-model="f.nombre"></div>
        <div class="grid c2"><div class="field"><label>Precio de venta (IVA incluido)</label><InputDinero v-model="f.precio"/></div>
          <div class="field"><label>Costo</label><InputDinero v-model="f.costo"/></div>
          <div class="field"><label>Impuesto</label><select class="input" v-model="f.impuesto_id"><option v-for="i in store.cat.impuestos" :key="i.id" :value="i.id">{{ i.nombre }}</option></select></div>
          <div class="field"><label>Existencias</label><InputDinero v-model="f.stock"/></div></div></div>
      <template #pie><button class="btn" @click="$emit('cerrar')">Cancelar</button><button class="btn primary" :disabled="!f.nombre.trim() || !f.precio || cargando" @click="crear">Crear y agregar</button></template></Modal>`,
};

// ───────────────────────── Ventas del turno + devolución ─────────────────────────
const ModalDevolucion = {
  props: { ventaId: Number },
  emits: ['hecho', 'cerrar'],
  setup(p, { emit }) {
    const v = ref(null), cant = reactive({}), danado = reactive({}), medio = ref('efectivo'), motivo = ref(''), cargando = ref(false);
    onMounted(async () => { try { v.value = await api.get('/api/ventas/' + p.ventaId); } catch (e) { errorToast(e); emit('cerrar'); } });
    const restante = it => it.cantidad - it.devuelto;
    const total = computed(() => !v.value ? 0 : v.value.items.reduce((s, it) => s + Math.round(it.total * (cant[it.id] || 0) / it.cantidad), 0));
    const hayItems = computed(() => Object.values(cant).some(x => x > 0));
    async function devolver() {
      cargando.value = true;
      try {
        const items = v.value.items.filter(it => cant[it.id] > 0).map(it => ({ venta_item_id: it.id, cantidad: cant[it.id], danado: !!danado[it.id] }));
        await api.post(`/api/ventas/${p.ventaId}/devolucion`, { items, medio_reintegro: medio.value, motivo: motivo.value });
        toast('Devolución registrada.', 'ok'); emit('hecho');
      } catch (e) { errorToast(e); } finally { cargando.value = false; }
    }
    return { v, cant, danado, medio, motivo, cargando, restante, total, hayItems, devolver, peso };
  },
  template: `<Modal :titulo="'Devolución · ' + (v ? v.numero : '')" ancho="lg" @cerrar="$emit('cerrar')">
      <div v-if="v" class="stack">
        <table class="t compact"><thead><tr><th>Producto</th><th class="num">Vendido</th><th class="num">Ya devuelto</th><th class="num">Devolver</th><th>¿Dañado?</th><th class="num">Valor</th></tr></thead><tbody>
          <tr v-for="it in v.items" :key="it.id"><td>{{ it.descripcion }}</td><td class="num">{{ it.cantidad }}</td><td class="num">{{ it.devuelto }}</td>
            <td class="num"><input class="input sm num" type="number" min="0" :max="restante(it)" :disabled="restante(it) === 0" style="width:80px" v-model.number="cant[it.id]"></td>
            <td><label class="check"><input type="checkbox" v-model="danado[it.id]" :disabled="!cant[it.id]"> sí</label></td>
            <td class="num">{{ peso(Math.round(it.total * (cant[it.id] || 0) / it.cantidad)) }}</td></tr>
        </tbody></table>
        <div class="grid c2"><div class="field"><label>Reintegro al cliente</label><select class="input" v-model="medio"><option value="efectivo">En efectivo (sale de la caja)</option><option value="banco">Por banco / datáfono</option></select></div>
          <div class="field"><label>Motivo</label><input class="input" v-model="motivo" placeholder="Ej.: producto en mal estado"></div></div>
        <div class="row between"><span class="muted">Un producto dañado no vuelve al inventario: se registra como merma.</span><b class="num" style="font-size:20px">Total: {{ peso(total) }}</b></div>
      </div>
      <template #pie><button class="btn" @click="$emit('cerrar')">Cancelar</button><button class="btn primary" :disabled="!hayItems || !motivo.trim() || cargando" @click="devolver">Registrar devolución</button></template></Modal>`,
};

const ModalVentasTurno = {
  components: { ModalDevolucion },
  emits: ['cerrar'],
  setup() {
    const lista = ref([]), cargando = ref(true), dev = ref(null);
    async function cargar() { cargando.value = true; try { lista.value = await api.get('/api/ventas' + query({ turno_id: store.turno?.id })); } catch (e) { errorToast(e); } cargando.value = false; }
    async function anular(v) {
      const motivo = await pedirTexto('Anular venta ' + v.numero, `Motivo de la anulación (${peso(v.total)})`, { textoOk: 'Anular' });
      if (!motivo) return;
      try { await api.post(`/api/ventas/${v.id}/anular`, { motivo }); toast('Venta anulada. El stock se devolvió al inventario.', 'ok'); await refrescarTurno(); cargar(); } catch (e) { errorToast(e); }
    }
    onMounted(cargar);
    return { lista, cargando, dev, anular, cargar, peso, hora, recibo: v => verPdf('Recibo ' + v.numero, `/api/ventas/${v.id}/recibo`) };
  },
  template: `<Modal titulo="Ventas del turno" ancho="lg" @cerrar="$emit('cerrar')">
      <div class="empty" v-if="!cargando && !lista.length">Todavía no hay ventas en este turno.</div>
      <div class="table-wrap" style="max-height:60vh" v-else><table class="t"><thead><tr><th>Tiquete</th><th>Hora</th><th class="num">Total</th><th>Estado</th><th></th></tr></thead><tbody>
        <tr v-for="v in lista" :key="v.id"><td><b>{{ v.numero }}</b></td><td>{{ hora(v.fecha) }}</td><td class="num">{{ peso(v.total) }}</td>
          <td><span class="chip" :class="v.estado === 'anulada' ? 'danger' : 'ok'">{{ v.estado === 'anulada' ? 'Anulada' : 'Completada' }}</span></td>
          <td class="actions"><button class="btn sm ghost" @click="recibo(v)" title="Recibo"><Icono n="recibo"/></button>
            <template v-if="v.estado === 'completada'"><button class="btn sm ghost" @click="dev = v.id" title="Devolución"><Icono n="deshacer"/></button>
            <button class="btn sm ghost" @click="anular(v)" title="Anular venta"><Icono n="prohibido"/></button></template></td></tr>
      </tbody></table></div>
      <ModalDevolucion v-if="dev" :venta-id="dev" @cerrar="dev = null" @hecho="dev = null; cargar()"/></Modal>`,
};

// ───────────────────────── Vista principal ─────────────────────────
export const Caja = {
  components: { Cobro, Resultado, Buscador, ModalCantidad, ModalDescuento, ModalEtiqueta, ModalSuspendidas, ModalCrearRapido, ModalVentasTurno },
  setup() {
    const carrito = reactive({ items: [], descuentoGlobal: 0 });
    const scan = ref(''), sel = ref(-1), cantPend = ref(1), flash = ref(-1);
    const dlg = ref(null);   // 'cobro' | 'buscar' | 'cantidad' | 'descuento' | 'etiqueta' | 'suspendidas' | 'rapido' | 'ventas' | 'resultado'
    const modoCobro = ref('efectivo'), ventaOk = ref(null), buscarInicial = ref(''), codigoNuevo = ref('');
    const inScan = ref(null), ocupado = ref(false);

    // ── persistencia del carrito (por si se recarga la ventana)
    try { const g = JSON.parse(sessionStorage.getItem('pos_carrito') || 'null'); if (g && g.turno === store.turno?.id) { carrito.items = g.items; carrito.descuentoGlobal = g.descuentoGlobal || 0; sel.value = carrito.items.length - 1; } } catch (e) { /* */ }
    watch(carrito, () => { try { sessionStorage.setItem('pos_carrito', JSON.stringify({ turno: store.turno?.id, items: carrito.items, descuentoGlobal: carrito.descuentoGlobal })); } catch (e) { /* */ } }, { deep: true });

    const bruto = computed(() => carrito.items.reduce((s, i) => s + i.precio * i.cantidad, 0));
    const descLineas = computed(() => carrito.items.reduce((s, i) => s + (i.descuento || 0), 0));
    const total = computed(() => Math.max(0, bruto.value - descLineas.value - carrito.descuentoGlobal));
    const unidades = computed(() => carrito.items.reduce((s, i) => s + i.cantidad, 0));
    const itemSel = computed(() => carrito.items[sel.value] || null);
    const hayTurno = computed(() => !!store.turno);

    const enfocar = () => nextTick(() => { if (!document.querySelector('.overlay')) inScan.value?.focus(); });
    watch(dlg, d => { if (!d) enfocar(); });

    function recalcDescGlobal() { if (carrito.descuentoGlobal > bruto.value - descLineas.value) carrito.descuentoGlobal = Math.max(0, bruto.value - descLineas.value); }

    function agregar(prod, cantidad = 1) {
      const idx = carrito.items.findIndex(i => i.producto_id === prod.id && !i.descuento);
      if (idx >= 0) carrito.items[idx].cantidad += cantidad;
      else carrito.items.push({ producto_id: prod.id, nombre: prod.nombre, codigo: prod.codigos?.[0]?.codigo || prod.codigo_interno || '', precio: prod.precio_venta,
        cantidad, descuento: 0, stock: prod.stock_actual, tarifa: prod.tarifa_pct });
      sel.value = idx >= 0 ? idx : carrito.items.length - 1; flash.value = sel.value; setTimeout(() => { flash.value = -1; }, 600);
      const it = carrito.items[sel.value];
      if (it.stock < it.cantidad) toast(`Stock en sistema de «${it.nombre}»: ${it.stock}. Revise el inventario.`, 'warn', 3500);
      beep('ok');
      nextTick(() => document.querySelector('.cart tr.sel')?.scrollIntoView({ block: 'nearest' }));
    }

    async function alEscanear() {
      let txt = scan.value.trim(); scan.value = '';
      if (!txt) return;
      let m = txt.match(/^(\d{1,3})\s*[*xX]\s*$/);                       // "6*" → cantidad para el siguiente
      if (m) { cantPend.value = parseInt(m[1], 10); return; }
      m = txt.match(/^(\d{1,3})\s*[*xX]\s*(.+)$/);                       // "6*7701234" → cantidad + código
      let cant = cantPend.value;
      if (m) { cant = parseInt(m[1], 10); txt = m[2]; }
      if (!/^[\w-]+$/.test(txt) || !/\d/.test(txt)) { buscarInicial.value = txt; dlg.value = 'buscar'; return; }   // texto: buscar por nombre
      ocupado.value = true;
      try {
        const prod = await api.get('/api/productos/codigo/' + encodeURIComponent(txt));
        agregar(prod, cant * (prod.unidades_por_codigo || 1)); cantPend.value = 1;
      } catch (e) {
        beep('error');
        if (e.codigo === 'CODIGO_NO_EXISTE' && esAdmin()) { codigoNuevo.value = txt; dlg.value = 'rapido'; }
        else errorToast(e);
      } finally { ocupado.value = false; enfocar(); }
    }

    function cambiarCant(i, d) { const it = carrito.items[i]; if (!it) return; it.cantidad = Math.max(1, it.cantidad + d); if (it.descuento > it.precio * it.cantidad) it.descuento = 0; recalcDescGlobal(); }
    async function quitar(i = sel.value) {
      const it = carrito.items[i]; if (!it) return;
      if (store.config.exigir_pin_quitar_linea === '1' && !esAdmin()) {
        const pin = await pedirPin('Quitar un producto de la venta requiere el PIN del administrador.');
        if (!pin) return;
        try { await api.post('/api/auth/autorizar', { pin }); } catch (e) { return errorToast(e); }
      }
      carrito.items.splice(i, 1); sel.value = Math.min(i, carrito.items.length - 1); recalcDescGlobal(); beep('ok'); enfocar();
    }
    async function cancelarVenta() {
      if (!carrito.items.length) return;
      if (await confirmar('¿Cancelar la venta?', 'Se vaciará el carrito.', { peligro: true, textoOk: 'Sí, cancelar' })) { carrito.items = []; carrito.descuentoGlobal = 0; sel.value = -1; }
      enfocar();
    }
    function aplicarDescuento({ destino, monto }) {
      if (destino === 'linea' && itemSel.value) itemSel.value.descuento = monto;
      else carrito.descuentoGlobal = monto;
      recalcDescGlobal(); dlg.value = null;
    }

    function abrirCobro(modo) {
      if (!hayTurno.value) return toast('Primero abra la caja.', 'warn');
      if (!carrito.items.length || total.value <= 0) { beep('error'); return toast('Agregue productos antes de cobrar.', 'warn'); }
      modoCobro.value = modo; dlg.value = 'cobro';
    }
    async function cobrar(pagos) {
      try {
        const v = await api.post('/api/ventas', { items: carrito.items.map(i => ({ producto_id: i.producto_id, cantidad: i.cantidad, descuento: i.descuento || 0 })),
          pagos, descuento_global: carrito.descuentoGlobal });
        beep('cobro'); ventaOk.value = v; dlg.value = 'resultado';
        carrito.items = []; carrito.descuentoGlobal = 0; sel.value = -1; cantPend.value = 1;
        refrescarTurno();
      } catch (e) {
        errorToast(e); dlg.value = null;
        if (e.codigo === 'SIN_TURNO') refrescarTurno();
      }
    }

    async function suspender(etiqueta) {
      try {
        await api.post('/api/ventas-suspendidas', { carrito: { items: carrito.items, descuentoGlobal: carrito.descuentoGlobal, total: total.value }, etiqueta });
        carrito.items = []; carrito.descuentoGlobal = 0; sel.value = -1; dlg.value = null; toast('Venta suspendida. Puede retomarla con F7.', 'ok');
      } catch (e) { errorToast(e); }
    }
    async function retomar(s) {
      try {
        const d = await api.post(`/api/ventas-suspendidas/${s.id}/retomar`);
        carrito.items = d.items; carrito.descuentoGlobal = d.descuentoGlobal || 0; sel.value = carrito.items.length - 1; dlg.value = null;
      } catch (e) { errorToast(e); }
    }
    function abrirSuspender() { if (!carrito.items.length) return toast('No hay productos para suspender.', 'warn'); dlg.value = 'etiqueta'; }
    function abrirRetomar() { if (carrito.items.length) return toast('Termine o suspenda la venta actual antes de retomar otra.', 'warn'); dlg.value = 'suspendidas'; }
    function abrirDescuento() { if (!carrito.items.length) return; dlg.value = 'descuento'; }
    function abrirCantidad() { if (itemSel.value) dlg.value = 'cantidad'; }

    // ── teclado
    function tecla(e) {
      if (document.querySelector('.overlay') || store.bloqueado) return;
      const k = e.key;
      const mapa = { F2: () => { buscarInicial.value = ''; dlg.value = 'buscar'; }, F3: abrirCantidad, F4: () => quitar(), F5: abrirDescuento, F6: abrirSuspender,
        F7: abrirRetomar, F8: () => { dlg.value = 'ventas'; }, F9: () => abrirCobro('efectivo'), F10: () => abrirCobro('banco'), F11: () => abrirCobro('mixto'), Escape: cancelarVenta };
      if (mapa[k]) { e.preventDefault(); mapa[k](); return; }
      if (!scan.value) {
        if (k === 'ArrowDown') { e.preventDefault(); sel.value = Math.min(sel.value + 1, carrito.items.length - 1); }
        else if (k === 'ArrowUp') { e.preventDefault(); sel.value = Math.max(sel.value - 1, 0); }
        else if (k === '+' || k === '=') { e.preventDefault(); cambiarCant(sel.value, 1); }
        else if (k === '-') { e.preventDefault(); cambiarCant(sel.value, -1); }
        else if (k === 'Delete') { e.preventDefault(); quitar(); }
      }
    }
    function clicGlobal(e) { if (!document.querySelector('.overlay') && !e.target.closest('input, select, textarea, button, a, .cart')) enfocar(); }
    onMounted(() => { window.addEventListener('keydown', tecla); window.addEventListener('click', clicGlobal); refrescarTurno(); enfocar(); });
    onBeforeUnmount(() => { window.removeEventListener('keydown', tecla); window.removeEventListener('click', clicGlobal); });

    return { store, carrito, scan, sel, cantPend, flash, dlg, modoCobro, ventaOk, buscarInicial, codigoNuevo, inScan, ocupado, bruto, descLineas, total, unidades, itemSel, hayTurno,
      alEscanear, agregar, cambiarCant, quitar, cancelarVenta, aplicarDescuento, abrirCobro, cobrar, suspender, retomar, abrirSuspender, abrirRetomar, abrirDescuento, abrirCantidad,
      peso, miles, enfocar, verRecibo: () => { verPdf('Recibo ' + ventaOk.value.numero, `/api/ventas/${ventaOk.value.id}/recibo`); },
      ir: h => { location.hash = h; }, elegirBusqueda: p => { dlg.value = null; agregar(p, cantPend.value); cantPend.value = 1; },
      cantidadNueva: v => { itemSel.value.cantidad = v; recalcDescGlobal(); dlg.value = null; },
      creado: p => { dlg.value = null; agregar(p, cantPend.value); cantPend.value = 1; toast('Producto creado.', 'ok'); } };
  },
  template: `
    <div class="page nopad">
      <div v-if="!hayTurno" class="page"><div style="max-width:520px;margin:50px auto" class="card center stack">
        <Icono n="candado" class="ico xl" style="margin:0 auto;color:var(--faint)"/><h2>La caja está cerrada</h2>
        <p class="muted">Para vender hay que abrir el turno e indicar la base en efectivo.</p>
        <button class="btn primary lg" @click="ir('#/apertura')">Abrir caja</button></div></div>

      <template v-else>
      <div class="caja">
        <section class="caja-left">
          <div class="scan">
            <Icono n="barras"/>
            <input ref="inScan" class="input lg" v-model="scan" @keydown.enter.prevent="alEscanear" autocomplete="off" spellcheck="false"
                   placeholder="Escanee el código de barras o escriba el nombre…" :disabled="ocupado">
            <span class="qty chip accent" v-if="cantPend > 1">× {{ cantPend }}</span>
          </div>
          <div class="cart">
            <table class="t" v-if="carrito.items.length">
              <thead><tr><th style="width:44px">#</th><th>Producto</th><th class="center" style="width:150px">Cantidad</th><th class="num" style="width:120px">Precio</th><th class="num" style="width:130px">Total</th><th style="width:48px"></th></tr></thead>
              <tbody>
                <tr v-for="(it, i) in carrito.items" :key="it.producto_id + '-' + i" class="clickable" :class="{ sel: i === sel, flash: i === flash }" @click="sel = i">
                  <td class="muted">{{ i + 1 }}</td>
                  <td><b>{{ it.nombre }}</b><div class="xs muted">{{ it.codigo }}<span v-if="it.descuento" class="danger"> · desc. {{ peso(it.descuento) }}</span></div></td>
                  <td class="center"><span class="qtybox"><button @click.stop="cambiarCant(i, -1)" tabindex="-1">−</button><b>{{ it.cantidad }}</b><button @click.stop="cambiarCant(i, 1)" tabindex="-1">+</button></span></td>
                  <td class="num">{{ peso(it.precio) }}</td>
                  <td class="num"><b>{{ peso(it.precio * it.cantidad - (it.descuento || 0)) }}</b></td>
                  <td><button class="btn sm ghost icon" @click.stop="quitar(i)" tabindex="-1" title="Quitar (Supr)"><Icono n="x"/></button></td>
                </tr>
              </tbody>
            </table>
            <div v-else class="cart-empty"><div><Icono n="barras" class="ico xl" style="margin:0 auto 10px"/><h3>Listo para vender</h3><p class="small" style="margin-top:6px">Escanee un producto para comenzar.<br>Use <b>6*</b> y luego escanee para agregar 6 unidades.</p></div></div>
          </div>
        </section>

        <aside class="caja-right">
          <div class="total-card">
            <div class="lbl muted">Total a pagar</div>
            <div class="big">{{ peso(total) }}</div>
            <div class="row between small muted"><span>{{ unidades }} artículo{{ unidades === 1 ? '' : 's' }}</span>
              <span v-if="descLineas + carrito.descuentoGlobal > 0" class="danger">Descuento {{ peso(descLineas + carrito.descuentoGlobal) }}</span></div>
          </div>
          <div class="pay-btns">
            <button class="btn primary" @click="abrirCobro('efectivo')"><span><Icono n="billetes" class="ico lg"/> Efectivo</span><span class="kbd">F9</span></button>
            <button class="btn" @click="abrirCobro('banco')"><span><Icono n="tarjeta" class="ico lg"/> Banco / datáfono</span><span class="kbd">F10</span></button>
            <button class="btn" @click="abrirCobro('mixto')"><span><Icono n="porcentaje" class="ico lg"/> Pago mixto</span><span class="kbd">F11</span></button>
          </div>
          <div class="shortcuts">
            <button class="btn" @click="dlg = 'buscar'"><Icono n="buscar"/> Buscar <span class="kbd">F2</span></button>
            <button class="btn" @click="abrirCantidad" :disabled="!itemSel"><Icono n="lapiz"/> Cantidad <span class="kbd">F3</span></button>
            <button class="btn" @click="abrirDescuento" :disabled="!carrito.items.length"><Icono n="porcentaje"/> Descuento <span class="kbd">F5</span></button>
            <button class="btn" @click="quitar()" :disabled="!itemSel"><Icono n="basura"/> Quitar <span class="kbd">F4</span></button>
            <button class="btn" @click="abrirSuspender" :disabled="!carrito.items.length"><Icono n="pausa"/> Suspender <span class="kbd">F6</span></button>
            <button class="btn" @click="abrirRetomar"><Icono n="play"/> Retomar <span class="kbd">F7</span></button>
            <button class="btn" @click="dlg = 'ventas'"><Icono n="recibo"/> Ventas <span class="kbd">F8</span></button>
            <button class="btn" @click="cancelarVenta" :disabled="!carrito.items.length"><Icono n="x"/> Cancelar <span class="kbd">Esc</span></button>
          </div>
        </aside>
      </div>
      <div class="keybar"><span><b>Enter</b> agregar</span><span><b>6*</b> cantidad</span><span><b>↑ ↓</b> elegir línea</span><span><b>+ / −</b> cantidad</span><span><b>Supr</b> quitar</span></div>
      </template>

      <Cobro v-if="dlg === 'cobro'" :total="total" :modo-inicial="modoCobro" @cerrar="dlg = null" @confirmar="cobrar"/>
      <Resultado v-if="dlg === 'resultado'" :venta="ventaOk" @cerrar="dlg = null" @recibo="verRecibo"/>
      <Buscador v-if="dlg === 'buscar'" :inicial="buscarInicial" @cerrar="dlg = null" @elegir="elegirBusqueda"/>
      <ModalCantidad v-if="dlg === 'cantidad' && itemSel" :item="itemSel" @cerrar="dlg = null" @aceptar="cantidadNueva"/>
      <ModalDescuento v-if="dlg === 'descuento'" :item="itemSel" :bruto="bruto - descLineas" @cerrar="dlg = null" @aplicar="aplicarDescuento"/>
      <ModalEtiqueta v-if="dlg === 'etiqueta'" @cerrar="dlg = null" @aceptar="suspender"/>
      <ModalSuspendidas v-if="dlg === 'suspendidas'" @cerrar="dlg = null" @retomar="retomar"/>
      <ModalCrearRapido v-if="dlg === 'rapido'" :codigo="codigoNuevo" @cerrar="dlg = null" @creado="creado"/>
      <ModalVentasTurno v-if="dlg === 'ventas'" @cerrar="dlg = null"/>
    </div>`,
};
