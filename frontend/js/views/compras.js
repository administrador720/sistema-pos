// Compras: entrada de mercancía (actualiza stock y costo promedio)
import { api, query } from '../api.js';
import { store, errorToast, toast, confirmar } from '../store.js';
import { peso, entero, decimal, fechaHora, fecha, isoHoy, beep, conUnidad } from '../util.js';

const { ref, reactive, computed, onMounted, nextTick } = Vue;

const NuevaCompra = {
  emits: ['cerrar', 'guardada'],
  setup(p, { emit }) {
    const f = reactive({ proveedor_id: null, numero_factura: '', nota: '' }), lineas = ref([]), guardando = ref(false), buscador = ref(null);
    const total = computed(() => lineas.value.reduce((s, l) => s + (l.cantidad || 0) * (l.costo || 0), 0));
    const unidades = computed(() => lineas.value.length);
    async function agregar(prod) {
      let completo = prod;
      if (prod.costo_promedio === undefined) { try { completo = await api.get('/api/productos/' + prod.id); } catch (e) { return errorToast(e); } }
      const ex = lineas.value.find(l => l.producto_id === prod.id);
      if (ex) { if (ex.unidad !== 'kg') ex.cantidad += 1; beep('ok'); return; }
      lineas.value.push({ producto_id: prod.id, nombre: prod.nombre, unidad: completo.unidad || 'u', cantidad: completo.unidad === 'kg' ? null : 1, costo: Math.round(completo.costo_promedio * 100) / 100, costo_actual: completo.costo_promedio,
        precio_actual: completo.precio_venta, stock: completo.stock_actual, nuevo_precio: null });
      beep('ok');
      nextTick(() => document.querySelector('.compra-lineas tbody tr:last-child input')?.select());
    }
    function variacion(l) { return l.costo_actual ? ((l.costo - l.costo_actual) / l.costo_actual) * 100 : null; }
    async function guardar() {
      if (!lineas.value.length) return toast('Agregue al menos un producto.', 'warn');
      if (lineas.value.some(l => !(l.cantidad > 0))) return toast('Indique la cantidad (o los kilos) de cada producto.', 'warn');
      const sinCosto = lineas.value.filter(l => !(l.costo > 0));
      if (sinCosto.length && !await confirmar('Productos sin costo', `${sinCosto.length} producto(s) tienen costo 0. ¿Guardar así?`, { textoOk: 'Guardar de todos modos' })) return;
      guardando.value = true;
      try {
        await api.post('/api/compras', { ...f, items: lineas.value.map(l => ({ producto_id: l.producto_id, cantidad: l.cantidad, costo_unitario: l.costo || 0, nuevo_precio: l.nuevo_precio || null })) });
        toast('Compra registrada. El inventario y los costos se actualizaron.', 'ok', 5000); emit('guardada');
      } catch (e) { errorToast(e); } finally { guardando.value = false; }
    }
    onMounted(() => nextTick(() => buscador.value?.focus()));
    return { f, lineas, guardando, total, unidades, buscador, store, agregar, variacion, guardar, peso, decimal, entero, conUnidad };
  },
  template: `
    <Modal titulo="Nueva compra / entrada de mercancía" ancho="xl" @cerrar="$emit('cerrar')">
      <div class="stack">
        <div class="grid" style="grid-template-columns:2fr 1fr 2fr">
          <div class="field"><label>Proveedor</label><select class="input" v-model="f.proveedor_id"><option :value="null">Sin proveedor</option><option v-for="c in store.cat.proveedores" :key="c.id" :value="c.id">{{ c.nombre }}</option></select></div>
          <div class="field"><label>Nº de factura</label><input class="input" v-model="f.numero_factura"></div>
          <div class="field"><label>Nota</label><input class="input" v-model="f.nota" placeholder="Opcional"></div>
        </div>
        <div class="field"><label>Agregar producto (escanee el código o busque por nombre)</label><BuscaProducto ref="buscador" @elegir="agregar"/></div>
        <div class="table-wrap compra-lineas" style="max-height:44vh">
          <table class="t compact" v-if="lineas.length"><thead><tr><th>Producto</th><th class="num" style="width:110px">Cantidad</th><th class="num" style="width:150px">Costo unitario (kg o und)</th><th class="num" style="width:150px">Nuevo precio (opcional)</th><th class="num" style="width:130px">Subtotal</th><th style="width:46px"></th></tr></thead>
            <tbody><tr v-for="(l, i) in lineas" :key="l.producto_id">
              <td><b>{{ l.nombre }}</b><div class="xs muted">Stock {{ conUnidad(l.stock, l.unidad) }} · costo actual {{ decimal(l.costo_actual, 0) }}{{ l.unidad === 'kg' ? ' /kg' : '' }} · precio {{ peso(l.precio_actual) }}{{ l.unidad === 'kg' ? ' /kg' : '' }}</div></td>
              <td class="num"><InputPeso v-if="l.unidad === 'kg'" v-model="l.cantidad" placeholder="kg"/><input v-else class="input sm num" type="number" min="1" v-model.number="l.cantidad" @focus="$event.target.select()"></td>
              <td class="num"><input class="input sm num" type="number" min="0" step="0.01" v-model.number="l.costo" @focus="$event.target.select()">
                <div class="xs" v-if="variacion(l) !== null && Math.abs(variacion(l)) >= 0.5" :class="variacion(l) > 0 ? 'danger' : 'ok'">{{ variacion(l) > 0 ? '▲' : '▼' }} {{ Math.abs(variacion(l)).toFixed(1) }} %</div></td>
              <td class="num"><InputDinero v-model="l.nuevo_precio" :placeholder="peso(l.precio_actual)" class="sm"/></td>
              <td class="num"><b>{{ peso((l.cantidad || 0) * (l.costo || 0)) }}</b></td>
              <td><button class="btn ghost icon sm" @click="lineas.splice(i, 1)"><Icono n="x"/></button></td></tr></tbody></table>
          <div v-else class="empty">Escanee o busque los productos que llegaron.</div>
        </div>
        <div class="row between"><span class="muted small">Digite el costo sin el IVA descontable. El costo promedio se recalcula con lo que ya había en bodega.</span>
          <div class="right"><div class="muted small">{{ unidades }} producto(s)</div><b class="num" style="font-size:24px">{{ peso(total) }}</b></div></div>
      </div>
      <template #pie><button class="btn" @click="$emit('cerrar')">Cancelar</button><button class="btn primary" :disabled="guardando || !lineas.length" @click="guardar"><Icono n="check"/> Registrar compra</button></template>
    </Modal>`,
};

const Detalle = {
  props: { id: Number },
  emits: ['cerrar'],
  setup(p) {
    const c = ref(null);
    onMounted(async () => { try { c.value = await api.get('/api/compras/' + p.id); } catch (e) { errorToast(e); } });
    return { c, peso, decimal, fechaHora, conUnidad };
  },
  template: `
    <Modal :titulo="c ? 'Compra #' + c.id + (c.numero_factura ? ' · factura ' + c.numero_factura : '') : 'Compra'" ancho="md" @cerrar="$emit('cerrar')">
      <div v-if="c" class="stack"><div class="muted">{{ fechaHora(c.fecha) }} · {{ c.proveedor || 'Sin proveedor' }}<span v-if="c.nota"> · {{ c.nota }}</span></div>
        <table class="t compact"><thead><tr><th>Producto</th><th class="num">Cantidad</th><th class="num">Costo</th><th class="num">Subtotal</th></tr></thead><tbody>
          <tr v-for="i in c.items" :key="i.producto_id"><td>{{ i.nombre }}</td><td class="num">{{ conUnidad(i.cantidad, i.unidad) }}</td><td class="num">{{ decimal(i.costo_unitario) }}</td><td class="num">{{ peso(i.subtotal) }}</td></tr></tbody>
          <tfoot><tr><td colspan="3">Total</td><td class="num">{{ peso(c.total) }}</td></tr></tfoot></table></div>
    </Modal>`,
};

export const Compras = {
  components: { NuevaCompra, Detalle },
  setup() {
    const filtro = reactive({ desde: isoHoy(-60), hasta: isoHoy(), proveedor_id: null }), lista = ref([]), cargando = ref(true), dlg = ref(null), verId = ref(null);
    async function cargar() { cargando.value = true; try { lista.value = await api.get('/api/compras' + query(filtro)); } catch (e) { errorToast(e); } cargando.value = false; }
    onMounted(cargar);
    const total = computed(() => lista.value.reduce((s, c) => s + c.total, 0));
    return { filtro, lista, cargando, dlg, verId, total, store, cargar, peso, fechaHora, hecho: () => { dlg.value = null; cargar(); } };
  },
  template: `
    <div class="page">
      <div class="page-head">
        <div class="row wrap"><div class="field"><label>Desde</label><input type="date" class="input" v-model="filtro.desde" @change="cargar"></div>
          <div class="field"><label>Hasta</label><input type="date" class="input" v-model="filtro.hasta" @change="cargar"></div>
          <div class="field"><label>Proveedor</label><select class="input" v-model="filtro.proveedor_id" @change="cargar"><option :value="null">Todos</option><option v-for="c in store.cat.proveedores" :key="c.id" :value="c.id">{{ c.nombre }}</option></select></div></div>
        <button class="btn primary lg" @click="dlg = 'nueva'"><Icono n="mas"/> Nueva compra</button>
      </div>
      <div class="card pad0"><div class="table-wrap" style="max-height:calc(100vh - 230px)"><table class="t"><thead><tr><th>#</th><th>Fecha</th><th>Proveedor</th><th>Factura</th><th class="num">Productos</th><th class="num">Total</th></tr></thead><tbody>
        <tr v-for="c in lista" :key="c.id" class="clickable" @click="verId = c.id; dlg = 'detalle'"><td class="muted">{{ c.id }}</td><td>{{ fechaHora(c.fecha) }}</td><td><b>{{ c.proveedor || '—' }}</b></td><td>{{ c.numero_factura || '—' }}</td><td class="num">{{ c.n_items }}</td><td class="num"><b>{{ peso(c.total) }}</b></td></tr>
        <tr v-if="!cargando && !lista.length"><td colspan="6"><div class="empty"><Icono n="camion" class="ico xl"/><div>No hay compras en este periodo.</div></div></td></tr></tbody>
        <tfoot v-if="lista.length"><tr><td colspan="5">Total comprado</td><td class="num">{{ peso(total) }}</td></tr></tfoot></table></div></div>
      <NuevaCompra v-if="dlg === 'nueva'" @cerrar="dlg = null" @guardada="hecho"/>
      <Detalle v-if="dlg === 'detalle'" :id="verId" @cerrar="dlg = null"/>
    </div>`,
};
