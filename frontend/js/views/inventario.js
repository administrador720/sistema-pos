// Inventario: alertas, kardex, mermas y ajustes manuales
import { api, query } from '../api.js';
import { store, errorToast, toast, refrescarAlertas, confirmar } from '../store.js';
import { peso, entero, decimal, fechaHora, isoHoy } from '../util.js';

const { ref, reactive, computed, onMounted, watch } = Vue;

export const Inventario = {
  setup() {
    const tab = ref('alertas'), alertas = ref(null);
    // kardex
    const kProd = ref(null), kDesde = ref(isoHoy(-30)), kHasta = ref(isoHoy()), kardex = ref([]);
    // merma / ajuste
    const motivos = ref([]), merma = reactive({ prod: null, cantidad: null, motivo: 'VENCIDO', nota: '' }), ajuste = reactive({ prod: null, nuevo: null, nota: '' });
    const mermasMes = ref([]);

    async function cargarAlertas() { try { alertas.value = await api.get('/api/inventario/alertas'); store.alertas = alertas.value.total; } catch (e) { errorToast(e); } }
    async function cargarKardex() {
      if (!kProd.value) return;
      try { kardex.value = await api.get('/api/inventario/kardex' + query({ producto_id: kProd.value.id, desde: kDesde.value, hasta: kHasta.value })); } catch (e) { errorToast(e); }
    }
    async function cargarMermas() { try { mermasMes.value = (await api.get('/api/informes/mermas' + query({ desde: isoHoy(-30), hasta: isoHoy() }))).filas; } catch (e) { /* no crítico */ } }
    onMounted(async () => { cargarAlertas(); cargarMermas(); try { motivos.value = await api.get('/api/inventario/motivos-merma'); } catch (e) { /* */ } });
    watch([kDesde, kHasta], cargarKardex);
    function verKardex(a) { kProd.value = { id: a.id, nombre: a.nombre }; tab.value = 'kardex'; cargarKardex(); }
    function elegirKardex(p) { kProd.value = p; cargarKardex(); }

    async function elegirMerma(p) { merma.prod = await api.get('/api/productos/' + p.id); }
    async function elegirAjuste(p) { ajuste.prod = await api.get('/api/productos/' + p.id); ajuste.nuevo = ajuste.prod.stock_actual; }
    async function registrarMerma() {
      try {
        await api.post('/api/inventario/mermas', { producto_id: merma.prod.id, cantidad: merma.cantidad, motivo: merma.motivo, nota: merma.nota });
        toast(`Merma registrada: ${merma.cantidad} × ${merma.prod.nombre}.`, 'ok');
        merma.prod = null; merma.cantidad = null; merma.nota = ''; cargarAlertas(); cargarMermas();
      } catch (e) { errorToast(e); }
    }
    const dif = computed(() => ajuste.prod && ajuste.nuevo !== null ? ajuste.nuevo - ajuste.prod.stock_actual : 0);
    async function registrarAjuste() {
      if (!await confirmar('¿Ajustar el inventario?', `${ajuste.prod.nombre}\nDe ${ajuste.prod.stock_actual} a ${ajuste.nuevo} unidades (${dif.value > 0 ? '+' : ''}${dif.value}).\nQuedará registrado con su nombre y el motivo.`, { textoOk: 'Sí, ajustar' })) return;
      try {
        await api.post('/api/inventario/ajustes', { producto_id: ajuste.prod.id, nuevo_stock: ajuste.nuevo, nota: ajuste.nota });
        toast('Ajuste registrado.', 'ok'); ajuste.prod = null; ajuste.nota = ''; ajuste.nuevo = null; cargarAlertas();
      } catch (e) { errorToast(e); }
    }
    return { tab, alertas, kProd, kDesde, kHasta, kardex, motivos, merma, ajuste, mermasMes, dif, verKardex, elegirKardex, elegirMerma, elegirAjuste, registrarMerma, registrarAjuste,
      peso, entero, decimal, fechaHora };
  },
  template: `
    <div class="page">
      <div class="tabs"><button :class="{ on: tab === 'alertas' }" @click="tab = 'alertas'">Alertas de stock <span class="chip danger" v-if="alertas && alertas.total" style="margin-left:6px">{{ alertas.total }}</span></button>
        <button :class="{ on: tab === 'kardex' }" @click="tab = 'kardex'">Kardex</button><button :class="{ on: tab === 'mermas' }" @click="tab = 'mermas'">Mermas y ajustes</button></div>

      <div v-if="tab === 'alertas'" class="stack lg">
        <div class="alert ok" v-if="alertas && !alertas.total"><Icono n="check"/>Todo en orden: no hay productos agotados, bajo el mínimo ni con stock negativo.</div>
        <div class="grid c3" v-if="alertas">
          <div class="card pad0" v-for="g in [['Agotados', alertas.agotados, 'danger', 'Sin existencias y con mínimo definido'], ['Bajo el mínimo', alertas.bajo_minimo, 'warn', 'Hay que reponer pronto'], ['Stock negativo', alertas.negativos, 'danger', 'Se vendió más de lo registrado: revise compras o haga un conteo']]" :key="g[0]">
            <div style="padding:16px 18px 6px"><div class="row between"><h3>{{ g[0] }}</h3><span class="chip" :class="g[1].length ? g[2] : ''">{{ g[1].length }}</span></div><div class="xs muted">{{ g[3] }}</div></div>
            <div class="table-wrap" style="max-height:340px"><table class="t compact"><tbody>
              <tr v-for="a in g[1]" :key="a.id" class="clickable" @click="verKardex(a)"><td>{{ a.nombre }}</td><td class="num"><b :class="g[2]">{{ a.stock }}</b><span class="muted xs"> / mín. {{ a.minimo }}</span></td></tr>
              <tr v-if="!g[1].length"><td class="muted center" style="padding:24px">Ninguno</td></tr></tbody></table></div>
          </div>
        </div>
      </div>

      <div v-if="tab === 'kardex'" class="stack">
        <div class="row wrap" style="align-items:flex-end"><div class="field" style="min-width:340px;flex:1"><label>Producto</label><BuscaProducto :limpiar="false" @elegir="elegirKardex"/></div>
          <div class="field"><label>Desde</label><input type="date" class="input" v-model="kDesde"></div><div class="field"><label>Hasta</label><input type="date" class="input" v-model="kHasta"></div></div>
        <div class="card pad0" v-if="kProd"><div style="padding:14px 18px"><h3>{{ kProd.nombre }}</h3></div>
          <div class="table-wrap" style="max-height:calc(100vh - 340px)"><table class="t compact"><thead><tr><th>Fecha</th><th>Movimiento</th><th>Detalle</th><th class="num">Cantidad</th><th class="num">Costo</th><th class="num">Saldo</th><th>Usuario</th></tr></thead><tbody>
            <tr v-for="k in kardex" :key="k.id"><td class="nowrap">{{ fechaHora(k.fecha) }}</td><td>{{ k.tipo_nombre }}</td><td class="muted small">{{ k.motivo || '' }} {{ k.nota || '' }}</td>
              <td class="num" :class="k.cantidad < 0 ? 'danger' : 'ok'"><b>{{ k.cantidad > 0 ? '+' : '' }}{{ k.cantidad }}</b></td><td class="num">{{ decimal(k.costo_unitario) }}</td><td class="num"><b>{{ k.stock_resultante }}</b></td><td>{{ k.usuario }}</td></tr>
            <tr v-if="!kardex.length"><td colspan="7" class="empty">Sin movimientos en este periodo.</td></tr></tbody></table></div></div>
        <div class="empty" v-else><Icono n="lista" class="ico xl"/><div>Elija un producto para ver todas sus entradas y salidas.</div></div>
      </div>

      <div v-if="tab === 'mermas'" class="grid c2" style="align-items:start">
        <div class="card stack">
          <div><h2>Registrar merma o baja</h2><p class="muted small" style="margin-top:4px">Producto vencido, dañado, perdido o de consumo interno. Descuenta del inventario y queda en el informe de mermas.</p></div>
          <div class="field"><label>Producto</label><BuscaProducto @elegir="elegirMerma" v-if="!merma.prod"/>
            <div v-else class="row between card soft" style="padding:10px 14px"><div><b>{{ merma.prod.nombre }}</b><div class="xs muted">Stock actual: {{ merma.prod.stock_actual }}</div></div><button class="btn ghost sm" @click="merma.prod = null">Cambiar</button></div></div>
          <div class="grid c2"><div class="field"><label>Cantidad</label><InputDinero v-model="merma.cantidad"/></div>
            <div class="field"><label>Motivo</label><select class="input" v-model="merma.motivo"><option v-for="m in motivos" :key="m.codigo" :value="m.codigo">{{ m.nombre }}</option></select></div></div>
          <div class="field"><label>Nota (opcional)</label><input class="input" v-model="merma.nota"></div>
          <button class="btn primary" :disabled="!merma.prod || !merma.cantidad" @click="registrarMerma"><Icono n="basura"/> Registrar merma</button>
          <div v-if="mermasMes.length"><h3 style="margin:6px 0">Últimos 30 días</h3><table class="t compact"><tbody><tr v-for="m in mermasMes" :key="m.nombre"><td>{{ m.nombre }}</td><td class="num">{{ m.unidades }} u.</td><td class="num"><b>{{ peso(m.valor) }}</b></td></tr></tbody></table></div>
        </div>
        <div class="card stack">
          <div><h2>Ajuste manual de inventario</h2><p class="muted small" style="margin-top:4px">Para corregir una diferencia puntual. Si va a revisar muchos productos, mejor haga un <a href="#/conteos">conteo de inventario</a>.</p></div>
          <div class="field"><label>Producto</label><BuscaProducto @elegir="elegirAjuste" v-if="!ajuste.prod"/>
            <div v-else class="row between card soft" style="padding:10px 14px"><div><b>{{ ajuste.prod.nombre }}</b><div class="xs muted">Stock en el sistema: {{ ajuste.prod.stock_actual }}</div></div><button class="btn ghost sm" @click="ajuste.prod = null">Cambiar</button></div></div>
          <div class="field"><label>Cantidad real contada</label><InputDinero v-model="ajuste.nuevo" :disabled="!ajuste.prod"/></div>
          <div class="alert info" v-if="ajuste.prod && ajuste.nuevo !== null"><Icono n="info"/>Diferencia: <b>{{ dif > 0 ? '+' : '' }}{{ dif }}</b> unidades ({{ peso(Math.abs(dif) * ajuste.prod.costo_promedio) }} a costo)</div>
          <div class="field"><label>Motivo del ajuste (obligatorio)</label><input class="input" v-model="ajuste.nota" placeholder="Ej.: error al recibir el pedido"></div>
          <button class="btn primary" :disabled="!ajuste.prod || ajuste.nuevo === null || dif === 0 || !ajuste.nota.trim()" @click="registrarAjuste"><Icono n="check"/> Aplicar ajuste</button>
        </div>
      </div>
    </div>`,
};
