// Registrar una factura de compra (entrada de mercancía): actualiza existencias y costo promedio
import { get, post } from '../api.js';
import { aviso, avisoError } from '../componentes.js';
import { aNumero, conUnidad, miles, peso, pitido } from '../util.js';

const { ref, reactive, computed, onMounted } = Vue;
const txt = v => (v === null || v === undefined ? '' : String(v).replace('.', ','));

export const Compras = {
  setup() {
    const provs = ref([]), f = reactive({ proveedor_id: '', numero_factura: '' }), lineas = ref([]), guardando = ref(false), hecho = ref(null);
    onMounted(async () => { try { provs.value = (await get('/api/catalogos')).proveedores || []; } catch (e) { avisoError(e); } });

    async function agregar(p) {
      let c = p;
      try { c = await get('/api/productos/' + p.id); } catch (e) { return avisoError(e); }   // trae el costo y el precio actuales
      const ex = lineas.value.find(l => l.producto_id === c.id);
      const por = p.unidades_por_codigo || 1;   // un código de paca vale varias unidades
      if (ex) { if (ex.unidad !== 'kg') ex.cantidad += por; pitido('ok'); return; }
      lineas.value.push({ producto_id: c.id, nombre: c.nombre, unidad: c.unidad, cantidad: c.unidad === 'kg' ? null : por,
        costo: Math.round((c.costo_promedio || 0) * 100) / 100, costo_actual: c.costo_promedio || 0, precio_actual: c.precio_venta, nuevo_precio: null });
      pitido('ok');
    }
    const total = computed(() => lineas.value.reduce((s, l) => s + (l.cantidad || 0) * (l.costo || 0), 0));
    const variacion = l => (l.costo_actual ? ((l.costo - l.costo_actual) / l.costo_actual) * 100 : null);
    const listo = computed(() => lineas.value.length > 0 && lineas.value.every(l => l.cantidad > 0 && l.costo >= 0));
    async function guardar() {
      const sinCosto = lineas.value.filter(l => !(l.costo > 0));
      if (sinCosto.length && !confirm(`${sinCosto.length} producto(s) tienen costo 0. ¿Guardar así?`)) return;
      guardando.value = true;
      try {
        const r = await post('/api/compras', { proveedor_id: f.proveedor_id ? Number(f.proveedor_id) : null, numero_factura: f.numero_factura,
          items: lineas.value.map(l => ({ producto_id: l.producto_id, cantidad: l.cantidad, costo_unitario: l.costo || 0, nuevo_precio: l.nuevo_precio || null })) });
        hecho.value = { id: r.id, productos: lineas.value.length, total: total.value };
        lineas.value = []; f.numero_factura = '';
      } catch (e) { avisoError(e); } finally { guardando.value = false; }
    }
    return { provs, f, lineas, total, listo, guardando, hecho, agregar, variacion, guardar, aNumero, txt, peso, conUnidad, miles, aviso };
  },
  template: `
    <Pantalla titulo="Factura de compra">
      <div class="aviso ok" v-if="hecho"><b>Factura registrada.</b> {{ hecho.productos }} producto(s) por {{ peso(hecho.total) }}. Las existencias y los costos ya se actualizaron.<br>
        <button class="btn chico" style="margin-top:8px" @click="hecho = null">Registrar otra</button></div>
      <template v-else>
        <div class="tarjeta">
          <label class="campo">Proveedor<select class="input" v-model="f.proveedor_id"><option value="">Sin proveedor</option><option v-for="p in provs" :key="p.id" :value="p.id">{{ p.nombre }}</option></select></label>
          <label class="campo">Número de factura<input class="input" v-model="f.numero_factura" placeholder="Opcional" autocapitalize="characters"></label>
        </div>
        <BuscarProducto @elegir="agregar" placeholder="Producto que llegó"/>
        <div class="lista" v-if="lineas.length">
          <div class="linea" v-for="(l, i) in lineas" :key="l.producto_id">
            <div class="fila entre"><b class="crece">{{ l.nombre }}</b><button class="btn chico icono" @click="lineas.splice(i, 1)" aria-label="Quitar"><Icono n="x"/></button></div>
            <div class="xs muted">Costo actual {{ peso(l.costo_actual) }}{{ l.unidad === 'kg' ? ' /kg' : '' }} · precio {{ peso(l.precio_actual) }}{{ l.unidad === 'kg' ? ' /kg' : '' }}</div>
            <div class="fila envuelve">
              <Paso v-model="l.cantidad" :decimal="l.unidad === 'kg'" :paso="l.unidad === 'kg' ? 0.5 : 1"/>
              <label class="campo crece" style="min-width:110px">Costo {{ l.unidad === 'kg' ? 'por kg' : 'unidad' }}<input class="input num" inputmode="decimal" :value="txt(l.costo)" @input="l.costo = aNumero($event.target.value)"></label>
              <label class="campo crece" style="min-width:110px">Nuevo precio<input class="input num" inputmode="numeric" :placeholder="miles(l.precio_actual)" :value="l.nuevo_precio || ''" @input="l.nuevo_precio = aNumero($event.target.value.replace(/\\D/g, ''))"></label>
            </div>
            <div class="fila entre small"><span :class="variacion(l) > 0.5 ? 'danger' : variacion(l) < -0.5 ? 'ok' : 'muted'" v-if="variacion(l) !== null && Math.abs(variacion(l)) >= 0.5">{{ variacion(l) > 0 ? '▲' : '▼' }} {{ Math.abs(variacion(l)).toFixed(1).replace('.', ',') }} % frente al costo actual</span><span v-else></span>
              <b class="num">{{ peso((l.cantidad || 0) * (l.costo || 0)) }}</b></div>
          </div>
        </div>
        <div class="vacio" v-else>Escanee cada producto de la factura.</div>
      </template>
      <template #pie v-if="!hecho">
        <div class="crece"><div class="xs muted">{{ lineas.length }} producto(s)</div><div class="total num" style="font-size:22px">{{ peso(total) }}</div></div>
        <button class="btn primario grande" :disabled="!listo || guardando" @click="guardar"><Icono n="check"/> Guardar</button>
      </template>
    </Pantalla>`,
};
