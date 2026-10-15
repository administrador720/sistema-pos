// Informes administrativos: catálogo, parámetros, tabla ordenable y exportación a Excel / PDF
import { api, query } from '../api.js';
import { store, errorToast, exportarArchivo } from '../store.js';
import { formatear, esNumerico, isoHoy, inicioMes, fecha } from '../util.js';
import { ordenarPor } from '../components.js';

const { ref, reactive, computed, onMounted, watch } = Vue;

const ATAJOS = [['hoy', 'Hoy'], ['7', '7 días'], ['30', '30 días'], ['mes', 'Este mes'], ['mes_ant', 'Mes pasado'], ['anio', 'Este año'], ['custom', 'Personalizado']];
function rangoDe(k) {
  const hoy = isoHoy(), d = new Date(), f = x => `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}-${String(x.getDate()).padStart(2, '0')}`;
  if (k === 'hoy') return [hoy, hoy];
  if (k === '7') return [isoHoy(-6), hoy];
  if (k === '30') return [isoHoy(-29), hoy];
  if (k === 'mes') return [inicioMes(), hoy];
  if (k === 'anio') return [`${d.getFullYear()}-01-01`, hoy];
  return [f(new Date(d.getFullYear(), d.getMonth() - 1, 1)), f(new Date(d.getFullYear(), d.getMonth(), 0))];
}
const LIMITE_FILAS = 500;

export const Informes = {
  setup() {
    const catalogo = ref([]), slug = ref(null), atajo = ref('30'), custom = reactive({ desde: isoHoy(-29), hasta: isoHoy() });
    const params = reactive({}), prodElegido = ref(null), r = ref(null), cargando = ref(false), orden = reactive({ clave: null, asc: true });
    const actual = computed(() => catalogo.value.find(c => c.slug === slug.value));
    const grupos = computed(() => { const g = {}; for (const c of catalogo.value) (g[c.grupo] ||= []).push(c); return g; });
    const rango = computed(() => atajo.value === 'custom' ? [custom.desde, custom.hasta] : rangoDe(atajo.value));

    async function generar() {
      if (!actual.value) return;
      if (actual.value.params.some(p => p.tipo === 'producto') && !params.producto_id) { r.value = null; return; }
      cargando.value = true;
      try {
        const [desde, hasta] = rango.value;
        r.value = await api.get(`/api/informes/${slug.value}` + query({ ...(actual.value.fechas ? { desde, hasta } : {}), ...params }));
        orden.clave = null;
      } catch (e) { errorToast(e); r.value = null; }
      cargando.value = false;
    }
    function elegir(s) {
      slug.value = s; location.hash = '#/informes/' + s;
      for (const k of Object.keys(params)) delete params[k]; prodElegido.value = null;
      for (const p of actual.value.params) if (p.default !== null && p.default !== undefined) params[p.name] = p.default;
      r.value = null; generar();
    }
    onMounted(async () => {
      try { catalogo.value = await api.get('/api/informes'); } catch (e) { return errorToast(e); }
      const pedido = store.ruta.arg && catalogo.value.find(c => c.slug === store.ruta.arg);
      elegir(pedido ? pedido.slug : catalogo.value[0].slug);
    });
    watch(atajo, () => { if (atajo.value !== 'custom') generar(); });
    function elegirProd(p) { prodElegido.value = p; params.producto_id = p.id; generar(); }

    const filas = computed(() => {
      if (!r.value) return [];
      const f = orden.clave ? ordenarPor(r.value.filas, orden.clave, orden.asc) : r.value.filas;
      return f.slice(0, LIMITE_FILAS);
    });
    function ordenar(k) { if (orden.clave === k) orden.asc = !orden.asc; else { orden.clave = k; orden.asc = !esNumerico(r.value.columnas.find(c => c.key === k)?.tipo); } }
    const exportar = f => { const [desde, hasta] = rango.value; return exportarArchivo(`/api/informes/${slug.value}`, { ...(actual.value.fechas ? { desde, hasta } : {}), ...params }, f, slug.value).catch(errorToast); };
    return { catalogo, grupos, slug, actual, atajo, custom, params, r, cargando, orden, filas, prodElegido, ATAJOS, LIMITE_FILAS, elegir, generar, ordenar, exportar, elegirProd, formatear, esNumerico, fecha };
  },
  template: `
    <div class="page">
      <div class="split">
        <div class="card informes-nav" style="padding:10px;position:sticky;top:0;max-height:calc(100vh - 130px);overflow:auto">
          <template v-for="(lista, g) in grupos" :key="g"><h4>{{ g }}</h4>
            <button v-for="c in lista" :key="c.slug" :class="{ on: slug === c.slug }" @click="elegir(c.slug)">{{ c.titulo }}</button></template>
        </div>

        <div class="stack" v-if="actual">
          <div class="card stack">
            <div><h2>{{ actual.titulo }}</h2><p class="muted small" style="margin-top:4px">{{ actual.descripcion }}</p></div>
            <div class="row wrap" style="align-items:flex-end">
              <div class="seg" v-if="actual.fechas"><button v-for="a in ATAJOS" :key="a[0]" :class="{ on: atajo === a[0] }" @click="atajo = a[0]">{{ a[1] }}</button></div>
              <template v-if="actual.fechas && atajo === 'custom'"><input type="date" class="input sm" style="width:auto" v-model="custom.desde"><span class="muted">a</span><input type="date" class="input sm" style="width:auto" v-model="custom.hasta"><button class="btn sm primary" @click="generar">Generar</button></template>
              <div class="field" v-for="p in actual.params" :key="p.name" style="min-width:200px" :style="p.tipo === 'producto' ? { minWidth: '320px' } : {}">
                <label>{{ p.label }}</label>
                <select v-if="p.tipo === 'opcion'" class="input sm" v-model="params[p.name]" @change="generar"><option v-for="o in p.opciones" :key="o[0]" :value="o[0]">{{ o[1] }}</option></select>
                <input v-else-if="p.tipo === 'numero'" class="input sm num" type="number" min="1" v-model.number="params[p.name]" @change="generar" style="width:140px">
                <div v-else><BuscaProducto :limpiar="false" @elegir="elegirProd"/></div>
              </div>
              <div class="row" style="margin-left:auto"><button class="btn sm" :disabled="!r" @click="exportar('xlsx')"><Icono n="bajar"/> Excel</button><button class="btn sm" :disabled="!r" @click="exportar('pdf')"><Icono n="impresora"/> PDF</button></div>
            </div>
          </div>

          <div class="card pad0" :style="{ opacity: cargando ? .55 : 1 }">
            <div v-if="!r && !cargando" class="empty"><Icono n="informe" class="ico xl"/><div>{{ actual.params.some(p => p.tipo === 'producto') ? 'Elija un producto para ver el informe.' : 'Sin datos.' }}</div></div>
            <template v-if="r">
              <div class="row between" style="padding:14px 20px;border-bottom:1px solid var(--border)"><div><b>{{ r.titulo }}</b><div class="xs muted" v-if="actual.fechas">{{ fecha(r.desde) }} – {{ fecha(r.hasta) }} · {{ r.filas.length }} fila(s)</div></div></div>
              <div class="table-wrap" style="max-height:calc(100vh - 360px)"><table class="t" v-if="r.columnas.length">
                <thead><tr><th v-for="c in r.columnas" :key="c.key" class="sortable" :class="{ num: esNumerico(c.tipo) }" @click="ordenar(c.key)">{{ c.titulo }} <span v-if="orden.clave === c.key">{{ orden.asc ? '▲' : '▼' }}</span></th></tr></thead>
                <tbody><tr v-for="(f, i) in filas" :key="i"><td v-for="c in r.columnas" :key="c.key" :class="{ num: esNumerico(c.tipo) }">{{ formatear(f[c.key], c.tipo) }}</td></tr>
                  <tr v-if="!r.filas.length"><td :colspan="r.columnas.length" class="empty">No hay datos para este periodo.</td></tr></tbody>
                <tfoot v-if="Object.keys(r.totales || {}).length && r.filas.length"><tr><td v-for="(c, i) in r.columnas" :key="c.key" :class="{ num: esNumerico(c.tipo) }">{{ i === 0 ? 'Total' : (r.totales[c.key] !== undefined ? formatear(r.totales[c.key], c.tipo) : '') }}</td></tr></tfoot>
              </table><div v-else class="empty">{{ r.nota }}</div></div>
              <div class="muted small" style="padding:12px 20px;border-top:1px solid var(--border)" v-if="r.nota && r.columnas.length">{{ r.nota }}<span v-if="r.filas.length > LIMITE_FILAS"> · Se muestran las primeras {{ LIMITE_FILAS }} filas; exporte a Excel para ver todas.</span></div>
            </template>
          </div>
        </div>
      </div>
    </div>`,
};
