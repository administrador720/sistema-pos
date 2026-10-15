// Cierres de caja: historial de turnos con su arqueo
import { api } from '../api.js';
import { errorToast, verPdf } from '../store.js';
import { peso, fechaHora, hora } from '../util.js';

const { ref, onMounted } = Vue;

const estado = d => d === null || d === undefined ? { t: 'Abierto', c: 'accent' } : d === 0 ? { t: 'Cuadra', c: 'ok' } : d < 0 ? { t: 'Faltante', c: 'danger' } : { t: 'Sobrante', c: 'warn' };

const Detalle = {
  props: { id: Number },
  emits: ['cerrar'],
  setup(p) {
    const z = ref(null);
    onMounted(async () => { try { z.value = await api.get(`/api/turnos/${p.id}/reporte`); } catch (e) { errorToast(e); } });
    return { z, peso, fechaHora, estado, pdf: () => verPdf('Cierre de turno ' + p.id, `/api/turnos/${p.id}/reporte?formato=pdf`) };
  },
  template: `
    <Modal :titulo="'Turno #' + id" ancho="lg" @cerrar="$emit('cerrar')">
      <div v-if="z" class="stack">
        <div class="muted">{{ z.caja }} · {{ z.turno.usuario }} · {{ fechaHora(z.turno.abierto_en) }} → {{ z.turno.cerrado_en ? fechaHora(z.turno.cerrado_en) : 'abierto' }}</div>
        <div class="grid c2" v-if="z.turno.estado === 'cerrado'">
          <div class="card soft stack sm"><div class="row between"><h3>Efectivo</h3><span class="chip" :class="estado(z.turno.diferencia_efectivo).c">{{ estado(z.turno.diferencia_efectivo).t }}</span></div>
            <div class="row between"><span class="muted">Esperado</span><b class="num">{{ peso(z.turno.efectivo_esperado) }}</b></div><div class="row between"><span class="muted">Contado</span><b class="num">{{ peso(z.turno.efectivo_contado) }}</b></div>
            <div class="row between"><b>Diferencia</b><b class="num" :class="estado(z.turno.diferencia_efectivo).c">{{ peso(z.turno.diferencia_efectivo) }}</b></div></div>
          <div class="card soft stack sm"><div class="row between"><h3>Banco</h3><span class="chip" :class="estado(z.turno.diferencia_banco).c">{{ estado(z.turno.diferencia_banco).t }}</span></div>
            <div class="row between"><span class="muted">Esperado</span><b class="num">{{ peso(z.turno.banco_esperado) }}</b></div><div class="row between"><span class="muted">Reportado</span><b class="num">{{ peso(z.turno.banco_reportado) }}</b></div>
            <div class="row between"><b>Diferencia</b><b class="num" :class="estado(z.turno.diferencia_banco).c">{{ peso(z.turno.diferencia_banco) }}</b></div></div>
        </div>
        <table class="t compact"><thead><tr><th>Medio de pago</th><th class="num">Pagos</th><th class="num">Monto</th></tr></thead><tbody>
          <tr v-for="m in z.totales.por_medio" :key="m.medio"><td>{{ m.medio }}</td><td class="num">{{ m.pagos }}</td><td class="num">{{ peso(m.monto) }}</td></tr></tbody>
          <tfoot><tr><td>Ventas ({{ z.totales.ventas_n }} tiquetes)</td><td></td><td class="num">{{ peso(z.totales.ventas_total) }}</td></tr></tfoot></table>
        <div class="grid c4 small"><div><span class="muted">Base</span><br><b class="num">{{ peso(z.totales.base) }}</b></div><div><span class="muted">Ingresos</span><br><b class="num">{{ peso(z.totales.ingresos) }}</b></div>
          <div><span class="muted">Retiros</span><br><b class="num">{{ peso(z.totales.retiros) }}</b></div><div><span class="muted">Devoluciones</span><br><b class="num">{{ peso(z.totales.devoluciones_efectivo + z.totales.devoluciones_banco) }}</b></div>
          <div><span class="muted">Anulaciones</span><br><b class="num">{{ z.totales.anuladas_n }}</b></div><div><span class="muted">Descuentos</span><br><b class="num">{{ peso(z.totales.descuentos) }}</b></div></div>
        <div v-if="z.movimientos.length"><h3 style="margin-bottom:6px">Movimientos de efectivo</h3><table class="t compact"><tbody>
          <tr v-for="m in z.movimientos" :key="m.id"><td>{{ fechaHora(m.fecha) }}</td><td><span class="chip" :class="m.tipo === 'retiro' ? 'warn' : 'ok'">{{ m.tipo }}</span></td><td>{{ m.motivo }}</td><td class="muted small">{{ m.usuario }}{{ m.autorizado_por ? ' · autorizó ' + m.autorizado_por : '' }}</td><td class="num">{{ peso(m.monto) }}</td></tr></tbody></table></div>
        <p class="muted small" v-if="z.turno.observaciones">Observaciones: {{ z.turno.observaciones }}</p>
      </div>
      <template #pie><button class="btn" @click="pdf"><Icono n="impresora"/> Ver / imprimir PDF</button><button class="btn primary" @click="$emit('cerrar')">Cerrar</button></template>
    </Modal>`,
};

export const Turnos = {
  components: { Detalle },
  setup() {
    const lista = ref([]), cargando = ref(true), ver = ref(null);
    onMounted(async () => { try { lista.value = await api.get('/api/turnos?limite=150'); } catch (e) { errorToast(e); } cargando.value = false; });
    return { lista, cargando, ver, peso, fechaHora, estado };
  },
  template: `
    <div class="page">
      <div class="card pad0"><div class="table-wrap" style="max-height:calc(100vh - 150px)"><table class="t"><thead><tr><th>Turno</th><th>Cajero</th><th>Apertura</th><th>Cierre</th><th class="num">Base</th><th class="num">Dif. efectivo</th><th class="num">Dif. banco</th><th>Estado</th></tr></thead><tbody>
        <tr v-for="t in lista" :key="t.id" class="clickable" @click="ver = t.id"><td><b>#{{ t.id }}</b></td><td>{{ t.usuario }}</td><td>{{ fechaHora(t.abierto_en) }}</td><td>{{ t.cerrado_en ? fechaHora(t.cerrado_en) : '—' }}</td>
          <td class="num">{{ peso(t.base_efectivo) }}</td>
          <td class="num"><b :class="estado(t.diferencia_efectivo).c">{{ t.diferencia_efectivo === null ? '' : peso(t.diferencia_efectivo) }}</b></td>
          <td class="num"><b :class="estado(t.diferencia_banco).c">{{ t.diferencia_banco === null ? '' : peso(t.diferencia_banco) }}</b></td>
          <td><span class="chip" :class="estado(t.diferencia_efectivo).c">{{ t.estado === 'abierto' ? 'Abierto' : estado(t.diferencia_efectivo).t }}</span></td></tr>
        <tr v-if="!cargando && !lista.length"><td colspan="8"><div class="empty"><Icono n="recibo" class="ico xl"/><div>Todavía no hay turnos.</div></div></td></tr></tbody></table></div></div>
      <Detalle v-if="ver" :id="ver" @cerrar="ver = null"/>
    </div>`,
};
