// Vender y cobrar desde el celular (efectivo o banco)
import { get, post } from '../api.js';
import { aviso, avisoError } from '../componentes.js';
import { aNumero, bruta, conUnidad, kilos, miles, peso, pitido, valorLinea } from '../util.js';

const { ref, computed, onMounted } = Vue;
const BILLETES = [2000, 5000, 10000, 20000, 50000, 100000];

export const Venta = {
  setup() {
    const items = ref([]), turno = ref(undefined), medios = ref([]), buscador = ref(null);
    const pesar = ref(null), modo = ref('kilos'), kg = ref(null), valor = ref(null);          // ventana de peso
    const cobro = ref(false), tipo = ref('efectivo'), recibido = ref(null), medioId = ref(null), referencia = ref(''), enviando = ref(false), listo = ref(null);

    onMounted(async () => {
      try { turno.value = (await get('/api/turnos/actual', { silencioso: true })).turno; medios.value = (await get('/api/catalogos')).medios_pago.filter(m => m.activo); } catch (e) { turno.value = null; avisoError(e); }
    });
    const bancos = computed(() => medios.value.filter(m => m.tipo === 'banco'));
    const efectivo = computed(() => medios.value.find(m => m.tipo === 'efectivo'));
    const total = computed(() => items.value.reduce((s, i) => s + bruta(i), 0));
    const artic = computed(() => items.value.reduce((s, i) => s + (i.unidad === 'kg' ? 1 : i.cantidad), 0));
    const devuelta = computed(() => Math.max(0, (recibido.value ?? total.value) - total.value));
    const falta = computed(() => Math.max(0, total.value - (recibido.value ?? total.value)));
    const medio = computed(() => bancos.value.find(m => m.id === medioId.value));
    const puedeCobrar = computed(() => !enviando.value && total.value > 0 && (tipo.value === 'efectivo' ? (recibido.value ?? total.value) >= total.value
      : !!medio.value && (!medio.value.requiere_referencia || referencia.value.trim())));

    function agregar(p) {
      if (p.unidad === 'kg') { pesar.value = p; modo.value = 'kilos'; kg.value = null; valor.value = null; return; }
      const por = p.unidades_por_codigo || 1;
      const ex = items.value.find(i => i.producto_id === p.id && i.unidad !== 'kg');
      if (ex) ex.cantidad += por;
      else items.value.push({ producto_id: p.id, nombre: p.nombre, precio: p.precio_venta, unidad: 'u', cantidad: por });
      pitido('ok');
    }
    const cantPeso = computed(() => modo.value === 'kilos' ? (kg.value || 0) : (valor.value && pesar.value?.precio_venta ? Math.round(valor.value / pesar.value.precio_venta * 1000) / 1000 : 0));
    const subPeso = computed(() => modo.value === 'valor' ? (valor.value || 0) : valorLinea(pesar.value?.precio_venta || 0, cantPeso.value));
    const pesoValido = computed(() => (pesar.value?.precio_venta || 0) > 0 && cantPeso.value >= 0.001 && subPeso.value > 0);
    function agregarPeso() {
      if (!pesoValido.value) return;
      const p = pesar.value;
      items.value.push({ producto_id: p.id, nombre: p.nombre, precio: p.precio_venta, unidad: 'kg', cantidad: cantPeso.value, valor: modo.value === 'valor' ? valor.value : null });
      pesar.value = null; pitido('ok');
    }
    function mas(i, d) { const it = items.value[i]; it.cantidad = Math.max(1, it.cantidad + d); }
    function abrirCobro() { tipo.value = 'efectivo'; recibido.value = null; referencia.value = ''; medioId.value = bancos.value[0]?.id ?? null; cobro.value = true; }
    const sugeridos = computed(() => BILLETES.filter(b => b > total.value).slice(0, 3));

    async function cobrar() {
      if (!puedeCobrar.value) return;
      enviando.value = true;
      try {
        const pagos = tipo.value === 'efectivo'
          ? [{ medio_pago_id: efectivo.value.id, monto: total.value, recibido: recibido.value ?? total.value }]
          : [{ medio_pago_id: medioId.value, monto: total.value, referencia: referencia.value.trim() || null }];
        const v = await post('/api/ventas', { items: items.value.map(i => (i.valor ? { producto_id: i.producto_id, valor: i.valor } : { producto_id: i.producto_id, cantidad: i.cantidad })), pagos });
        pitido('cobro'); listo.value = { numero: v.numero, total: v.total, devuelta: v.pagos.reduce((s, p) => s + (p.devuelta || 0), 0) };
        items.value = []; cobro.value = false;
      } catch (e) { avisoError(e); if (e.codigo === 'SIN_TURNO') turno.value = null; } finally { enviando.value = false; }
    }
    return { items, turno, buscador, pesar, modo, kg, valor, cobro, tipo, recibido, medioId, referencia, enviando, listo, bancos, total, artic, devuelta, falta, medio, puedeCobrar,
      agregar, cantPeso, subPeso, pesoValido, agregarPeso, mas, abrirCobro, sugeridos, cobrar, peso, kilos, miles, aNumero, bruta, conUnidad };
  },
  template: `
    <Pantalla titulo="Vender">
      <div class="aviso" v-if="turno === null"><b>La caja está cerrada.</b> Ábrala en el computador (indicando la base) para poder vender.</div>
      <div class="tarjeta center" v-if="listo">
        <div class="chip ok" style="align-self:center"><Icono n="check"/> Venta registrada</div>
        <div class="muted">{{ listo.numero }}</div><div class="total num">{{ peso(listo.total) }}</div>
        <div class="aviso ok" v-if="listo.devuelta > 0">Entregue de devuelta <b>{{ peso(listo.devuelta) }}</b></div>
        <button class="btn primario grande bloque" @click="listo = null">Nueva venta</button>
      </div>
      <template v-else>
        <BuscarProducto ref="buscador" :continuo="true" @elegir="agregar" placeholder="Código o nombre"/>
        <div class="lista" v-if="items.length">
          <div class="linea" v-for="(it, i) in items" :key="i + '-' + it.producto_id">
            <div class="fila entre"><b class="crece">{{ it.nombre }}</b><b class="num">{{ peso(bruta(it)) }}</b></div>
            <div class="fila entre">
              <div class="fila" v-if="it.unidad === 'kg'"><b>{{ kilos(it.cantidad) }}</b><span class="xs muted">× {{ peso(it.precio) }}/kg{{ it.valor ? ' · por valor' : '' }}</span></div>
              <div class="paso" v-else><button @click="mas(i, -1)">−</button><input :value="it.cantidad" readonly><button @click="mas(i, 1)">+</button></div>
              <button class="btn chico icono" @click="items.splice(i, 1)" aria-label="Quitar"><Icono n="x"/></button>
            </div>
          </div>
        </div>
        <div class="vacio" v-else>Escanee los productos para armar la venta.</div>
      </template>

      <template #pie v-if="!listo">
        <div class="crece"><div class="xs muted">{{ artic }} artículo(s)</div><div class="total num">{{ peso(total) }}</div></div>
        <button class="btn primario grande" :disabled="!items.length || turno === null || turno === undefined" @click="abrirCobro">Cobrar</button>
      </template>

      <Hoja v-if="pesar" @cerrar="pesar = null">
        <h2>{{ pesar.nombre }}</h2><div class="muted small">Precio por kilo: <b>{{ peso(pesar.precio_venta) }}</b></div>
        <div class="seg"><button :class="{ on: modo === 'kilos' }" @click="modo = 'kilos'">Peso en kilos</button><button :class="{ on: modo === 'valor' }" @click="modo = 'valor'">Valor en pesos</button></div>
        <div class="fila" style="justify-content:center" v-if="modo === 'kilos'"><Paso v-model="kg" :decimal="true" :paso="0.25" @enter="agregarPeso"/></div>
        <input v-else class="input grande num" inputmode="numeric" placeholder="$ 0" :value="valor ? miles(valor) : ''" @input="valor = aNumero($event.target.value.replace(/\\D/g, ''))">
        <div class="tarjeta center" style="background:var(--accent-soft);border:none"><div class="small">{{ modo === 'kilos' ? 'Valor a cobrar' : 'Debe pesar aproximadamente' }}</div>
          <div class="total num">{{ modo === 'kilos' ? peso(subPeso) : kilos(cantPeso) }}</div></div>
        <div class="fila"><button class="btn crece" @click="pesar = null">Cancelar</button><button class="btn primario crece" :disabled="!pesoValido" @click="agregarPeso"><Icono n="check"/> Agregar</button></div>
      </Hoja>

      <Hoja v-if="cobro" @cerrar="cobro = false">
        <div class="center"><div class="muted small">Total a pagar</div><div class="total num" style="font-size:40px">{{ peso(total) }}</div></div>
        <div class="seg"><button :class="{ on: tipo === 'efectivo' }" @click="tipo = 'efectivo'">Efectivo</button><button :class="{ on: tipo === 'banco' }" @click="tipo = 'banco'" :disabled="!bancos.length">Banco</button></div>
        <template v-if="tipo === 'efectivo'">
          <label class="campo">Efectivo recibido<input class="input grande num" inputmode="numeric" :placeholder="miles(total)" :value="recibido ? miles(recibido) : ''" @input="recibido = aNumero($event.target.value.replace(/\\D/g, ''))" @keydown.enter="cobrar"></label>
          <div class="fila envuelve"><button class="btn chico" @click="recibido = total">Exacto</button><button class="btn chico" v-for="b in sugeridos" :key="b" @click="recibido = b">{{ peso(b) }}</button></div>
          <div class="aviso" :class="falta > 0 ? 'error' : 'ok'" style="text-align:center;font-size:20px"><b>{{ falta > 0 ? 'Falta ' + peso(falta) : 'Devuelta ' + peso(devuelta) }}</b></div>
        </template>
        <template v-else>
          <label class="campo">Medio de pago<select class="input" v-model="medioId"><option v-for="b in bancos" :key="b.id" :value="b.id">{{ b.nombre }}</option></select></label>
          <label class="campo">Número de aprobación {{ medio && medio.requiere_referencia ? '' : '(opcional)' }}<input class="input" v-model="referencia" autocomplete="off"></label>
        </template>
        <div class="fila"><button class="btn crece" @click="cobro = false" :disabled="enviando">Volver</button><button class="btn primario crece grande" :disabled="!puedeCobrar" @click="cobrar"><Icono n="check"/> {{ enviando ? 'Registrando…' : 'Confirmar' }}</button></div>
      </Hoja>
    </Pantalla>`,
};
