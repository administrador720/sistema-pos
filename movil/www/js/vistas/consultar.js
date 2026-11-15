// Consultar precio y existencias de un producto
import { get } from '../api.js';
import { avisoError } from '../componentes.js';
import { cantidadTxt, conUnidad, peso } from '../util.js';

const { ref } = Vue;

export const Consultar = {
  setup() {
    const prod = ref(null);
    async function elegir(p) { try { prod.value = await get('/api/productos/' + p.id); } catch (e) { avisoError(e); } }
    const bajo = p => p.stock_actual <= p.stock_minimo;
    return { prod, elegir, bajo, peso, conUnidad, cantidadTxt };
  },
  template: `
    <Pantalla titulo="Consultar">
      <BuscarProducto @elegir="elegir" placeholder="Código o nombre"/>
      <div class="tarjeta" v-if="prod">
        <div class="fila entre envuelve"><h2 class="crece">{{ prod.nombre }}</h2><span class="chip" v-if="prod.categoria">{{ prod.categoria }}</span></div>
        <div class="total num">{{ peso(prod.precio_venta) }}<span class="muted small" v-if="prod.unidad === 'kg'"> por kilo</span></div>
        <div class="fila entre"><span class="muted">Existencias</span><b class="num" :class="prod.stock_actual < 0 ? 'danger' : bajo(prod) ? 'warn' : 'ok'">{{ conUnidad(prod.stock_actual, prod.unidad) }}</b></div>
        <div class="fila entre" v-if="prod.stock_minimo"><span class="muted">Stock mínimo</span><span class="num">{{ conUnidad(prod.stock_minimo, prod.unidad) }}</span></div>
        <div class="fila entre" v-if="prod.ubicacion"><span class="muted">Ubicación</span><span>{{ prod.ubicacion }}</span></div>
        <div class="fila entre" v-if="prod.costo_promedio !== undefined"><span class="muted">Costo promedio</span><span class="num">{{ peso(prod.costo_promedio) }}</span></div>
        <div class="fila entre" v-if="prod.margen_pct !== null && prod.margen_pct !== undefined"><span class="muted">Margen</span><b class="num" :class="prod.margen_pct < 0 ? 'danger' : ''">{{ String(prod.margen_pct).replace('.', ',') }} %</b></div>
        <div class="fila entre" v-if="prod.proveedor"><span class="muted">Proveedor</span><span>{{ prod.proveedor }}</span></div>
        <div class="fila envuelve"><span class="chip acento" v-if="prod.codigo_interno">Código corto {{ prod.codigo_interno }}</span>
          <span class="chip" v-for="c in prod.codigos" :key="c.codigo">{{ c.codigo }}<b v-if="c.unidades > 1"> × {{ c.unidades }}</b></span></div>
        <span class="chip danger" v-if="!prod.activo" style="align-self:flex-start">Producto inactivo</span>
      </div>
      <div class="vacio" v-else>Escanee un producto para ver su precio y cuántas unidades hay.</div>
    </Pantalla>`,
};
