// Panel de ventas del dueño: lo esencial de un vistazo
import { get } from '../api.js';
import { avisoError } from '../componentes.js';
import { cantidadTxt, inicioMes, isoHoy, miles, peso } from '../util.js';

const { ref, computed, onMounted, watch } = Vue;

export const Panel = {
  setup() {
    const periodo = ref('hoy'), d = ref(null), error = ref('');
    const rango = () => periodo.value === 'hoy' ? [isoHoy(), isoHoy()] : periodo.value === '7d' ? [isoHoy(-6), isoHoy()] : [inicioMes(), isoHoy()];
    async function cargar() {
      error.value = '';
      try { const [a, b] = rango(); d.value = await get(`/api/dashboard?desde=${a}&hasta=${b}`); } catch (e) { error.value = e.message; d.value = null; avisoError(e); }
    }
    watch(periodo, cargar); onMounted(cargar);
    const maxSerie = computed(() => Math.max(1, ...(d.value?.serie || []).map(s => s.ventas)));
    const totalMedios = computed(() => (d.value?.medios || []).reduce((s, m) => s + m.monto, 0) || 1);
    const variacion = v => (v === null || v === undefined ? '' : (v > 0 ? '▲ ' : v < 0 ? '▼ ' : '') + String(Math.abs(v)).replace('.', ',') + ' %');
    return { periodo, d, error, maxSerie, totalMedios, variacion, peso, miles, cantidadTxt };
  },
  template: `
    <Pantalla titulo="Panel de ventas">
      <div class="seg"><button :class="{ on: periodo === 'hoy' }" @click="periodo = 'hoy'">Hoy</button><button :class="{ on: periodo === '7d' }" @click="periodo = '7d'">7 días</button><button :class="{ on: periodo === 'mes' }" @click="periodo = 'mes'">Este mes</button></div>
      <div class="aviso error" v-if="error">{{ error }}</div>
      <template v-if="d">
        <div class="kpis">
          <div class="kpi"><span>Ventas</span><b class="num">{{ peso(d.kpis.ventas) }}</b><small :class="d.kpis.ventas_var > 0 ? 'ok' : d.kpis.ventas_var < 0 ? 'danger' : 'muted'">{{ variacion(d.kpis.ventas_var) }}</small></div>
          <div class="kpi"><span>Tiquetes</span><b class="num">{{ miles(d.kpis.transacciones) }}</b><small :class="d.kpis.transacciones_var > 0 ? 'ok' : d.kpis.transacciones_var < 0 ? 'danger' : 'muted'">{{ variacion(d.kpis.transacciones_var) }}</small></div>
          <div class="kpi"><span>Ticket promedio</span><b class="num">{{ peso(d.kpis.ticket_promedio) }}</b></div>
          <div class="kpi"><span>Margen</span><b class="num">{{ peso(d.kpis.margen) }}</b><small class="muted">{{ d.kpis.margen_pct === null ? '' : String(d.kpis.margen_pct).replace('.', ',') + ' %' }}</small></div>
        </div>
        <div class="tarjeta" v-if="d.serie.length > 1"><h3>Ventas por día</h3>
          <div class="barras"><i v-for="s in d.serie" :key="s.fecha" :style="{ height: Math.max(2, s.ventas * 100 / maxSerie) + '%' }" :title="s.fecha + ': ' + peso(s.ventas)"></i></div>
          <div class="fila entre xs muted"><span>{{ d.serie[0].fecha.slice(5) }}</span><span>{{ d.serie[d.serie.length - 1].fecha.slice(5) }}</span></div></div>
        <div class="tarjeta" v-if="d.medios.length"><h3>Cómo pagaron</h3>
          <div v-for="m in d.medios" :key="m.medio" class="pila" style="gap:4px"><div class="fila entre small"><span>{{ m.medio }}</span><b class="num">{{ peso(m.monto) }}</b></div>
            <div class="medidor"><i :style="{ width: Math.round(m.monto * 100 / totalMedios) + '%' }"></i></div></div></div>
        <div class="tarjeta" v-if="d.top_ventas.length"><h3>Lo más vendido</h3>
          <div class="fila entre small" v-for="p in d.top_ventas.slice(0, 5)" :key="p.nombre"><span class="crece">{{ p.nombre }}</span><span class="muted num">{{ cantidadTxt(p.unidades) }}</span><b class="num">{{ peso(p.ventas) }}</b></div></div>
        <div class="tarjeta"><h3>Inventario</h3>
          <div class="fila envuelve"><span class="chip" :class="d.inventario.agotados ? 'danger' : 'ok'">{{ d.inventario.agotados }} agotados</span><span class="chip" :class="d.inventario.bajo_minimo ? 'warn' : 'ok'">{{ d.inventario.bajo_minimo }} bajo el mínimo</span>
            <span class="chip danger" v-if="d.inventario.negativos">{{ d.inventario.negativos }} con stock negativo</span></div>
          <div class="fila entre small"><span class="muted">Valor del inventario (a costo)</span><b class="num">{{ peso(d.inventario.valor) }}</b></div>
          <div class="small" v-if="d.conteos.en_curso">Conteo en curso: <b>{{ d.conteos.en_curso.nombre }}</b></div></div>
        <div class="tarjeta" v-if="d.cierres.length"><h3>Últimos cierres de caja</h3>
          <div class="fila entre small" v-for="c in d.cierres.slice(0, 3)" :key="c.id"><span>Turno {{ c.id }} · {{ c.cajero }}</span>
            <b class="num" :class="c.diferencia_efectivo < 0 ? 'danger' : c.diferencia_efectivo > 0 ? 'warn' : 'ok'">{{ c.diferencia_efectivo === 0 ? 'Cuadró' : peso(c.diferencia_efectivo) }}</b></div></div>
      </template>
      <div class="vacio" v-else-if="!error">Cargando…</div>
    </Pantalla>`,
};
