// Conteos de inventario físico: programación, captura ciega, revisión de inconsistencias y ajustes
import { api, query } from '../api.js';
import { store, esAdmin, errorToast, toast, confirmar, exportarArchivo, pedirTexto } from '../store.js';
import { peso, entero, fecha, fechaHora, porcentaje, isoHoy, beep, aFecha, cantidadTxt, conUnidad } from '../util.js';

const { ref, reactive, computed, onMounted, nextTick, watch } = Vue;

const FRECUENCIAS = { una_vez: 'Una sola vez', dias: 'Cada N días', semanal: 'Cada semana', quincenal: 'Cada 15 días', mensual: 'Cada mes' };
const TIPOS = { total: 'Todo el inventario', parcial: 'Una parte', ciclico: 'Cíclico' };
const ESTADO_CHIP = { borrador: '', en_conteo: 'accent', en_revision: 'warn', aplicado: 'ok', cancelado: '' };

function textoFrecuencia(p) {
  if (p.frecuencia === 'una_vez') return 'Una sola vez';
  const n = p.intervalo || 1;
  return { dias: `Cada ${n} día(s)`, semanal: n === 1 ? 'Cada semana' : `Cada ${n} semanas`, quincenal: n === 1 ? 'Cada 15 días' : `Cada ${n} quincenas`, mensual: n === 1 ? 'Cada mes' : `Cada ${n} meses` }[p.frecuencia];
}
function diasHasta(iso) { return Math.round((aFecha(iso) - aFecha(isoHoy())) / 86400000); }

// ───────────────────────── Qué se va a contar ─────────────────────────
const Alcance = {
  props: { modelValue: Object },
  setup(p) {
    const v = p.modelValue;
    const alternar = (lista, id) => { const i = lista.indexOf(id); i >= 0 ? lista.splice(i, 1) : lista.push(id); };
    return { v, store, alternar, TIPOS };
  },
  template: `
    <div class="stack">
      <div class="seg" style="align-self:flex-start"><button v-for="(t, k) in TIPOS" :key="k" :class="{ on: v.tipo === k }" @click="v.tipo = k">{{ t }}</button></div>
      <p class="hint" v-if="v.tipo === 'total'">Se cuentan todos los productos activos. Ideal para el inventario general del negocio.</p>
      <p class="hint" v-if="v.tipo === 'parcial'">Elija qué parte del negocio se cuenta: por categorías, proveedores o ubicaciones (pasillos).</p>
      <p class="hint" v-if="v.tipo === 'ciclico'">El sistema elige los productos que más conviene contar (primero los que tuvieron diferencias y los que hace más tiempo no se cuentan). Sirve para contar un poco cada semana sin parar la tienda.</p>
      <template v-if="v.tipo !== 'total'">
        <div class="field" v-if="v.tipo === 'ciclico'"><label>¿Cuántos productos contar?</label><input class="input num" type="number" min="1" v-model.number="v.n" style="max-width:160px"></div>
        <div class="field"><label>Categorías {{ v.tipo === 'ciclico' ? '(opcional)' : '' }}</label>
          <div class="pill-tabs"><button v-for="c in store.cat.categorias" :key="c.id" :class="{ on: v.categoria_ids.includes(c.id) }" @click="alternar(v.categoria_ids, c.id)">{{ c.nombre }}</button></div></div>
        <div class="field"><label>Proveedores {{ v.tipo === 'ciclico' ? '(opcional)' : '' }}</label>
          <div class="pill-tabs"><button v-for="c in store.cat.proveedores" :key="c.id" :class="{ on: v.proveedor_ids.includes(c.id) }" @click="alternar(v.proveedor_ids, c.id)">{{ c.nombre }}</button></div></div>
        <div class="field"><label>Ubicaciones / pasillos (separados por coma)</label><input class="input" v-model="v.ubicacionesTexto" placeholder="Pasillo 1, Pasillo 2"></div>
      </template>
    </div>`,
};
const alcanceInicial = () => ({ tipo: 'total', n: 50, categoria_ids: [], proveedor_ids: [], ubicacionesTexto: '' });
function alcanceAApi(v) {
  const a = {};
  if (v.categoria_ids.length) a.categoria_ids = v.categoria_ids;
  if (v.proveedor_ids.length) a.proveedor_ids = v.proveedor_ids;
  const u = v.ubicacionesTexto.split(',').map(x => x.trim()).filter(Boolean); if (u.length) a.ubicaciones = u;
  if (v.tipo === 'ciclico') a.n = v.n || 50;
  return a;
}

const ModalNuevo = {
  components: { Alcance },
  emits: ['cerrar', 'creado'],
  setup(p, { emit }) {
    const v = reactive(alcanceInicial()), nombre = ref('Conteo del ' + fecha(isoHoy())), iniciar = ref(true), cargando = ref(false);
    async function crear() {
      cargando.value = true;
      try {
        const c = await api.post('/api/conteos', { nombre: nombre.value, tipo: v.tipo, alcance: alcanceAApi(v) });
        if (iniciar.value) await api.post(`/api/conteos/${c.id}/iniciar`);
        toast(iniciar.value ? 'Conteo iniciado. Ya se puede contar con el lector.' : 'Conteo creado.', 'ok'); emit('creado', c);
      } catch (e) { errorToast(e); } finally { cargando.value = false; }
    }
    return { v, nombre, iniciar, cargando, crear };
  },
  template: `<Modal titulo="Nuevo conteo de inventario" ancho="md" @cerrar="$emit('cerrar')"><div class="stack">
      <div class="field"><label>Nombre</label><input class="input" v-model="nombre"></div><Alcance :model-value="v"/>
      <label class="check"><input type="checkbox" v-model="iniciar"> Iniciar de una vez (empezar a recibir capturas)</label></div>
      <template #pie><button class="btn" @click="$emit('cerrar')">Cancelar</button><button class="btn primary" :disabled="cargando || !nombre.trim()" @click="crear">{{ iniciar ? 'Crear e iniciar' : 'Crear' }}</button></template></Modal>`,
};

const ModalProgramar = {
  components: { Alcance },
  props: { prog: Object },
  emits: ['cerrar', 'guardado'],
  setup(p, { emit }) {
    const v = reactive(alcanceInicial());
    const f = reactive({ nombre: '', frecuencia: 'mensual', intervalo: 1, proxima_fecha: isoHoy(7) }), cargando = ref(false);
    if (p.prog) {
      Object.assign(f, { nombre: p.prog.nombre, frecuencia: p.prog.frecuencia, intervalo: p.prog.intervalo, proxima_fecha: p.prog.proxima_fecha });
      Object.assign(v, { tipo: p.prog.tipo, n: p.prog.alcance.n || 50, categoria_ids: [...(p.prog.alcance.categoria_ids || [])], proveedor_ids: [...(p.prog.alcance.proveedor_ids || [])],
        ubicacionesTexto: (p.prog.alcance.ubicaciones || []).join(', ') });
    }
    async function guardar() {
      cargando.value = true;
      const cuerpo = { ...f, tipo: v.tipo, alcance: alcanceAApi(v), activo: true };
      try { if (p.prog) await api.put('/api/conteos/programaciones/' + p.prog.id, cuerpo); else await api.post('/api/conteos/programaciones', cuerpo); toast('Programación guardada.', 'ok'); emit('guardado'); }
      catch (e) { errorToast(e); } finally { cargando.value = false; }
    }
    return { v, f, cargando, guardar, FRECUENCIAS };
  },
  template: `<Modal :titulo="prog ? 'Editar conteo programado' : 'Programar conteo'" ancho="md" @cerrar="$emit('cerrar')"><div class="stack">
      <div class="alert info"><Icono n="info"/><div>Usted decide cuándo hacerlo: el sistema solo le <b>recuerda</b> en el panel de control cuando se acerca la fecha. El conteo no empieza hasta que usted lo inicie.</div></div>
      <div class="field"><label>Nombre</label><input class="input" v-model="f.nombre" placeholder="Ej.: Conteo mensual general"></div>
      <div class="grid c3"><div class="field"><label>Repetir</label><select class="input" v-model="f.frecuencia"><option v-for="(t, k) in FRECUENCIAS" :key="k" :value="k">{{ t }}</option></select></div>
        <div class="field" v-if="['dias', 'semanal', 'mensual', 'quincenal'].includes(f.frecuencia)"><label>Cada cuántos</label><input class="input num" type="number" min="1" v-model.number="f.intervalo"></div>
        <div class="field"><label>{{ f.frecuencia === 'una_vez' ? 'Fecha' : 'Próxima fecha' }}</label><input class="input" type="date" v-model="f.proxima_fecha"></div></div>
      <Alcance :model-value="v"/></div>
      <template #pie><button class="btn" @click="$emit('cerrar')">Cancelar</button><button class="btn primary" :disabled="cargando || !f.nombre.trim()" @click="guardar">Guardar</button></template></Modal>`,
};

// ───────────────────────── Captura (a ciegas) ─────────────────────────
const Captura = {
  props: { conteo: Object },
  emits: ['cambio'],
  setup(p, { emit }) {
    const scan = ref(''), qty = ref(1), ubic = ref(''), preguntar = ref(false), pend = ref(null), capturas = ref([]), ultima = ref(null), prog = ref(p.conteo.progreso);
    const inScan = ref(null), inQty = ref(null), ocupado = ref(false), msgError = ref('');
    async function cargar() {
      try { capturas.value = await api.get(`/api/conteos/${p.conteo.id}/capturas`); prog.value = (await api.get('/api/conteos/' + p.conteo.id)).progreso; emit('cambio', prog.value); } catch (e) { errorToast(e); }
    }
    async function registrar(cuerpo) {
      ocupado.value = true; msgError.value = '';
      try {
        const r = await api.post(`/api/conteos/${p.conteo.id}/capturas`, { ...cuerpo, ubicacion: ubic.value || null });
        ultima.value = r; beep('ok'); await cargar();
      } catch (e) { beep('error'); msgError.value = e.message; }
      finally { ocupado.value = false; pend.value = null; qty.value = 1; nextTick(() => inScan.value?.focus()); }
    }
    async function alEscanear() {
      let t = scan.value.trim(); scan.value = ''; if (!t) return;
      let m = t.match(/^(\d{1,4}(?:[.,]\d{1,3})?)\s*[*xX]\s*(.*)$/), cant = qty.value || 1;
      if (m) { cant = parseFloat(m[1].replace(',', '.')); t = m[2]; if (!t) { qty.value = cant; return; } }
      // Se consulta el producto: si es por peso siempre se pregunta cuántos kilos hay (no se puede suponer «1»)
      let prod = null;
      try { prod = await api.get('/api/productos/codigo/' + encodeURIComponent(t)); } catch (e) { beep('error'); msgError.value = e.message; return; }
      if (preguntar.value || prod.unidad === 'kg') {
        pend.value = { codigo: t, nombre: prod.nombre, unidad: prod.unidad }; if (prod.unidad === 'kg') qty.value = null;
        nextTick(() => inQty.value?.focus()); return;
      }
      registrar({ codigo: t, cantidad: cant });
    }
    function confirmarCantidad() { if (pend.value && qty.value !== null) registrar({ codigo: pend.value.codigo, cantidad: qty.value }); }
    async function quitar(c) { try { await api.del(`/api/conteos/${p.conteo.id}/capturas/${c.id}`); toast('Captura eliminada.', 'ok', 1800); cargar(); } catch (e) { errorToast(e); } }
    onMounted(() => { cargar(); nextTick(() => inScan.value?.focus()); });
    const pct = computed(() => prog.value && prog.value.productos ? Math.round(prog.value.contados * 100 / prog.value.productos) : 0);
    return { scan, qty, ubic, preguntar, pend, capturas, ultima, prog, inScan, inQty, ocupado, msgError, pct, alEscanear, confirmarCantidad, quitar, entero, fechaHora, cantidadTxt };
  },
  template: `
    <div class="grid" style="grid-template-columns:minmax(0,1fr) 420px;align-items:start">
      <div class="stack">
        <div class="card stack">
          <div class="row between"><h2>Contar</h2><label class="check small"><input type="checkbox" v-model="preguntar"> Preguntar la cantidad después de escanear</label></div>
          <div class="scan"><Icono n="barras"/><input ref="inScan" class="input lg" v-model="scan" @keydown.enter.prevent="alEscanear" placeholder="Escanee cada producto (o use 12* y escanee para contar 12)" autocomplete="off" :disabled="ocupado || !!pend">
            <span class="qty chip accent" v-if="qty > 1 && !pend">× {{ cantidadTxt(qty) }}</span></div>
          <div v-if="pend" class="card soft stack sm"><b style="font-size:18px">{{ pend.nombre }}</b>
            <div class="row"><InputPeso v-if="pend.unidad === 'kg'" ref="inQty" v-model="qty" grande placeholder="kilos" style="flex:1" @enter="confirmarCantidad"/><InputDinero v-else ref="inQty" v-model="qty" grande style="flex:1" @enter="confirmarCantidad"/><button class="btn primary lg" @click="confirmarCantidad">Guardar</button><button class="btn lg" @click="pend = null; qty = 1">Cancelar</button></div></div>
          <div class="grid c2"><div class="field"><label>Ubicación / pasillo (opcional)</label><input class="input" v-model="ubic" placeholder="Ej.: bodega"></div>
            <div class="field"><label>Cantidad por escaneo</label><InputDinero v-model="qty"/></div></div>
          <div class="alert danger" v-if="msgError"><Icono n="alerta"/>{{ msgError }}</div>
          <div class="alert ok" v-else-if="ultima"><Icono n="check"/><div><b>{{ ultima.nombre }}</b> · +{{ cantidadTxt(ultima.cantidad) }} (llevas {{ cantidadTxt(ultima.total_contado) }} de este producto)</div></div>
          <p class="hint">El sistema <b>no muestra cuántas unidades debería haber</b>: así el conteo es honesto. Si cuenta el mismo producto en otra góndola, las cantidades se suman.</p>
        </div>
      </div>
      <div class="stack">
        <div class="card stack sm"><div class="row between"><h3>Avance</h3><b>{{ prog ? prog.contados : 0 }} / {{ prog ? prog.productos : 0 }} productos</b></div>
          <div class="progress"><i :style="{ width: pct + '%' }"></i></div><div class="xs muted">{{ prog ? prog.pendientes : 0 }} productos aún sin contar</div></div>
        <div class="card pad0"><div style="padding:14px 18px"><h3>Últimas capturas</h3></div>
          <div class="table-wrap" style="max-height:46vh"><table class="t compact"><tbody>
            <tr v-for="c in capturas" :key="c.id"><td><b>{{ c.nombre }}</b><div class="xs muted">{{ fechaHora(c.capturado_en) }}{{ c.ubicacion ? ' · ' + c.ubicacion : '' }}</div></td><td class="num"><b>+{{ cantidadTxt(c.cantidad) }}</b></td>
              <td><button class="btn ghost sm icon" @click="quitar(c)" title="Deshacer"><Icono n="deshacer"/></button></td></tr>
            <tr v-if="!capturas.length"><td class="empty">Aún no hay capturas.</td></tr></tbody></table></div></div>
      </div>
    </div>`,
};

// ───────────────────────── Revisión de inconsistencias ─────────────────────────
const Revision = {
  props: { conteo: Object },
  emits: ['cambio'],
  setup(p, { emit }) {
    const r = ref(null), filtro = ref('dif'), sel = reactive({}), dlgAplicar = ref(false), asumir = ref(false), cargando = ref(false);
    async function cargar() { try { r.value = await api.get(`/api/conteos/${p.conteo.id}/revision`); if (p.conteo.estado === 'en_revision' && r.value.resumen.con_diferencia === 0) filtro.value = 'todos'; } catch (e) { errorToast(e); } }
    onMounted(cargar);
    const editable = computed(() => p.conteo.estado === 'en_revision');
    const filas = computed(() => {
      if (!r.value) return [];
      const f = { dif: x => !x.no_contado && x.diferencia !== 0, falt: x => x.diferencia < 0, sob: x => x.diferencia > 0, rec: x => x.racha_faltantes >= 2, nc: x => x.no_contado, todos: () => true }[filtro.value];
      return r.value.items.filter(f);
    });
    const LIMITE = 400;
    const visibles = computed(() => filas.value.slice(0, LIMITE));
    const cuenta = computed(() => { const it = r.value?.items || []; return { dif: it.filter(x => !x.no_contado && x.diferencia !== 0).length, falt: it.filter(x => x.diferencia < 0).length, sob: it.filter(x => x.diferencia > 0).length,
      rec: it.filter(x => x.racha_faltantes >= 2).length, nc: it.filter(x => x.no_contado).length, todos: it.length }; });
    const seleccion = computed(() => Object.keys(sel).filter(k => sel[k]).map(Number));
    async function reconteo() {
      try { await api.post(`/api/conteos/${p.conteo.id}/reconteo`, { producto_ids: seleccion.value }); toast('Vuelve a captura: cuente de nuevo esos productos.', 'ok', 5000); emit('cambio'); } catch (e) { errorToast(e); }
    }
    async function aplicar() {
      cargando.value = true;
      try { await api.post(`/api/conteos/${p.conteo.id}/aplicar`, { asumir_cero_no_contados: asumir.value }); toast('Ajustes aplicados. El inventario quedó actualizado.', 'ok', 6000); dlgAplicar.value = false; emit('cambio'); }
      catch (e) { errorToast(e); } finally { cargando.value = false; }
    }
    async function cancelar() {
      if (await confirmar('¿Cancelar este conteo?', 'No se hará ningún ajuste de inventario.', { peligro: true, textoOk: 'Sí, cancelar conteo' })) {
        try { await api.post(`/api/conteos/${p.conteo.id}/cancelar`); emit('cambio'); } catch (e) { errorToast(e); } }
    }
    const exportar = f => exportarArchivo(`/api/conteos/${p.conteo.id}/informe`, {}, f, `conteo-${p.conteo.id}`).catch(errorToast);
    return { r, filtro, sel, filas, visibles, cuenta, seleccion, editable, dlgAplicar, asumir, cargando, reconteo, aplicar, cancelar, exportar, peso, entero, porcentaje, cantidadTxt };
  },
  template: `
    <div class="stack lg" v-if="r">
      <div class="grid c4">
        <div class="card kpi"><span class="lbl">Exactitud del inventario</span><span class="val" :class="r.resumen.exactitud_pct >= 95 ? 'ok' : r.resumen.exactitud_pct >= 85 ? 'warn' : 'danger'">{{ porcentaje(r.resumen.exactitud_pct) }}</span><span class="sub">{{ r.resumen.contados - r.resumen.con_diferencia }} de {{ r.resumen.contados }} sin diferencia</span></div>
        <div class="card kpi"><span class="lbl">Faltantes</span><span class="val danger">{{ peso(r.resumen.valor_faltantes) }}</span><span class="sub">{{ r.resumen.faltantes }} producto(s) · a costo</span></div>
        <div class="card kpi"><span class="lbl">Sobrantes</span><span class="val ok">{{ peso(r.resumen.valor_sobrantes) }}</span><span class="sub">{{ r.resumen.sobrantes }} producto(s) · a costo</span></div>
        <div class="card kpi"><span class="lbl">Diferencia neta</span><span class="val" :class="r.resumen.valor_neto < 0 ? 'danger' : ''">{{ peso(r.resumen.valor_neto) }}</span><span class="sub">{{ r.resumen.no_contados }} sin contar · {{ r.resumen.recurrentes }} con faltante repetido</span></div>
      </div>
      <div class="alert" v-if="r.resumen.recurrentes"><Icono n="alerta"/><div><b>{{ r.resumen.recurrentes }} producto(s) con faltante en conteos seguidos.</b> Puede ser robo, error de codificación o ventas con código equivocado: revíselos primero.</div></div>
      <div class="card pad0">
        <div class="row between wrap" style="padding:14px 18px;border-bottom:1px solid var(--border)">
          <div class="pill-tabs"><button v-for="t in [['dif', 'Con diferencia'], ['falt', 'Faltantes'], ['sob', 'Sobrantes'], ['rec', 'Faltante repetido'], ['nc', 'Sin contar'], ['todos', 'Todos']]" :key="t[0]" :class="{ on: filtro === t[0] }" @click="filtro = t[0]">{{ t[1] }} · {{ cuenta[t[0]] }}</button></div>
          <div class="row"><button class="btn sm" @click="exportar('pdf')"><Icono n="impresora"/> PDF</button><button class="btn sm" @click="exportar('xlsx')"><Icono n="bajar"/> Excel</button>
            <button class="btn sm" v-if="editable" :disabled="!seleccion.length" @click="reconteo"><Icono n="refrescar"/> Pedir reconteo ({{ seleccion.length }})</button></div>
        </div>
        <div class="table-wrap" style="max-height:calc(100vh - 430px)"><table class="t"><thead><tr><th v-if="editable" style="width:40px"></th><th>Producto</th><th>Ubicación</th><th class="num">Sistema</th><th class="num">Contado</th><th class="num">Diferencia</th><th class="num">Valor (costo)</th><th class="num">%</th><th></th></tr></thead><tbody>
          <tr v-for="x in visibles" :key="x.producto_id"><td v-if="editable"><input type="checkbox" v-model="sel[x.producto_id]"></td>
            <td><b>{{ x.nombre }}</b><div class="xs muted">{{ x.codigo }}</div></td><td class="muted">{{ x.ubicacion || '—' }}</td>
            <td class="num">{{ cantidadTxt(x.stock_teorico) }}<span class="xs muted" v-if="x.unidad === 'kg'"> kg</span></td><td class="num"><b>{{ x.contado === null ? '—' : cantidadTxt(x.contado) }}</b></td>
            <td class="num"><b :class="x.diferencia < 0 ? 'danger' : x.diferencia > 0 ? 'ok' : 'muted'">{{ x.diferencia === null ? '—' : (x.diferencia > 0 ? '+' : '') + cantidadTxt(x.diferencia) }}</b></td>
            <td class="num" :class="x.valor_diferencia < 0 ? 'danger' : ''">{{ x.valor_diferencia === null ? '' : peso(x.valor_diferencia) }}</td><td class="num muted">{{ x.pct === null ? '' : porcentaje(x.pct) }}</td>
            <td><span class="chip danger" v-if="x.racha_faltantes >= 2">Faltante × {{ x.racha_faltantes }} conteos</span><span class="chip warn" v-if="x.no_contado">Sin contar</span><span class="chip" v-if="x.reconteo && !x.no_contado">Recontado</span></td></tr>
          <tr v-if="!filas.length"><td colspan="9" class="empty">Nada en esta vista.</td></tr>
          <tr v-if="filas.length > 400"><td colspan="9" class="muted center small">Se muestran los primeros 400 de {{ entero(filas.length) }} productos (los de mayor valor primero). Use los filtros o exporte a Excel para verlos todos.</td></tr></tbody></table></div>
      </div>
      <div class="row end" v-if="editable"><button class="btn danger" @click="cancelar">Cancelar conteo</button><button class="btn primary lg" @click="dlgAplicar = true"><Icono n="check"/> Aplicar ajustes al inventario…</button></div>
      <Modal v-if="dlgAplicar" titulo="Aplicar ajustes de inventario" ancho="sm" @cerrar="dlgAplicar = false"><div class="stack">
        <p>Se ajustarán <b>{{ r.resumen.con_diferencia }}</b> producto(s) para que el sistema quede igual a lo contado. Diferencia neta: <b>{{ peso(r.resumen.valor_neto) }}</b> a costo.</p>
        <label class="check" v-if="r.resumen.no_contados"><input type="checkbox" v-model="asumir"> Asumir en <b>cero</b> los {{ r.resumen.no_contados }} productos que no se contaron</label>
        <div class="alert"><Icono n="alerta"/>Esta acción no se puede deshacer: el conteo queda cerrado.</div></div>
        <template #pie><button class="btn" @click="dlgAplicar = false">Volver</button><button class="btn primary" :disabled="cargando" @click="aplicar">Sí, aplicar ajustes</button></template></Modal>
    </div>`,
};

// ───────────────────────── Detalle de un conteo ─────────────────────────
const Detalle = {
  components: { Captura, Revision },
  props: { id: Number },
  setup(p) {
    const c = ref(null), clave = ref(0), cargando = ref(true);
    async function cargar() { try { c.value = await api.get('/api/conteos/' + p.id); clave.value++; } catch (e) { errorToast(e); } cargando.value = false; }
    onMounted(cargar);
    async function terminar() {
      const falta = c.value.progreso.pendientes;
      if (!await confirmar('¿Terminar la captura?', falta ? `Aún hay ${falta} producto(s) sin contar. Podrá decidir en la revisión si se dejan igual o se asumen en cero.` : 'Pasará a la revisión de inconsistencias.', { textoOk: 'Terminar y revisar' })) return;
      try { await api.post(`/api/conteos/${p.id}/cerrar-captura`); await cargar(); } catch (e) { errorToast(e); }
    }
    async function iniciar() { try { await api.post(`/api/conteos/${p.id}/iniciar`); await cargar(); } catch (e) { errorToast(e); } }
    return { c, clave, cargando, cargar, terminar, iniciar, esAdmin, ESTADO_CHIP, fechaHora, ir: () => { location.hash = '#/conteos'; } };
  },
  template: `
    <div class="page" v-if="c">
      <div class="page-head"><div class="row"><button class="btn ghost icon" @click="ir"><Icono n="izq"/></button>
        <div><h1>{{ c.nombre }}</h1><div class="row" style="margin-top:4px"><span class="chip" :class="ESTADO_CHIP[c.estado]">{{ c.estado_nombre }}</span><span class="muted small">{{ c.iniciado_en ? 'Inició ' + fechaHora(c.iniciado_en) : 'Creado ' + fechaHora(c.creado_en) }}</span></div></div></div>
        <button class="btn primary lg" v-if="c.estado === 'en_conteo' && esAdmin()" @click="terminar"><Icono n="check"/> Terminar captura y revisar</button></div>
      <Captura v-if="c.estado === 'en_conteo'" :conteo="c" :key="clave" @cambio="c.progreso = $event"/>
      <Revision v-else-if="c.estado === 'en_revision' || c.estado === 'aplicado'" :conteo="c" :key="clave + c.estado" @cambio="cargar"/>
      <div v-else-if="c.estado === 'borrador'" class="card center stack"><h2>Este conteo todavía no se ha iniciado</h2>
        <button class="btn primary lg" style="align-self:center" @click="iniciar" v-if="esAdmin()">Iniciar conteo</button></div>
      <div v-else class="empty">Este conteo fue cancelado.</div>
    </div>`,
};

// ───────────────────────── Lista ─────────────────────────
export const Conteos = {
  components: { Detalle, ModalNuevo, ModalProgramar },
  setup() {
    const id = computed(() => parseInt(store.ruta.arg, 10) || null);
    const lista = ref([]), progs = ref([]), recordatorios = ref([]), dlg = ref(null), editProg = ref(null), cargando = ref(true);
    async function cargar() {
      cargando.value = true;
      try {
        lista.value = await api.get('/api/conteos');
        if (esAdmin()) progs.value = await api.get('/api/conteos/programaciones');
      } catch (e) { errorToast(e); }
      cargando.value = false;
    }
    onMounted(() => { if (!id.value) cargar(); });
    const hayEnCurso = computed(() => lista.value.find(c => c.estado === 'en_conteo' || c.estado === 'en_revision'));
    const abrir = c => { location.hash = '#/conteos/' + c.id; };
    async function iniciarProg(pr) {
      if (hayEnCurso.value) return toast('Ya hay un conteo en curso. Termínelo o cancélelo primero.', 'warn');
      if (!await confirmar('¿Iniciar este conteo ahora?', `«${pr.nombre}» empieza a recibir capturas.`, { textoOk: 'Iniciar conteo' })) return;
      try { const c = await api.post(`/api/conteos/programaciones/${pr.id}/iniciar`); abrir(c); } catch (e) { errorToast(e); }
    }
    async function borrarProg(pr) { if (await confirmar('¿Eliminar la programación?', `«${pr.nombre}»`, { peligro: true, textoOk: 'Eliminar' })) { try { await api.del('/api/conteos/programaciones/' + pr.id); cargar(); } catch (e) { errorToast(e); } } }
    const estadoProg = pr => { const d = diasHasta(pr.proxima_fecha); return d < 0 ? { t: `Vencido hace ${-d} día(s)`, c: 'danger' } : d === 0 ? { t: 'Hoy', c: 'warn' } : d <= 3 ? { t: `En ${d} día(s)`, c: 'warn' } : { t: `En ${d} días`, c: '' }; };
    return { id, lista, progs, dlg, editProg, cargando, hayEnCurso, store, esAdmin, abrir, iniciarProg, borrarProg, estadoProg, textoFrecuencia, TIPOS, ESTADO_CHIP, fecha, fechaHora, porcentaje,
      hecho: c => { dlg.value = null; if (c) abrir(c); else cargar(); } };
  },
  template: `
    <Detalle v-if="id" :id="id"/>
    <div class="page" v-else>
      <div class="page-head"><div><p class="muted" v-if="esAdmin()">Cuente el inventario cuando usted lo decida y revise las diferencias antes de ajustar.</p>
        <p class="muted" v-else>Aquí aparece el conteo de inventario en curso.</p></div>
        <div class="row" v-if="esAdmin()"><button class="btn" @click="editProg = null; dlg = 'programar'"><Icono n="calendario"/> Programar conteo</button><button class="btn primary" @click="dlg = 'nuevo'"><Icono n="mas"/> Nuevo conteo</button></div></div>

      <div class="alert info" v-if="hayEnCurso" style="margin-bottom:16px"><Icono n="conteo"/><div class="grow"><b>Conteo en curso:</b> {{ hayEnCurso.nombre }} ({{ hayEnCurso.estado_nombre }})</div>
        <button class="btn sm primary" @click="abrir(hayEnCurso)">{{ hayEnCurso.estado === 'en_conteo' ? 'Seguir contando' : 'Ir a la revisión' }}</button></div>

      <div class="stack lg">
        <div class="card pad0" v-if="esAdmin()"><div style="padding:16px 20px 4px"><h2><Icono n="calendario"/> Conteos programados</h2></div>
          <table class="t"><thead><tr><th>Nombre</th><th>Qué se cuenta</th><th>Se repite</th><th>Próxima fecha</th><th></th></tr></thead><tbody>
            <tr v-for="pr in progs" :key="pr.id" :style="{ opacity: pr.activo ? 1 : .5 }"><td><b>{{ pr.nombre }}</b></td><td>{{ TIPOS[pr.tipo] }}<span v-if="pr.tipo === 'ciclico'" class="muted"> ({{ pr.alcance.n || 50 }} productos)</span></td><td>{{ textoFrecuencia(pr) }}</td>
              <td><span v-if="pr.activo">{{ fecha(pr.proxima_fecha) }} <span class="chip" :class="estadoProg(pr).c" style="margin-left:6px">{{ estadoProg(pr).t }}</span></span><span v-else class="muted">Finalizado</span></td>
              <td class="actions"><button class="btn sm primary" @click="iniciarProg(pr)">Iniciar ahora</button><button class="btn sm ghost icon" @click="editProg = pr; dlg = 'programar'"><Icono n="lapiz"/></button><button class="btn sm ghost icon" @click="borrarProg(pr)"><Icono n="basura"/></button></td></tr>
            <tr v-if="!progs.length"><td colspan="5" class="empty">No hay conteos programados. Use «Programar conteo» para que el sistema le recuerde cuándo contar.</td></tr></tbody></table></div>

        <div class="card pad0"><div style="padding:16px 20px 4px"><h2><Icono n="conteo"/> {{ esAdmin() ? 'Historial de conteos' : 'Conteo en captura' }}</h2></div>
          <table class="t"><thead><tr><th>Nombre</th><th>Tipo</th><th>Estado</th><th>Fecha</th><th class="num">Exactitud</th></tr></thead><tbody>
            <tr v-for="c in lista" :key="c.id" class="clickable" @click="abrir(c)"><td><b>{{ c.nombre }}</b></td><td>{{ TIPOS[c.tipo] }}</td><td><span class="chip" :class="ESTADO_CHIP[c.estado]">{{ c.estado_nombre }}</span></td>
              <td>{{ fechaHora(c.cerrado_en || c.iniciado_en || c.creado_en) }}</td><td class="num">{{ c.exactitud_pct === null ? '—' : porcentaje(c.exactitud_pct) }}</td></tr>
            <tr v-if="!cargando && !lista.length"><td colspan="5" class="empty">{{ esAdmin() ? 'Todavía no se ha hecho ningún conteo.' : 'No hay ningún conteo en captura en este momento.' }}</td></tr></tbody></table></div>
      </div>
      <ModalNuevo v-if="dlg === 'nuevo'" @cerrar="dlg = null" @creado="hecho"/>
      <ModalProgramar v-if="dlg === 'programar'" :prog="editProg" @cerrar="dlg = null" @guardado="hecho()"/>
    </div>`,
};
