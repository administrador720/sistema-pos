// Panel de control: rendimiento del negocio, rotación de inventario y alertas
import { api, query } from '../api.js';
import { store, errorToast } from '../store.js';
import { peso, entero, formatear, fecha, hora, fechaHora, isoHoy, inicioMes, css, porcentaje, decimal, aFecha, diaSemana } from '../util.js';

const { ref, reactive, computed, onMounted } = Vue;

const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const abreviar = n => Math.abs(n) >= 1e6 ? (n / 1e6).toFixed(1).replace('.', ',') + ' M' : Math.abs(n) >= 1e3 ? Math.round(n / 1e3) + ' mil' : String(Math.round(n));
const DIAS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];
const ORDEN_DIAS = [1, 2, 3, 4, 5, 6, 0];   // en la base 0 = domingo

const PERIODOS = [['hoy', 'Hoy'], ['7', '7 días'], ['30', '30 días'], ['mes', 'Este mes'], ['mes_ant', 'Mes pasado'], ['custom', 'Personalizado']];
function rangoDe(k) {
  const hoy = isoHoy(), d = new Date();
  if (k === 'hoy') return [hoy, hoy];
  if (k === '7') return [isoHoy(-6), hoy];
  if (k === '30') return [isoHoy(-29), hoy];
  if (k === 'mes') return [inicioMes(), hoy];
  const ini = new Date(d.getFullYear(), d.getMonth() - 1, 1), fin = new Date(d.getFullYear(), d.getMonth(), 0);
  const f = x => `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}-${String(x.getDate()).padStart(2, '0')}`;
  return [f(ini), f(fin)];
}

// Tarjeta de gráfico: título, alternar entre gráfico y tabla (la tabla es siempre el equivalente accesible)
const Tarjeta = {
  props: { titulo: String, sub: String, columnas: Array, filas: Array },
  setup() { const vista = ref('grafico'); return { vista, formatear }; },
  template: `
    <div class="card viz-card">
      <div class="card-title"><h3>{{ titulo }}</h3>
        <div class="seg"><button :class="{ on: vista === 'grafico' }" @click="vista = 'grafico'">Gráfico</button><button :class="{ on: vista === 'tabla' }" @click="vista = 'tabla'">Tabla</button></div></div>
      <div class="sub" v-if="sub">{{ sub }}</div>
      <slot v-if="vista === 'grafico'"/>
      <div v-else class="viz-tabla"><table class="t compact"><thead><tr><th v-for="c in columnas" :key="c.key" :class="{ num: c.num }">{{ c.titulo }}</th></tr></thead><tbody>
        <tr v-for="(f, i) in filas" :key="i"><td v-for="c in columnas" :key="c.key" :class="{ num: c.num }">{{ formatear(f[c.key], c.tipo) }}</td></tr>
        <tr v-if="!filas.length"><td :colspan="columnas.length" class="muted center">Sin datos en este periodo</td></tr></tbody></table></div>
      <slot name="pie"/>
    </div>`,
};

function delta(v) {
  if (v === null || v === undefined) return null;
  const mag = Math.abs(v) >= 1000 ? 'más de 1.000' : Math.abs(v).toFixed(1).replace('.', ',');   // base tan pequeña que el % no dice nada
  return { txt: `${v > 0 ? '▲' : v < 0 ? '▼' : '•'} ${mag} % vs. periodo anterior`, cls: v > 0 ? 'up' : v < 0 ? 'down' : '' };
}

export const Dashboard = {
  components: { Tarjeta },
  setup() {
    const per = ref('30'), custom = reactive({ desde: isoHoy(-29), hasta: isoHoy() });
    const d = ref(null), rot = ref(null), cargando = ref(true), metProd = ref('ventas');
    const rango = computed(() => per.value === 'custom' ? [custom.desde, custom.hasta] : rangoDe(per.value));

    async function cargar() {
      cargando.value = true;
      const [desde, hasta] = rango.value;
      try { d.value = await api.get('/api/dashboard' + query({ desde, hasta })); } catch (e) { errorToast(e); }
      cargando.value = false;
      rot.value = null;
      api.get('/api/informes/rotacion' + query({ desde, hasta, agrupar: 'total' })).then(r => { rot.value = r.filas[0] || { vacio: true }; }).catch(() => { rot.value = { vacio: true }; });
    }
    onMounted(cargar);
    const elegir = k => { per.value = k; if (k !== 'custom') cargar(); };

    // ── opciones de gráficos (los colores salen de las variables del tema activo)
    const base = () => {
      store.tema;  // dependencia: se recalcula al cambiar de tema
      const c = { grid: css('--viz-grid'), eje: css('--viz-eje'), texto: css('--viz-texto'), tinta: css('--viz-tinta'), marca: css('--viz-marca'), sup: css('--surface') };
      const tooltip = { backgroundColor: c.sup, borderColor: c.grid, borderWidth: 1, padding: [10, 12], textStyle: { color: c.tinta, fontFamily: 'Inter, system-ui, sans-serif', fontSize: 13 }, extraCssText: 'box-shadow:0 8px 24px rgba(0,0,0,.14);border-radius:10px' };
      return { c, tooltip };
    };
    const fila = (color, valor, nombre) => `<div style="display:flex;align-items:center;gap:8px;margin-top:4px"><span style="width:14px;height:3px;border-radius:2px;background:${color}"></span><b style="font-size:14px">${esc(valor)}</b><span style="opacity:.7">${esc(nombre)}</span></div>`;

    const opVentas = computed(() => {
      const { c, tooltip } = base(), s = d.value?.serie || [];
      return {
        animationDuration: 300, grid: { left: 4, right: 10, top: 14, bottom: 4, containLabel: true },
        xAxis: { type: 'category', data: s.map(x => x.fecha), axisTick: { show: false }, axisLine: { lineStyle: { color: c.eje } },
          axisLabel: { color: c.texto, hideOverlap: true, formatter: v => v.slice(8, 10) + '/' + v.slice(5, 7) } },
        yAxis: { type: 'value', axisLabel: { color: c.texto, formatter: v => abreviar(v) }, splitLine: { lineStyle: { color: c.grid, width: 1 } }, axisLine: { show: false } },
        tooltip: { ...tooltip, trigger: 'axis', axisPointer: { type: 'shadow', shadowStyle: { color: c.grid, opacity: .45 } },
          formatter: p => { const x = s[p[0].dataIndex]; return `<div style="opacity:.7;margin-bottom:2px">${esc(diaSemana(x.fecha))} ${esc(fecha(x.fecha))}</div>` + fila(c.marca, peso(x.ventas), 'Ventas') + fila(c.eje, entero(x.tiquetes), 'Tiquetes'); } },
        series: [{ type: 'bar', data: s.map(x => x.ventas), barMaxWidth: 24, itemStyle: { color: c.marca, borderRadius: [4, 4, 0, 0] }, emphasis: { itemStyle: { opacity: .82 } } }],
      };
    });
    const colsVentas = [{ key: 'fecha', titulo: 'Día', tipo: 'fecha' }, { key: 'tiquetes', titulo: 'Tiquetes', tipo: 'entero', num: true }, { key: 'ventas', titulo: 'Ventas', tipo: 'dinero', num: true }];

    const opCalor = computed(() => {
      const { c, tooltip } = base(), cal = d.value?.calor || [];
      const horas = []; const hs = cal.map(x => x.hora); const h0 = Math.min(6, ...(hs.length ? hs : [6])), h1 = Math.max(21, ...(hs.length ? hs : [21]));
      for (let h = h0; h <= h1; h++) horas.push(h);
      const datos = cal.map(x => [horas.indexOf(x.hora), ORDEN_DIAS.indexOf(x.dia), x.tiquetes]).filter(x => x[0] >= 0);
      const max = Math.max(1, ...datos.map(x => x[2]));
      return {
        animationDuration: 300, grid: { left: 4, right: 10, top: 6, bottom: 56, containLabel: true },
        xAxis: { type: 'category', data: horas.map(h => h + 'h'), axisTick: { show: false }, axisLine: { show: false }, splitArea: { show: false }, axisLabel: { color: c.texto, interval: 1 } },
        yAxis: { type: 'category', data: DIAS, inverse: true, axisTick: { show: false }, axisLine: { show: false }, axisLabel: { color: c.texto } },
        visualMap: { type: 'continuous', min: 0, max, calculable: false, orient: 'horizontal', left: 'center', bottom: 6, itemWidth: 8, itemHeight: 190, text: ['Más tiquetes', 'Menos'],
          textStyle: { color: c.texto }, inRange: { color: [css('--viz-h0'), css('--viz-h1'), css('--viz-h2'), css('--viz-h3')] } },
        tooltip: { ...tooltip, trigger: 'item', formatter: p => { const x = cal.find(k => ORDEN_DIAS.indexOf(k.dia) === p.value[1] && horas.indexOf(k.hora) === p.value[0]);
          return `<div style="opacity:.7">${esc(DIAS[p.value[1]])} · ${horas[p.value[0]]}:00</div>` + fila(c.marca, entero(p.value[2]) + ' tiquetes', '') + (x ? fila(c.eje, peso(x.ventas), 'Ventas') : ''); } },
        series: [{ type: 'heatmap', data: datos, itemStyle: { borderColor: c.sup, borderWidth: 2, borderRadius: 4 }, emphasis: { itemStyle: { borderColor: c.tinta, borderWidth: 2 } } }],
      };
    });
    const filasCalor = computed(() => (d.value?.calor || []).slice().sort((a, b) => b.tiquetes - a.tiquetes).slice(0, 12).map(x => ({ dia: DIAS[ORDEN_DIAS.indexOf(x.dia)], hora: x.hora + ':00', tiquetes: x.tiquetes, ventas: x.ventas })));
    const colsCalor = [{ key: 'dia', titulo: 'Día' }, { key: 'hora', titulo: 'Hora' }, { key: 'tiquetes', titulo: 'Tiquetes', tipo: 'entero', num: true }, { key: 'ventas', titulo: 'Ventas', tipo: 'dinero', num: true }];

    function opBarras(items, claveValor, nombreValor) {
      const { c, tooltip } = base();
      return {
        animationDuration: 300, grid: { left: 4, right: 70, top: 4, bottom: 4, containLabel: true },
        xAxis: { type: 'value', show: false },
        yAxis: { type: 'category', inverse: true, data: items.map(x => x.nombre), axisTick: { show: false }, axisLine: { lineStyle: { color: c.eje } },
          axisLabel: { color: c.texto, width: 150, overflow: 'truncate' } },
        tooltip: { ...tooltip, trigger: 'axis', axisPointer: { type: 'shadow', shadowStyle: { color: c.grid, opacity: .45 } },
          formatter: p => { const x = items[p[0].dataIndex]; return `<div style="opacity:.7;margin-bottom:2px">${esc(x.nombre)}</div>` + fila(c.marca, peso(x[claveValor]), nombreValor); } },
        series: [{ type: 'bar', data: items.map(x => x[claveValor]), barMaxWidth: 20, itemStyle: { color: c.marca, borderRadius: [0, 4, 4, 0] }, emphasis: { itemStyle: { opacity: .82 } },
          label: { show: true, position: 'right', color: c.tinta, fontSize: 12, formatter: p => '$ ' + abreviar(p.value) } }],
      };
    }
    const itemsProd = computed(() => (metProd.value === 'ventas' ? d.value?.top_ventas : d.value?.top_margen) || []);
    const opProd = computed(() => opBarras(itemsProd.value, metProd.value === 'ventas' ? 'ventas' : 'margen', metProd.value === 'ventas' ? 'Ventas' : 'Margen bruto'));
    const opCat = computed(() => opBarras(d.value?.top_categorias || [], 'ventas', 'Ventas'));
    const altoBarras = n => ({ height: Math.max(120, n * 34 + 12) + 'px' });

    // ── medios de pago: barra apilada (parte de un todo) con la leyenda como etiqueta directa
    const medios = computed(() => {
      const lista = d.value?.medios || [], total = lista.reduce((s, x) => s + x.monto, 0) || 1;
      const orden = store.cat.medios_pago.filter(m => m.activo).map(m => m.nombre);
      return lista.map(x => { const i = orden.indexOf(x.medio); return { ...x, pct: x.monto * 100 / total, color: i >= 0 && i < 4 ? `var(--viz-${i + 1})` : 'var(--viz-eje)' }; });
    });
    const colsMedios = [{ key: 'medio', titulo: 'Medio de pago' }, { key: 'monto', titulo: 'Monto', tipo: 'dinero', num: true }, { key: 'pct', titulo: '%', tipo: 'porcentaje', num: true }];

    const k = computed(() => d.value?.kpis);
    const periodoTxt = computed(() => { const [a, b] = rango.value; return a === b ? fecha(a) : `${fecha(a)} – ${fecha(b)}`; });
    const estadoDif = x => x === 0 ? { t: 'Cuadra', c: 'ok', i: 'check' } : x < 0 ? { t: 'Faltante', c: 'danger', i: 'alerta' } : { t: 'Sobrante', c: 'warn', i: 'info' };
    return { PERIODOS, per, custom, d, rot, cargando, metProd, elegir, cargar, opVentas, colsVentas, opCalor, filasCalor, colsCalor, opProd, opCat, itemsProd, medios, colsMedios, k, periodoTxt,
      delta, estadoDif, altoBarras, store, peso, entero, porcentaje, decimal, fecha, fechaHora, formatear, ir: h => { location.hash = h; },
      colsProd: [{ key: 'nombre', titulo: 'Producto' }, { key: 'ventas', titulo: 'Ventas', tipo: 'dinero', num: true }, { key: 'unidades', titulo: 'Unidades', tipo: 'entero', num: true }],
      colsProdMargen: [{ key: 'nombre', titulo: 'Producto' }, { key: 'margen', titulo: 'Margen', tipo: 'dinero', num: true }],
      colsCat: [{ key: 'nombre', titulo: 'Categoría' }, { key: 'ventas', titulo: 'Ventas', tipo: 'dinero', num: true }, { key: 'margen', titulo: 'Margen', tipo: 'dinero', num: true }] };
  },
  template: `
    <div class="page">
      <!-- Filtro de periodo: una sola fila sobre todo lo que gobierna -->
      <div class="filtros">
        <div class="seg"><button v-for="p in PERIODOS" :key="p[0]" :class="{ on: per === p[0] }" @click="elegir(p[0])">{{ p[1] }}</button></div>
        <template v-if="per === 'custom'"><input type="date" class="input sm" style="width:auto" v-model="custom.desde"><span class="muted">a</span><input type="date" class="input sm" style="width:auto" v-model="custom.hasta"><button class="btn sm primary" @click="cargar">Ver</button></template>
        <span class="muted small" style="margin-left:auto">{{ periodoTxt }}</span>
      </div>

      <div v-if="!d" class="empty">Cargando panel…</div>
      <div v-else class="refresca" :class="{ carga: cargando }">
        <div class="alert" v-if="d.respaldo && d.respaldo.alerta" style="margin-bottom:14px"><Icono n="base"/><div class="grow">{{ d.respaldo.alerta }}</div><a href="#/config" class="bold">Respaldos</a></div>

        <!-- Cifra principal (una sola) + indicadores -->
        <div class="grid c4" style="margin-bottom:14px">
          <div class="card kpi hero" style="grid-column:span 2"><span class="lbl">Ventas netas</span><span class="val">{{ peso(k.ventas) }}</span>
            <span class="sub"><span class="delta" v-if="delta(k.ventas_var)" :class="delta(k.ventas_var).cls">{{ delta(k.ventas_var).txt }}</span><span v-else>Sin periodo anterior para comparar</span></span>
            <span class="sub">{{ entero(k.transacciones) }} tiquetes · descuenta devoluciones</span></div>
          <div class="card kpi"><span class="lbl">Tiquetes</span><span class="val">{{ entero(k.transacciones) }}</span>
            <span class="sub"><span class="delta" v-if="delta(k.transacciones_var)" :class="delta(k.transacciones_var).cls">{{ delta(k.transacciones_var).txt }}</span></span></div>
          <div class="card kpi"><span class="lbl">Ticket promedio</span><span class="val">{{ peso(k.ticket_promedio) }}</span>
            <span class="sub"><span class="delta" v-if="delta(k.ticket_promedio_var)" :class="delta(k.ticket_promedio_var).cls">{{ delta(k.ticket_promedio_var).txt }}</span><span v-else>{{ k.unidades_por_ticket }} artículos por tiquete</span></span></div>
          <div class="card kpi"><span class="lbl">Margen bruto</span><span class="val">{{ porcentaje(k.margen_pct) }}</span>
            <span class="sub">{{ peso(k.margen) }}<span class="delta" v-if="delta(k.margen_var)" :class="delta(k.margen_var).cls">{{ delta(k.margen_var).txt }}</span></span></div>
          <div class="card kpi"><span class="lbl">Rotación del inventario</span>
            <span class="val" v-if="rot && !rot.vacio && rot.rotacion">{{ decimal(rot.rotacion) }}<span class="muted small" style="font-weight:500"> veces</span></span><span class="val muted" v-else>{{ rot ? '—' : '…' }}</span>
            <span class="sub" v-if="rot && rot.dias_inventario">{{ decimal(rot.dias_inventario, 0) }} días de inventario · GMROI {{ decimal(rot.gmroi) }}</span><span class="sub" v-else-if="rot">Aún sin datos suficientes</span></div>
          <div class="card kpi"><span class="lbl">Valor del inventario (a costo)</span><span class="val">{{ peso(d.inventario.valor) }}</span><span class="sub">{{ entero(d.inventario.productos) }} {{ d.inventario.productos === 1 ? 'producto activo' : 'productos activos' }}</span></div>
          <a class="card kpi" href="#/inventario" style="text-decoration:none;color:inherit"><span class="lbl">Alertas de stock</span>
            <span class="val" :class="d.inventario.agotados + d.inventario.bajo_minimo + d.inventario.negativos ? 'warn' : 'ok'">{{ d.inventario.agotados + d.inventario.bajo_minimo + d.inventario.negativos }}</span>
            <span class="sub">{{ d.inventario.agotados }} agotados · {{ d.inventario.bajo_minimo }} bajo mínimo · {{ d.inventario.negativos }} negativos</span></a>
        </div>

        <div class="dash-fila f21">
          <Tarjeta titulo="Ventas por día" :sub="'Ventas netas diarias · ' + periodoTxt" :columnas="colsVentas" :filas="d.serie">
            <Grafico v-if="d.serie.some(x => x.ventas > 0)" :opcion="opVentas"/><div v-else class="empty">Sin ventas en este periodo.</div></Tarjeta>
          <Tarjeta titulo="Cómo pagan los clientes" sub="Participación de cada medio de pago en las ventas" :columnas="colsMedios" :filas="medios">
            <div v-if="!medios.length" class="empty">Sin ventas en este periodo.</div>
            <template v-else>
              <div class="pila"><div v-for="m in medios" :key="m.medio" :style="{ flex: m.monto, background: m.color }" :title="m.medio + ': ' + peso(m.monto)"></div></div>
              <div class="pila-filas"><div v-for="m in medios" :key="m.medio"><i :style="{ background: m.color }"></i><span>{{ m.medio }}</span><b class="num">{{ peso(m.monto) }}</b><span class="muted num right">{{ porcentaje(m.pct) }}</span></div></div>
            </template>
          </Tarjeta>
        </div>

        <div class="dash-fila f12">
          <Tarjeta titulo="¿Cuándo se vende más?" sub="Tiquetes por día de la semana y hora: sirve para programar turnos" :columnas="colsCalor" :filas="filasCalor"><Grafico v-if="d.calor.length" :opcion="opCalor" alto="lg"/><div v-else class="empty">Sin ventas en este periodo.</div></Tarjeta>
          <Tarjeta :titulo="'Top 10 productos por ' + (metProd === 'ventas' ? 'ventas' : 'margen')" :sub="metProd === 'ventas' ? 'Lo que más dinero entra' : 'Lo que más utilidad deja'"
                   :columnas="metProd === 'ventas' ? colsProd : colsProdMargen" :filas="itemsProd">
            <div class="seg" style="align-self:flex-start;margin-bottom:6px"><button :class="{ on: metProd === 'ventas' }" @click="metProd = 'ventas'">Ventas</button><button :class="{ on: metProd === 'margen' }" @click="metProd = 'margen'">Margen</button></div>
            <div v-if="itemsProd.length" :style="altoBarras(itemsProd.length)"><Grafico :opcion="opProd" :style="{ height: '100%' }"/></div><div v-else class="empty">Sin ventas en este periodo.</div>
          </Tarjeta>
        </div>

        <div class="dash-fila f3">
          <Tarjeta titulo="Ventas por categoría" sub="Qué secciones sostienen el negocio" :columnas="colsCat" :filas="d.top_categorias">
            <div v-if="(d.top_categorias || []).length" :style="altoBarras(d.top_categorias.length)"><Grafico :opcion="opCat" :style="{ height: '100%' }"/></div><div v-else class="empty">Sin ventas en este periodo.</div>
          </Tarjeta>

          <div class="card stack">
            <div class="card-title" style="margin-bottom:0"><h3><Icono n="conteo"/> Conteos de inventario</h3><a href="#/conteos" class="small">Ver todos</a></div>
            <div class="alert info" v-if="d.conteos.en_curso"><Icono n="conteo"/><div class="grow">En curso: <b>{{ d.conteos.en_curso.nombre }}</b></div><a :href="'#/conteos/' + d.conteos.en_curso.id" class="bold">Abrir</a></div>
            <div v-for="r in d.conteos.recordatorios" :key="r.id" class="alert" :class="r.vencida ? 'danger' : ''">
              <Icono n="calendario"/><div class="grow"><b>{{ r.nombre }}</b><br><span class="small">{{ r.vencida ? 'Vencido hace ' + (-r.dias_restantes) + ' día(s)' : r.dias_restantes === 0 ? 'Es hoy' : 'En ' + r.dias_restantes + ' día(s)' }} · {{ fecha(r.proxima_fecha) }}</span></div>
              <button class="btn sm" @click="ir('#/conteos')">Iniciar</button></div>
            <div v-if="!d.conteos.recordatorios.length && !d.conteos.en_curso" class="muted small">No hay conteos próximos. Puede programarlos desde «Conteos».</div>
            <div v-if="d.conteos.ultimo" class="tile-list"><div><div class="grow"><div class="muted small">Último conteo aplicado</div><b>{{ d.conteos.ultimo.nombre }}</b><div class="xs muted">{{ fechaHora(d.conteos.ultimo.cerrado_en) }}</div></div>
              <div class="right"><div class="muted xs">Exactitud</div><b style="font-size:22px" :class="d.conteos.ultimo.exactitud_pct >= 95 ? 'ok' : d.conteos.ultimo.exactitud_pct >= 85 ? 'warn' : 'danger'">{{ porcentaje(d.conteos.ultimo.exactitud_pct) }}</b></div></div></div>
          </div>

          <div class="card stack">
            <div class="card-title" style="margin-bottom:0"><h3><Icono n="recibo"/> Últimos cierres de caja</h3><a href="#/turnos" class="small">Ver todos</a></div>
            <div class="tile-list" v-if="d.cierres.length"><div v-for="c in d.cierres" :key="c.id">
              <div class="grow"><b>{{ c.cajero }}</b><div class="xs muted">Turno {{ c.id }} · {{ fechaHora(c.cerrado_en) }}</div></div>
              <div class="right"><span class="chip" :class="estadoDif(c.diferencia_efectivo).c"><Icono :n="estadoDif(c.diferencia_efectivo).i"/>{{ estadoDif(c.diferencia_efectivo).t }}</span>
                <div class="xs num" :class="estadoDif(c.diferencia_efectivo).c" v-if="c.diferencia_efectivo">{{ peso(c.diferencia_efectivo) }}</div></div></div></div>
            <div v-else class="muted small">Todavía no hay turnos cerrados.</div>
          </div>
        </div>
      </div>
    </div>`,
};
