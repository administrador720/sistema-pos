// Productos: lista, editor (códigos de barras, precios, kardex), importación desde Excel y precios masivos
import { api, query } from '../api.js';
import { store, errorToast, toast, pedirTexto, confirmar } from '../store.js';
import { peso, entero, decimal, fechaHora, porcentaje, debounce, descargarBlob, cantidadTxt, conUnidad } from '../util.js';

const { ref, reactive, computed, onMounted, watch, nextTick } = Vue;

const margenDe = (precio, costo, tarifa) => {
  if (!precio) return null;
  const base = precio / (1 + (tarifa || 0) / 100);
  return (1 - (costo || 0) / base) * 100;
};

// ───────────────────────── Editor ─────────────────────────
const Editor = {
  props: { id: Number },   // sin id = producto nuevo
  emits: ['cerrar', 'guardado'],
  setup(p, { emit }) {
    const nuevo = !p.id;
    const f = reactive({ nombre: '', codigo_interno: '', marca: '', categoria_id: null, proveedor_id: null, impuesto_id: null, costo_promedio: 0,
      precio_venta: null, unidad: 'u', rapido: false, stock_minimo: 0, stock_maximo: 0, stock_inicial: null, ubicacion: '', activo: true, codigos: [] });
    const porPeso = computed(() => f.unidad === 'kg');
    const tab = ref('datos'), cargando = ref(!nuevo), guardando = ref(false);
    const codigoNuevo = ref(''), unidadesNuevo = ref(1), historial = ref(null), kardex = ref(null), stockActual = ref(0);
    const tarifa = computed(() => store.cat.impuestos.find(i => i.id === f.impuesto_id)?.tarifa_pct || 0);
    const margen = computed(() => margenDe(f.precio_venta, f.costo_promedio, tarifa.value));
    const inNombre = ref(null), inCodigo = ref(null);

    onMounted(async () => {
      if (nuevo) {
        f.impuesto_id = store.cat.impuestos.find(i => i.tarifa_pct === 19)?.id ?? store.cat.impuestos[0]?.id ?? null;
        f.categoria_id = store.cat.categorias[0]?.id ?? null;
        nextTick(() => inNombre.value?.focus()); return;
      }
      try {
        const d = await api.get('/api/productos/' + p.id);
        Object.assign(f, { nombre: d.nombre, codigo_interno: d.codigo_interno || '', marca: d.marca || '', categoria_id: d.categoria_id, proveedor_id: d.proveedor_id,
          impuesto_id: d.impuesto_id, costo_promedio: d.costo_promedio, precio_venta: d.precio_venta, unidad: d.unidad || 'u', rapido: !!d.rapido, stock_minimo: d.stock_minimo, stock_maximo: d.stock_maximo,
          ubicacion: d.ubicacion || '', activo: d.activo, codigos: d.codigos.map(c => ({ ...c })) });
        stockActual.value = d.stock_actual;
      } catch (e) { errorToast(e); emit('cerrar'); }
      cargando.value = false;
    });
    watch(tab, async t => {
      try {
        if (t === 'precios' && !historial.value) historial.value = await api.get(`/api/productos/${p.id}/historial-precios`);
        if (t === 'kardex' && !kardex.value) kardex.value = await api.get('/api/inventario/kardex' + query({ producto_id: p.id }));
      } catch (e) { errorToast(e); }
    });

    function agregarCodigo() {
      const c = codigoNuevo.value.trim(); if (!c) return;
      if (f.codigos.some(x => x.codigo === c)) { toast('Ese código ya está en la lista.', 'warn'); return; }
      f.codigos.push({ codigo: c, unidades: Math.max(1, unidadesNuevo.value || 1) });
      codigoNuevo.value = ''; unidadesNuevo.value = 1; nextTick(() => inCodigo.value?.focus());
    }
    async function nuevaCategoria() {
      const n = await pedirTexto('Nueva categoría', 'Nombre de la categoría'); if (!n) return;
      try { const c = await api.post('/api/categorias', { nombre: n }); store.cat.categorias.push(c); f.categoria_id = c.id; } catch (e) { errorToast(e); }
    }
    async function nuevoProveedor() {
      const n = await pedirTexto('Nuevo proveedor', 'Nombre del proveedor'); if (!n) return;
      try { const c = await api.post('/api/proveedores', { nombre: n }); store.cat.proveedores.push(c); f.proveedor_id = c.id; } catch (e) { errorToast(e); }
    }
    async function guardar() {
      guardando.value = true;
      try {
        const cuerpo = { ...f, codigos: f.codigos.map(c => ({ codigo: c.codigo, unidades: c.unidades })) };
        if (!nuevo) delete cuerpo.stock_inicial;
        if (nuevo) await api.post('/api/productos', cuerpo); else await api.put('/api/productos/' + p.id, cuerpo);
        toast(nuevo ? 'Producto creado.' : 'Producto guardado.', 'ok'); emit('guardado');
      } catch (e) { errorToast(e); } finally { guardando.value = false; }
    }
    return { nuevo, f, porPeso, tab, cargando, guardando, store, codigoNuevo, unidadesNuevo, historial, kardex, stockActual, margen, tarifa, inNombre, inCodigo,
      agregarCodigo, nuevaCategoria, nuevoProveedor, guardar, peso, entero, decimal, fechaHora, porcentaje, cantidadTxt, conUnidad };
  },
  template: `
    <Modal :titulo="nuevo ? 'Producto nuevo' : 'Editar producto'" ancho="lg" @cerrar="$emit('cerrar')">
      <div v-if="cargando" class="empty">Cargando…</div>
      <div v-else class="stack">
        <div class="tabs" v-if="!nuevo"><button :class="{ on: tab === 'datos' }" @click="tab = 'datos'">Datos</button>
          <button :class="{ on: tab === 'precios' }" @click="tab = 'precios'">Historial de precios</button>
          <button :class="{ on: tab === 'kardex' }" @click="tab = 'kardex'">Movimientos (kardex)</button></div>

        <div v-show="tab === 'datos'" class="stack">
          <div class="row wrap">
            <div class="seg"><button :class="{ on: !porPeso }" @click="f.unidad = 'u'">Se vende por unidad</button><button :class="{ on: porPeso }" @click="f.unidad = 'kg'">Se vende por peso (kg)</button></div>
            <span class="hint" v-if="porPeso">Verduras, frutas, carnes sueltas… El precio y el costo son <b>por kilo</b>; el cajero escribe el peso de la balanza.</span>
          </div>
          <div class="grid" style="grid-template-columns:2fr 1fr 1fr">
            <div class="field"><label>Nombre *</label><input ref="inNombre" class="input" v-model="f.nombre" :placeholder="porPeso ? 'Ej.: Tomate chonto' : ''"></div>
            <div class="field"><label>Marca</label><input class="input" v-model="f.marca"></div>
            <div class="field"><label>{{ porPeso ? 'Código corto (PLU)' : 'Código interno' }}</label><input class="input" v-model="f.codigo_interno" :placeholder="porPeso ? 'Ej.: 101' : ''">
              <span class="hint" v-if="porPeso">El cajero lo escribe en la caja para encontrarlo rápido.</span></div>
          </div>
          <label class="check" v-if="porPeso"><input type="checkbox" v-model="f.rapido"> Botón rápido en la caja (aparece en «Verduras y frutas», tecla F1)</label>
          <div class="grid c3">
            <div class="field"><label>Categoría</label><div class="row"><select class="input" v-model="f.categoria_id"><option :value="null">Sin categoría</option>
              <option v-for="c in store.cat.categorias" :key="c.id" :value="c.id">{{ c.nombre }}</option></select><button class="btn icon" @click="nuevaCategoria" title="Nueva categoría"><Icono n="mas"/></button></div></div>
            <div class="field"><label>Proveedor</label><div class="row"><select class="input" v-model="f.proveedor_id"><option :value="null">Sin proveedor</option>
              <option v-for="c in store.cat.proveedores" :key="c.id" :value="c.id">{{ c.nombre }}</option></select><button class="btn icon" @click="nuevoProveedor" title="Nuevo proveedor"><Icono n="mas"/></button></div></div>
            <div class="field"><label>Impuesto (incluido en el precio)</label><select class="input" v-model="f.impuesto_id"><option v-for="i in store.cat.impuestos" :key="i.id" :value="i.id">{{ i.nombre }}</option></select></div>
          </div>
          <div class="grid c4">
            <div class="field"><label>{{ porPeso ? 'Precio por kilo' : 'Precio de venta' }}</label><InputDinero v-model="f.precio_venta"/></div>
            <div class="field"><label>{{ porPeso ? 'Costo por kilo' : 'Costo' }} {{ nuevo ? '' : '(promedio)' }}</label><input class="input num" type="number" min="0" step="0.01" v-model.number="f.costo_promedio"></div>
            <div class="field"><label>Margen bruto</label><div class="input row" style="background:var(--surface-2)" :class="margen !== null && margen < 0 ? 'danger' : ''">
              <b class="num">{{ margen === null ? '—' : porcentaje(margen) }}</b><span class="xs muted">sobre precio sin impuesto</span></div></div>
            <div class="field" v-if="nuevo"><label>Existencias iniciales{{ porPeso ? ' (kg)' : '' }}</label>
              <InputPeso v-if="porPeso" v-model="f.stock_inicial" placeholder="0"/><InputDinero v-else v-model="f.stock_inicial" placeholder="0"/></div>
            <div class="field" v-else><label>Existencias actuales</label><div class="input row" style="background:var(--surface-2)"><b class="num">{{ conUnidad(stockActual, f.unidad) }}</b><span class="xs muted">cambian con compras, ventas y conteos</span></div></div>
          </div>
          <div class="alert" v-if="margen !== null && margen < 0"><Icono n="alerta"/>El precio está por debajo del costo: cada venta pierde dinero.</div>
          <div class="grid c3">
            <div class="field"><label>Stock mínimo (alerta){{ porPeso ? ' · kg' : '' }}</label>
              <InputPeso v-if="porPeso" v-model="f.stock_minimo"/><input v-else class="input num" type="number" min="0" v-model.number="f.stock_minimo"></div>
            <div class="field"><label>Stock máximo{{ porPeso ? ' · kg' : '' }}</label>
              <InputPeso v-if="porPeso" v-model="f.stock_maximo"/><input v-else class="input num" type="number" min="0" v-model.number="f.stock_maximo"></div>
            <div class="field"><label>Ubicación (pasillo / góndola)</label><input class="input" v-model="f.ubicacion"></div>
          </div>
          <div class="card soft stack sm">
            <div class="row between"><h3>Códigos de barras{{ porPeso ? ' (opcional)' : '' }}</h3><span class="hint">{{ porPeso ? 'Por peso se vende con el código corto o los botones rápidos; el código de barras no es necesario.' : 'Un producto puede tener varios. Un código de paca puede valer varias unidades.' }}</span></div>
            <div class="row wrap"><span v-for="c in f.codigos" :key="c.codigo" class="chip accent" style="height:30px">
              <Icono n="barras"/> {{ c.codigo }}<b v-if="c.unidades > 1"> × {{ c.unidades }}</b>
              <button class="btn ghost icon sm" style="width:22px;height:22px" @click="f.codigos.splice(f.codigos.indexOf(c), 1)"><Icono n="x"/></button></span>
              <span v-if="!f.codigos.length && !porPeso" class="muted small">Sin códigos: solo se podrá vender buscando por nombre.</span></div>
            <div class="row"><input ref="inCodigo" class="input" v-model="codigoNuevo" placeholder="Escanee o digite un código y presione Enter" @keydown.enter.prevent="agregarCodigo" style="flex:1">
              <input class="input num" type="number" min="1" v-model.number="unidadesNuevo" style="width:110px" title="Unidades que representa este código"><span class="muted small">unidades</span>
              <button class="btn" @click="agregarCodigo"><Icono n="mas"/> Agregar</button></div>
          </div>
          <label class="check"><input type="checkbox" v-model="f.activo"> Producto activo (se puede vender)</label>
        </div>

        <div v-if="tab === 'precios'">
          <div class="empty" v-if="historial && !historial.length">Este producto no ha tenido cambios de precio.</div>
          <table class="t compact" v-else-if="historial"><thead><tr><th>Fecha</th><th class="num">Antes</th><th class="num">Después</th><th>Cambió</th></tr></thead><tbody>
            <tr v-for="h in historial" :key="h.fecha"><td>{{ fechaHora(h.fecha) }}</td><td class="num">{{ peso(h.anterior) }}</td><td class="num"><b>{{ peso(h.nuevo) }}</b></td><td>{{ h.usuario }}</td></tr></tbody></table>
        </div>
        <div v-if="tab === 'kardex'">
          <div class="table-wrap" style="max-height:50vh"><table class="t compact" v-if="kardex"><thead><tr><th>Fecha</th><th>Movimiento</th><th class="num">Cantidad</th><th class="num">Costo</th><th class="num">Saldo</th><th>Usuario</th></tr></thead><tbody>
            <tr v-for="k in kardex" :key="k.id"><td>{{ fechaHora(k.fecha) }}</td><td>{{ k.tipo_nombre }}<span class="xs muted" v-if="k.nota"> · {{ k.nota }}</span></td>
              <td class="num" :class="k.cantidad < 0 ? 'danger' : 'ok'">{{ k.cantidad > 0 ? '+' : '' }}{{ cantidadTxt(k.cantidad) }}</td><td class="num">{{ decimal(k.costo_unitario) }}</td><td class="num"><b>{{ cantidadTxt(k.stock_resultante) }}</b></td><td>{{ k.usuario }}</td></tr></tbody></table></div>
        </div>
      </div>
      <template #pie>
        <button class="btn" @click="$emit('cerrar')">Cancelar</button>
        <button class="btn primary" :disabled="guardando || !f.nombre.trim()" @click="guardar"><Icono n="check"/> {{ nuevo ? 'Crear producto' : 'Guardar cambios' }}</button>
      </template>
    </Modal>`,
};

// ───────────────────────── Importar desde Excel ─────────────────────────
const Importar = {
  emits: ['cerrar', 'hecho'],
  setup(p, { emit }) {
    const archivo = ref(null), previo = ref(null), cargando = ref(false), sobre = ref(false), input = ref(null);
    async function subir(simular) {
      const fd = new FormData(); fd.append('archivo', archivo.value);
      return api.upload('/api/productos/importar?simular=' + simular, fd);
    }
    async function elegir(file) {
      if (!file) return; archivo.value = file; previo.value = null; cargando.value = true;
      try { previo.value = await subir(true); } catch (e) { errorToast(e); archivo.value = null; } finally { cargando.value = false; }
    }
    async function aplicar() {
      cargando.value = true;
      try { const r = await subir(false); toast(`Importación lista: ${r.creados} nuevos, ${r.actualizados} actualizados.`, 'ok', 6000); emit('hecho'); }
      catch (e) { errorToast(e); } finally { cargando.value = false; }
    }
    async function plantilla() { try { descargarBlob(await api.blob('/api/productos/plantilla'), 'plantilla-productos.xlsx'); } catch (e) { errorToast(e); } }
    return { archivo, previo, cargando, sobre, input, elegir, aplicar, plantilla };
  },
  template: `
    <Modal titulo="Importar productos desde Excel" ancho="lg" @cerrar="$emit('cerrar')">
      <div class="stack">
        <div class="alert info"><Icono n="info"/><div>Cargue su lista de productos de una vez. Descargue la plantilla, llénela (una fila por producto) y súbala. <b>Primero se revisa sin guardar nada</b>; usted confirma después.</div></div>
        <div class="row"><button class="btn" @click="plantilla"><Icono n="bajar"/> Descargar plantilla</button></div>
        <div class="dropzone" :class="{ over: sobre }" @click="input.click()" @dragover.prevent="sobre = true" @dragleave="sobre = false" @drop.prevent="sobre = false; elegir($event.dataTransfer.files[0])">
          <Icono n="subir" class="ico xl" style="margin:0 auto 8px"/>
          <div><b>{{ archivo ? archivo.name : 'Haga clic o arrastre aquí su archivo .xlsx o .csv' }}</b></div>
          <input ref="input" type="file" accept=".xlsx,.xlsm,.csv,.txt" class="hidden" @change="elegir($event.target.files[0])">
        </div>
        <div v-if="cargando" class="muted center">Revisando el archivo…</div>
        <div v-if="previo" class="stack">
          <div class="grid c4">
            <div class="card soft kpi"><span class="lbl">Filas leídas</span><span class="val">{{ previo.filas }}</span></div>
            <div class="card soft kpi"><span class="lbl">Productos nuevos</span><span class="val ok">{{ previo.creados }}</span></div>
            <div class="card soft kpi"><span class="lbl">Se actualizarán</span><span class="val">{{ previo.actualizados }}</span></div>
            <div class="card soft kpi"><span class="lbl">Con errores</span><span class="val" :class="previo.errores.length ? 'danger' : ''">{{ previo.errores.length }}</span></div>
          </div>
          <div class="table-wrap" style="max-height:220px" v-if="previo.errores.length"><table class="t compact"><thead><tr><th>Fila</th><th>Producto</th><th>Problema</th></tr></thead><tbody>
            <tr v-for="e in previo.errores" :key="e.fila"><td>{{ e.fila }}</td><td>{{ e.nombre }}</td><td class="danger">{{ e.error }}</td></tr></tbody></table></div>
          <div class="alert danger" v-if="previo.errores.length"><Icono n="alerta"/>Corrija estas filas y suba el archivo de nuevo. No se importa nada mientras haya errores.</div>
        </div>
      </div>
      <template #pie><button class="btn" @click="$emit('cerrar')">Cerrar</button>
        <button class="btn primary" :disabled="!previo || previo.errores.length || cargando || (previo.creados + previo.actualizados) === 0" @click="aplicar"><Icono n="check"/> Importar {{ previo ? previo.creados + previo.actualizados : 0 }} productos</button></template>
    </Modal>`,
};

// ───────────────────────── Cambio masivo de precios ─────────────────────────
const PreciosMasivo = {
  emits: ['cerrar', 'hecho'],
  setup(p, { emit }) {
    const f = reactive({ porcentaje: null, categoria_id: null, proveedor_id: null, redondeo: 50 }), r = ref(null), cargando = ref(false);
    async function simular() {
      if (f.porcentaje === null || f.porcentaje === '') return;
      cargando.value = true;
      try { r.value = await api.post('/api/productos/precios-masivo', { ...f, simular: true }); } catch (e) { errorToast(e); r.value = null; } finally { cargando.value = false; }
    }
    watch(f, debounce(simular, 350));
    async function aplicar() {
      if (!await confirmar('¿Aplicar el cambio de precios?', `Se cambiará el precio de ${r.value.afectados} producto(s). Queda registrado en el historial.`, { textoOk: 'Sí, aplicar' })) return;
      try { await api.post('/api/productos/precios-masivo', { ...f, simular: false }); toast('Precios actualizados.', 'ok'); emit('hecho'); } catch (e) { errorToast(e); }
    }
    return { f, r, cargando, store, aplicar, peso };
  },
  template: `
    <Modal titulo="Cambio masivo de precios" ancho="md" @cerrar="$emit('cerrar')">
      <div class="stack">
        <div class="grid c2">
          <div class="field"><label>Subir o bajar (%)</label><input class="input lg num" type="number" step="0.1" v-model.number="f.porcentaje" placeholder="Ej.: 5 sube, −3 baja" autofocus></div>
          <div class="field"><label>Redondear a múltiplos de</label><select class="input lg" v-model.number="f.redondeo"><option :value="0">Sin redondeo</option><option :value="10">$ 10</option><option :value="50">$ 50</option><option :value="100">$ 100</option><option :value="500">$ 500</option></select></div>
          <div class="field"><label>Solo la categoría</label><select class="input" v-model="f.categoria_id"><option :value="null">Todas</option><option v-for="c in store.cat.categorias" :key="c.id" :value="c.id">{{ c.nombre }}</option></select></div>
          <div class="field"><label>Solo el proveedor</label><select class="input" v-model="f.proveedor_id"><option :value="null">Todos</option><option v-for="c in store.cat.proveedores" :key="c.id" :value="c.id">{{ c.nombre }}</option></select></div>
        </div>
        <div v-if="r" class="stack sm">
          <div class="alert info"><Icono n="info"/>Se cambiará el precio de <b>{{ r.afectados }}</b> producto(s). Vista previa (nada se guarda todavía):</div>
          <table class="t compact" v-if="r.muestra.length"><thead><tr><th>Producto</th><th class="num">Antes</th><th class="num">Después</th></tr></thead><tbody>
            <tr v-for="m in r.muestra" :key="m.id"><td>{{ m.nombre }}</td><td class="num">{{ peso(m.antes) }}</td><td class="num"><b>{{ peso(m.despues) }}</b></td></tr></tbody></table>
        </div>
      </div>
      <template #pie><button class="btn" @click="$emit('cerrar')">Cancelar</button><button class="btn primary" :disabled="!r || !r.afectados" @click="aplicar">Aplicar cambio</button></template>
    </Modal>`,
};

// ───────────────────────── Lista ─────────────────────────
export const Productos = {
  components: { Editor, Importar, PreciosMasivo },
  setup() {
    const filtro = reactive({ q: '', categoria_id: null, proveedor_id: null, estado: 'activos', bajo_minimo: false }), pag = reactive({ offset: 0, limite: 50 });
    const datos = ref({ total: 0, productos: [] }), cargando = ref(true), dlg = ref(null), editId = ref(null);
    async function cargar() {
      cargando.value = true;
      try { datos.value = await api.get('/api/productos' + query({ ...filtro, ...pag, bajo_minimo: filtro.bajo_minimo || '' })); } catch (e) { errorToast(e); }
      cargando.value = false;
    }
    const recargar = debounce(() => { pag.offset = 0; cargar(); }, 250);
    watch(filtro, recargar);
    onMounted(cargar);
    const desde = computed(() => datos.value.total ? pag.offset + 1 : 0);
    const hasta = computed(() => Math.min(pag.offset + pag.limite, datos.value.total));
    function mover(d) { pag.offset = Math.max(0, Math.min(pag.offset + d * pag.limite, datos.value.total - 1)); cargar(); }
    const editar = id => { editId.value = id; dlg.value = 'editor'; };
    const hecho = () => { dlg.value = null; cargar(); };
    return { filtro, datos, cargando, dlg, editId, store, desde, hasta, mover, editar, hecho, cargar, peso, entero, decimal, porcentaje, cantidadTxt, conUnidad };
  },
  template: `
    <div class="page">
      <div class="row wrap" style="margin-bottom:12px">
        <input class="input grow" style="min-width:240px" v-model="filtro.q" placeholder="Buscar por nombre, marca o código de barras…">
        <button class="btn" @click="dlg = 'precios'"><Icono n="porcentaje"/> Precios masivos</button><button class="btn" @click="dlg = 'importar'"><Icono n="subir"/> Importar Excel</button>
        <button class="btn primary" @click="editar(null)"><Icono n="mas"/> Nuevo producto</button>
      </div>
      <div class="row wrap" style="margin-bottom:16px">
        <select class="input" style="width:210px" v-model="filtro.categoria_id"><option :value="null">Todas las categorías</option><option v-for="c in store.cat.categorias" :key="c.id" :value="c.id">{{ c.nombre }}</option></select>
        <select class="input" style="width:230px" v-model="filtro.proveedor_id"><option :value="null">Todos los proveedores</option><option v-for="c in store.cat.proveedores" :key="c.id" :value="c.id">{{ c.nombre }}</option></select>
        <div class="seg"><button :class="{ on: filtro.estado === 'activos' }" @click="filtro.estado = 'activos'">Activos</button><button :class="{ on: filtro.estado === 'inactivos' }" @click="filtro.estado = 'inactivos'">Inactivos</button><button :class="{ on: filtro.estado === 'todos' }" @click="filtro.estado = 'todos'">Todos</button></div>
        <label class="check"><input type="checkbox" v-model="filtro.bajo_minimo"> Solo bajo el mínimo</label>
      </div>
      <div class="card pad0">
        <div class="table-wrap" style="max-height:calc(100vh - 290px)">
          <table class="t"><thead><tr><th>Producto</th><th>Código</th><th>Categoría</th><th class="num">Costo</th><th class="num">Precio</th><th class="num">Margen</th><th class="num">Stock</th><th class="num">Mín.</th><th>Estado</th></tr></thead>
            <tbody>
              <tr v-for="p in datos.productos" :key="p.id" class="clickable" @click="editar(p.id)">
                <td><b>{{ p.nombre }}</b><span v-if="p.unidad === 'kg'" class="chip accent" style="margin-left:8px;height:20px">kg</span><span v-if="p.rapido" class="chip" style="margin-left:4px;height:20px" title="Botón rápido en la caja">F1</span><div class="xs muted">{{ p.marca || '' }}{{ p.marca && p.ubicacion ? ' · ' : '' }}{{ p.ubicacion || '' }}</div></td>
                <td class="muted small">{{ p.codigos[0] ? p.codigos[0].codigo : (p.codigo_interno || '—') }}<span v-if="p.codigos.length > 1" class="chip" style="margin-left:6px">+{{ p.codigos.length - 1 }}</span></td>
                <td>{{ p.categoria || '—' }}</td><td class="num">{{ decimal(p.costo_promedio, 0) }}</td><td class="num"><b>{{ peso(p.precio_venta) }}</b><span v-if="p.unidad === 'kg'" class="xs muted"> /kg</span></td>
                <td class="num" :class="p.margen_pct !== null && p.margen_pct < 0 ? 'danger' : ''">{{ p.margen_pct === null ? '—' : porcentaje(p.margen_pct) }}</td>
                <td class="num"><b :class="p.stock_actual < 0 ? 'danger' : p.stock_actual <= p.stock_minimo ? 'warn' : ''">{{ conUnidad(p.stock_actual, p.unidad) }}</b></td>
                <td class="num muted">{{ cantidadTxt(p.stock_minimo) }}</td><td><span class="chip" :class="p.activo ? 'ok' : ''">{{ p.activo ? 'Activo' : 'Inactivo' }}</span></td>
              </tr>
              <tr v-if="!cargando && !datos.productos.length"><td colspan="9"><div class="empty"><Icono n="caja_prod" class="ico xl"/><div>No hay productos con estos filtros.</div></div></td></tr>
            </tbody></table>
        </div>
        <div class="row between" style="padding:12px 18px;border-top:1px solid var(--border)">
          <span class="muted small">{{ desde }}–{{ hasta }} de {{ entero(datos.total) }} productos</span>
          <div class="row"><button class="btn sm" :disabled="desde <= 1" @click="mover(-1)"><Icono n="izq"/> Anterior</button><button class="btn sm" :disabled="hasta >= datos.total" @click="mover(1)">Siguiente <Icono n="der"/></button></div>
        </div>
      </div>
      <Editor v-if="dlg === 'editor'" :id="editId" @cerrar="dlg = null" @guardado="hecho"/>
      <Importar v-if="dlg === 'importar'" @cerrar="dlg = null" @hecho="hecho"/>
      <PreciosMasivo v-if="dlg === 'precios'" @cerrar="dlg = null" @hecho="hecho"/>
    </div>`,
};
