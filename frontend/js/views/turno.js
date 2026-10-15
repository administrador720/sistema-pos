// Apertura de caja (base) y cierre de caja (arqueo ciego)
import { api } from '../api.js';
import { store, esAdmin, errorToast, toast, refrescarTurno, confirmar, verPdf, cerrarSesionLocal } from '../store.js';
import { peso, miles, hora, fechaHora } from '../util.js';

const { ref, reactive, computed, onMounted, nextTick, watch } = Vue;

// Contador de billetes y monedas por denominación
export const ContadorDenominaciones = {
  props: { modelValue: { type: Object, required: true } },
  emits: ['update:modelValue'],
  setup(p, { emit }) {
    const lista = computed(() => store.config.denominaciones_lista || [50000, 20000, 10000, 5000, 2000, 1000, 500, 200, 100, 50]);
    const total = computed(() => lista.value.reduce((s, d) => s + d * (p.modelValue[d] || 0), 0));
    function poner(d, v) {
      const n = Math.max(0, parseInt(v, 10) || 0);
      emit('update:modelValue', { ...p.modelValue, [d]: n });
    }
    const cambiar = (d, delta) => poner(d, (p.modelValue[d] || 0) + delta);
    return { lista, total, poner, cambiar, peso, miles };
  },
  template: `
    <div class="stack">
      <div class="denoms">
        <div class="denom" v-for="d in lista" :key="d">
          <b>{{ d >= 1000 ? 'Billete' : 'Moneda' }} {{ miles(d) }}</b>
          <button class="btn sm icon ghost" @click="cambiar(d, -1)" tabindex="-1">−</button>
          <input type="number" min="0" :value="modelValue[d] || 0" @input="poner(d, $event.target.value)" @focus="$event.target.select()">
          <button class="btn sm icon ghost" @click="cambiar(d, 1)" tabindex="-1">+</button>
        </div>
      </div>
      <div class="row between" style="padding:12px 16px;background:var(--surface-2);border-radius:10px">
        <span class="muted">Total contado</span><b class="num" style="font-size:22px">{{ peso(total) }}</b>
      </div>
    </div>`,
};
export function aDenominaciones(obj) {
  return Object.entries(obj).filter(([, c]) => c > 0).map(([d, c]) => ({ denominacion: parseInt(d, 10), cantidad: c }));
}

export const Apertura = {
  components: { ContadorDenominaciones },
  setup() {
    const modo = ref('total'), base = ref(null), cont = ref({}), cargando = ref(false), campo = ref(null);
    const totalContado = computed(() => Object.entries(cont.value).reduce((s, [d, c]) => s + d * c, 0));
    const valor = computed(() => modo.value === 'total' ? base.value : totalContado.value);
    onMounted(async () => { await refrescarTurno(); nextTick(() => campo.value?.focus()); });
    async function abrir() {
      if (valor.value === null || valor.value === undefined) return toast('Digite la base con la que inicia el turno (puede ser 0).', 'warn');
      cargando.value = true;
      try {
        const cuerpo = modo.value === 'total' ? { base: valor.value } : { denominaciones: aDenominaciones(cont.value) };
        const r = await api.post('/api/turnos/abrir', cuerpo);
        await refrescarTurno();
        toast(`Caja abierta con base de ${peso(r.turno.base_efectivo)}.` + (r.cajon?.ok === false ? '\nNo se pudo abrir el cajón: ' + r.cajon.mensaje : ''), 'ok');
        location.hash = '#/caja';
      } catch (e) { errorToast(e); } finally { cargando.value = false; }
    }
    return { store, esAdmin, modo, base, cont, cargando, valor, abrir, campo, peso, hora, ir: h => { location.hash = h; } };
  },
  template: `
    <div class="page">
      <div style="max-width:720px;margin:0 auto" class="stack lg">
        <div v-if="store.turno" class="card stack">
          <div class="alert info"><Icono n="info"/><div>Ya hay un turno abierto: <b>#{{ store.turno.id }}</b> de {{ store.turno.usuario }}, desde las {{ hora(store.turno.abierto_en) }}, con base de {{ peso(store.turno.base_efectivo) }}.</div></div>
          <div class="row"><button class="btn primary" @click="ir('#/caja')">Ir a la caja</button><button class="btn" @click="ir('#/cierre')">Cerrar este turno</button></div>
        </div>
        <div v-else class="card stack lg">
          <div>
            <h1>Abrir caja</h1>
            <p class="muted" style="margin-top:6px">Indique con cuánto efectivo comienza el turno: es la <b>base</b> que se usa para dar devueltas. Al cerrar, el sistema compara el efectivo contado contra esta base más lo vendido.</p>
          </div>
          <div class="seg" style="align-self:flex-start">
            <button :class="{ on: modo === 'total' }" @click="modo = 'total'">Digitar el total</button>
            <button :class="{ on: modo === 'contar' }" @click="modo = 'contar'">Contar billetes y monedas</button>
          </div>
          <div v-if="modo === 'total'" class="field">
            <label>Base inicial en efectivo</label>
            <InputDinero ref="campo" v-model="base" grande placeholder="0" @enter="abrir"/>
          </div>
          <ContadorDenominaciones v-else v-model="cont"/>
          <button class="btn primary lg block" :disabled="cargando || valor === null" @click="abrir">
            <Icono n="caja"/> Abrir caja con {{ peso(valor || 0) }}
          </button>
          <p class="hint center">Se abrirá el cajón monedero para que verifique el dinero.</p>
        </div>
      </div>
    </div>`,
};

export const Cierre = {
  components: { ContadorDenominaciones },
  setup() {
    const cont = ref({}), banco = ref(null), obs = ref(''), cargando = ref(false), z = ref(null);
    const totalContado = computed(() => Object.entries(cont.value).reduce((s, [d, c]) => s + d * c, 0));
    onMounted(refrescarTurno);
    async function cerrar() {
      const ok = await confirmar('¿Cerrar la caja?', `Efectivo contado: ${peso(totalContado.value)}\nTotal del datáfono: ${peso(banco.value || 0)}\n\nUna vez cerrado el turno no se puede modificar.`,
        { textoOk: 'Sí, cerrar caja' });
      if (!ok) return;
      cargando.value = true;
      try {
        z.value = await api.post(`/api/turnos/${store.turno.id}/cerrar`, {
          denominaciones: aDenominaciones(cont.value), efectivo_contado: totalContado.value,
          banco_reportado: banco.value || 0, observaciones: obs.value });
        await refrescarTurno();
      } catch (e) { errorToast(e); } finally { cargando.value = false; }
    }
    const difClase = d => d === 0 ? 'ok' : d < 0 ? 'danger' : 'warn';
    const difTexto = d => d === 0 ? 'Cuadra' : d < 0 ? 'Faltante' : 'Sobrante';
    const pdf = () => verPdf(`Cierre de turno ${z.value.turno.id}`, `/api/turnos/${z.value.turno.id}/reporte?formato=pdf`);
    function salir() { api.post('/api/auth/logout').catch(() => {}); cerrarSesionLocal(); }
    return { store, esAdmin, cont, banco, obs, cargando, z, totalContado, cerrar, peso, hora, fechaHora, difClase, difTexto, pdf, salir, ir: h => { location.hash = h; } };
  },
  template: `
    <div class="page">
      <!-- Resultado del cierre -->
      <div v-if="z" style="max-width:860px;margin:0 auto" class="stack lg">
        <div class="card stack lg">
          <div class="row between wrap">
            <div><h1>Turno #{{ z.turno.id }} cerrado</h1><p class="muted">{{ z.turno.usuario }} · {{ fechaHora(z.turno.abierto_en) }} → {{ fechaHora(z.turno.cerrado_en) }}</p></div>
            <div class="row"><button class="btn" @click="pdf"><Icono n="impresora"/> Ver / imprimir</button><button class="btn primary" @click="ir('#/apertura')">Abrir nuevo turno</button></div>
          </div>
          <div class="grid c2">
            <div class="card soft stack sm">
              <div class="row between"><h3>Efectivo</h3><span class="chip" :class="difClase(z.turno.diferencia_efectivo)">{{ difTexto(z.turno.diferencia_efectivo) }}</span></div>
              <div class="row between"><span class="muted">Esperado (base + ventas + ingresos − retiros − devoluciones)</span><b class="num">{{ peso(z.turno.efectivo_esperado) }}</b></div>
              <div class="row between"><span class="muted">Contado</span><b class="num">{{ peso(z.turno.efectivo_contado) }}</b></div>
              <div class="row between" style="font-size:20px"><b>Diferencia</b><b class="num" :class="difClase(z.turno.diferencia_efectivo)">{{ peso(z.turno.diferencia_efectivo) }}</b></div>
            </div>
            <div class="card soft stack sm">
              <div class="row between"><h3>Banco / datáfono</h3><span class="chip" :class="difClase(z.turno.diferencia_banco)">{{ difTexto(z.turno.diferencia_banco) }}</span></div>
              <div class="row between"><span class="muted">Esperado según ventas</span><b class="num">{{ peso(z.turno.banco_esperado) }}</b></div>
              <div class="row between"><span class="muted">Reportado por el cierre</span><b class="num">{{ peso(z.turno.banco_reportado) }}</b></div>
              <div class="row between" style="font-size:20px"><b>Diferencia</b><b class="num" :class="difClase(z.turno.diferencia_banco)">{{ peso(z.turno.diferencia_banco) }}</b></div>
            </div>
          </div>
          <table class="t compact">
            <thead><tr><th>Medio de pago</th><th class="num">Pagos</th><th class="num">Monto</th></tr></thead>
            <tbody>
              <tr v-for="m in z.totales.por_medio" :key="m.medio"><td>{{ m.medio }}</td><td class="num">{{ m.pagos }}</td><td class="num">{{ peso(m.monto) }}</td></tr>
              <tr v-if="!z.totales.por_medio.length"><td colspan="3" class="muted center">Sin ventas en este turno</td></tr>
            </tbody>
            <tfoot><tr><td>Ventas totales ({{ z.totales.ventas_n }} tiquetes)</td><td></td><td class="num">{{ peso(z.totales.ventas_total) }}</td></tr></tfoot>
          </table>
          <div class="grid c4 small">
            <div><span class="muted">Base</span><br><b class="num">{{ peso(z.totales.base) }}</b></div>
            <div><span class="muted">Ingresos / retiros</span><br><b class="num">{{ peso(z.totales.ingresos) }} / {{ peso(z.totales.retiros) }}</b></div>
            <div><span class="muted">Devoluciones</span><br><b class="num">{{ z.totales.devoluciones_n }} · {{ peso(z.totales.devoluciones_efectivo + z.totales.devoluciones_banco) }}</b></div>
            <div><span class="muted">Anulaciones</span><br><b class="num">{{ z.totales.anuladas_n }}</b></div>
          </div>
          <button class="btn ghost" style="align-self:flex-start" @click="salir"><Icono n="salir"/> Cerrar sesión</button>
        </div>
      </div>

      <!-- Sin turno -->
      <div v-else-if="!store.turno" style="max-width:560px;margin:40px auto" class="card center stack">
        <Icono n="candado" class="ico xl" style="margin:0 auto;color:var(--faint)"/>
        <h2>No hay un turno abierto</h2><p class="muted">Abra la caja para empezar a vender.</p>
        <button class="btn primary lg" @click="ir('#/apertura')">Abrir caja</button>
      </div>

      <!-- Arqueo ciego -->
      <div v-else style="max-width:1000px;margin:0 auto" class="grid" :style="{ gridTemplateColumns: '1fr 320px' }">
        <div class="stack lg">
          <div class="card stack">
            <div><h1>Cerrar caja</h1><p class="muted" style="margin-top:6px">Cuente todo el efectivo de la caja. <b>El sistema no le muestra cuánto debería haber</b> hasta que confirme el cierre.</p></div>
            <div v-if="store.turno.usuario_id !== store.usuario.id" class="alert"><Icono n="alerta"/>Este turno es de <b>{{ store.turno.usuario }}</b>; está cerrándolo como {{ store.usuario.nombre }}.</div>
            <h3>1. Efectivo en la caja</h3>
            <ContadorDenominaciones v-model="cont"/>
          </div>
          <div class="card stack">
            <h3>2. Bancos y datáfono</h3>
            <div class="field" style="max-width:360px"><label>Total del cierre del datáfono + transferencias recibidas</label>
              <InputDinero v-model="banco" placeholder="0"/><span class="hint">Si no hubo pagos con banco, deje en 0.</span></div>
            <div class="field"><label>Observaciones (opcional)</label><textarea class="input" v-model="obs" placeholder="Ej.: se pagó al proveedor de pan $20.000"></textarea></div>
          </div>
        </div>
        <div class="stack">
          <div class="card stack sm" style="position:sticky;top:0">
            <h3>Resumen del turno</h3>
            <div class="row between"><span class="muted">Turno</span><b>#{{ store.turno.id }}</b></div>
            <div class="row between"><span class="muted">Abierto</span><b>{{ hora(store.turno.abierto_en) }}</b></div>
            <div class="row between"><span class="muted">Base inicial</span><b class="num">{{ peso(store.turno.base_efectivo) }}</b></div>
            <div class="row between"><span class="muted">Tiquetes</span><b class="num">{{ store.resumen?.ventas_n ?? 0 }}</b></div>
            <hr style="border:none;border-top:1px solid var(--border);width:100%">
            <div class="row between"><span class="muted">Efectivo contado</span><b class="num" style="font-size:20px">{{ peso(totalContado) }}</b></div>
            <button class="btn primary lg block" style="margin-top:8px" :disabled="cargando" @click="cerrar"><Icono n="candado"/> Cerrar caja</button>
          </div>
        </div>
      </div>
    </div>`,
};
