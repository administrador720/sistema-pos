// Contar inventario con la cámara (captura ciega: no se muestra cuánto debería haber)
import { del, get, post } from '../api.js';
import { aviso, avisoError } from '../componentes.js';
import { cantidadTxt, conUnidad, fechaHora, pitido } from '../util.js';

const { ref, onMounted, watch } = Vue;
const pref = (k, d) => { try { const v = localStorage.getItem(k); return v === null ? d : v === '1'; } catch (e) { return d; } };

export const Conteo = {
  setup() {
    const conteos = ref(null), sel = ref(null), prog = ref(null), caps = ref([]), actual = ref(null), cant = ref(1), directo = ref(pref('posm_conteo_directo', false)), buscador = ref(null);
    watch(directo, v => { try { localStorage.setItem('posm_conteo_directo', v ? '1' : '0'); } catch (e) { /* */ } });

    async function cargarLista() {
      try {
        conteos.value = (await get('/api/conteos')).filter(c => c.estado === 'en_conteo');
        if (conteos.value.length === 1) await elegirConteo(conteos.value[0]);
      } catch (e) { conteos.value = []; avisoError(e); }
    }
    async function refrescar() {
      caps.value = (await get(`/api/conteos/${sel.value.id}/capturas`, { silencioso: true })).slice(0, 15);
      prog.value = (await get('/api/conteos/' + sel.value.id, { silencioso: true })).progreso;
    }
    async function elegirConteo(c) { sel.value = c; try { await refrescar(); } catch (e) { avisoError(e); } }
    async function registrar(p, cantidad) {
      // un código de paca vale varias unidades: se manda el código para que el servidor haga la multiplicación
      const cuerpo = p._codigo ? { codigo: p._codigo, cantidad } : { producto_id: p.id, cantidad };
      try {
        const r = await post(`/api/conteos/${sel.value.id}/capturas`, cuerpo);
        pitido('ok'); aviso(`${p.nombre}: +${cantidadTxt(r.cantidad)}`, 'ok', 1700);
        actual.value = null; await refrescar();
      } catch (e) { avisoError(e); }
    }
    function alElegir(p) {
      if (directo.value && p.unidad !== 'kg') return registrar(p, 1);      // 1 por escaneo, sin preguntar
      actual.value = p; cant.value = p.unidad === 'kg' ? null : 1;
    }
    const confirmar = () => { if (actual.value && cant.value !== null && cant.value >= 0) registrar(actual.value, cant.value); };
    async function deshacer(c) { try { await del(`/api/conteos/${sel.value.id}/capturas/${c.id}`); aviso('Captura eliminada.', 'ok', 1800); await refrescar(); } catch (e) { avisoError(e); } }
    onMounted(cargarLista);
    return { conteos, sel, prog, caps, actual, cant, directo, buscador, elegirConteo, alElegir, confirmar, deshacer, cargarLista, cantidadTxt, conUnidad, fechaHora };
  },
  template: `
    <Pantalla titulo="Contar inventario">
      <div class="vacio" v-if="conteos === null">Buscando conteos…</div>
      <div class="pila" v-else-if="!sel">
        <div class="aviso info" v-if="!conteos.length">No hay un conteo en curso. En el computador entre a <b>Conteos → Nuevo conteo</b>, elija qué contar y presione <b>Iniciar</b>. Luego vuelva aquí.</div>
        <template v-else><h3>¿Qué conteo va a hacer?</h3>
          <div class="lista"><button class="item" v-for="c in conteos" :key="c.id" @click="elegirConteo(c)"><span><b>{{ c.nombre }}</b><br><span class="xs muted">Iniciado {{ fechaHora(c.iniciado_en) }}</span></span><Icono n="check"/></button></div></template>
        <button class="btn" @click="cargarLista">Buscar de nuevo</button>
      </div>
      <template v-else>
        <div class="tarjeta">
          <div class="fila entre"><b>{{ sel.nombre }}</b><span class="chip acento" v-if="prog">{{ prog.contados }} / {{ prog.productos }}</span></div>
          <div class="medidor" v-if="prog && prog.productos"><i :style="{ width: Math.round(prog.contados * 100 / prog.productos) + '%' }"></i></div>
          <label class="fila small"><input type="checkbox" v-model="directo" style="width:20px;height:20px"> Sumar 1 al escanear (sin preguntar la cantidad)</label>
        </div>
        <BuscarProducto ref="buscador" :continuo="directo" @elegir="alElegir" placeholder="Código o nombre"/>
        <div class="aviso info small">El sistema no muestra cuántas unidades debería haber: así el conteo es honesto. Si cuenta el mismo producto en otro lugar, las cantidades se suman.</div>
        <h3 v-if="caps.length">Últimas capturas</h3>
        <div class="lista" v-if="caps.length"><div class="item" v-for="c in caps" :key="c.id"><span class="crece"><b>{{ c.nombre }}</b><br><span class="xs muted">{{ fechaHora(c.capturado_en) }}</span></span>
          <b class="num">+{{ cantidadTxt(c.cantidad) }}</b><button class="btn chico icono" @click="deshacer(c)" aria-label="Deshacer"><Icono n="deshacer"/></button></div></div>
      </template>

      <Hoja v-if="actual" @cerrar="actual = null">
        <h2>{{ actual.nombre }}</h2>
        <p class="muted small">{{ actual.unidad === 'kg' ? 'Escriba los kilos que contó (use coma para los decimales).' : '¿Cuántas unidades contó?' }}</p>
        <div class="fila" style="justify-content:center"><Paso v-model="cant" :decimal="actual.unidad === 'kg'" :min="0" :paso="actual.unidad === 'kg' ? 0.5 : 1" @enter="confirmar"/></div>
        <div class="fila"><button class="btn crece" @click="actual = null">Cancelar</button><button class="btn primario crece" :disabled="cant === null" @click="confirmar"><Icono n="check"/> Registrar</button></div>
      </Hoja>
    </Pantalla>`,
};
