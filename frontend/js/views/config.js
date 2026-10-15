// Configuración: negocio, reglas, cajón, catálogos, usuarios, respaldos y auditoría + Mi cuenta
import { api, query } from '../api.js';
import { store, errorToast, toast, confirmar, pedirTexto, cargarCatalogos, cargarConfig, setTema } from '../store.js';
import { peso, fechaHora, fecha, isoHoy, miles, descargarBlob } from '../util.js';

const { ref, reactive, computed, onMounted, watch } = Vue;

// ───────────────────────── Tabla con formulario genérico ─────────────────────────
const Crud = {
  props: { singular: String, filas: Array, columnas: Array, campos: Array, guardar: Function, borrar: Function, nota: String },
  setup(p) {
    const dlg = ref(false), f = reactive({}), editId = ref(null), guardando = ref(false);
    function abrir(fila) {
      editId.value = fila ? fila.id : null;
      for (const c of p.campos) f[c.key] = fila ? (fila[c.key] ?? c.defecto ?? '') : (c.defecto !== undefined ? c.defecto : c.tipo === 'check' ? false : '');
      dlg.value = true;
    }
    async function enviar() { guardando.value = true; try { await p.guardar({ ...f }, editId.value); dlg.value = false; } catch (e) { errorToast(e); } finally { guardando.value = false; } }
    async function quitar() { if (await confirmar('¿Eliminar?', 'Esta acción no se puede deshacer.', { peligro: true, textoOk: 'Eliminar' })) { try { await p.borrar(editId.value); dlg.value = false; } catch (e) { errorToast(e); } } }
    const visible = c => !(c.soloAlCrear && editId.value) && !(c.soloAlEditar && !editId.value);
    return { dlg, f, editId, guardando, abrir, enviar, quitar, visible };
  },
  template: `
    <div class="stack">
      <div class="row between"><p class="muted small grow">{{ nota }}</p><button class="btn primary" @click="abrir(null)"><Icono n="mas"/> Nuevo {{ singular }}</button></div>
      <div class="card pad0"><div class="table-wrap" style="max-height:60vh"><table class="t"><thead><tr><th v-for="c in columnas" :key="c.key" :class="{ num: c.num }">{{ c.titulo }}</th></tr></thead><tbody>
        <tr v-for="fila in filas" :key="fila.id" class="clickable" @click="abrir(fila)"><td v-for="c in columnas" :key="c.key" :class="{ num: c.num }">
          <span v-if="c.chip" class="chip" :class="c.chip(fila[c.key])">{{ c.fmt ? c.fmt(fila[c.key], fila) : fila[c.key] }}</span><template v-else>{{ c.fmt ? c.fmt(fila[c.key], fila) : fila[c.key] }}</template></td></tr>
        <tr v-if="!filas.length"><td :colspan="columnas.length" class="empty">Aún no hay registros.</td></tr></tbody></table></div></div>
      <Modal v-if="dlg" :titulo="(editId ? 'Editar ' : 'Nuevo ') + singular" ancho="sm" @cerrar="dlg = false"><div class="stack">
        <template v-for="c in campos" :key="c.key"><div class="field" v-if="visible(c) && c.tipo !== 'check'"><label>{{ c.label }}</label>
          <select v-if="c.tipo === 'select'" class="input" v-model="f[c.key]"><option v-for="o in c.opciones" :key="o[0]" :value="o[0]">{{ o[1] }}</option></select>
          <input v-else-if="c.tipo === 'numero'" class="input num" type="number" step="any" v-model.number="f[c.key]">
          <input v-else class="input" :type="c.tipo === 'password' ? 'password' : 'text'" v-model="f[c.key]" :placeholder="c.ayuda" autocomplete="off">
          <span class="hint" v-if="c.ayuda && c.tipo !== 'texto' && c.tipo !== 'password'">{{ c.ayuda }}</span></div>
          <label class="check" v-else-if="visible(c)"><input type="checkbox" v-model="f[c.key]"> {{ c.label }}</label></template></div>
        <template #pie><button class="btn danger" v-if="editId && borrar" @click="quitar" style="margin-right:auto"><Icono n="basura"/> Eliminar</button><button class="btn" @click="dlg = false">Cancelar</button><button class="btn primary" :disabled="guardando" @click="enviar">Guardar</button></template></Modal>
    </div>`,
};

// ───────────────────────── Auditoría ─────────────────────────
const Auditoria = {
  setup() {
    const datos = ref({ acciones: [], filas: [] }), f = reactive({ accion: '', desde: isoHoy(-14), hasta: isoHoy() }), cargando = ref(true);
    async function cargar() { cargando.value = true; try { datos.value = await api.get('/api/auditoria' + query({ ...f, limite: 500 })); } catch (e) { errorToast(e); } cargando.value = false; }
    onMounted(cargar); watch(f, cargar);
    const resumen = x => { const d = x.despues, a = x.antes; if (!d && !a) return ''; const t = o => Object.entries(o || {}).map(([k, v]) => `${k}: ${typeof v === 'number' && /precio|total|monto|descuento|valor|base|dif/.test(k) ? peso(v) : v}`).join(' · '); return a ? `${t(a)}  →  ${t(d)}` : t(d); };
    return { datos, f, cargando, resumen, fechaHora };
  },
  template: `
    <div class="stack"><div class="row wrap"><div class="field"><label>Acción</label><select class="input sm" v-model="f.accion"><option value="">Todas</option><option v-for="a in datos.acciones" :key="a" :value="a">{{ a }}</option></select></div>
      <div class="field"><label>Desde</label><input type="date" class="input sm" v-model="f.desde"></div><div class="field"><label>Hasta</label><input type="date" class="input sm" v-model="f.hasta"></div></div>
      <div class="card pad0"><div class="table-wrap" style="max-height:62vh"><table class="t compact"><thead><tr><th>Fecha</th><th>Usuario</th><th>Acción</th><th>Detalle</th><th>Autorizó</th></tr></thead><tbody>
        <tr v-for="x in datos.filas" :key="x.id"><td class="nowrap">{{ fechaHora(x.fecha) }}</td><td>{{ x.usuario || '—' }}</td><td><span class="chip">{{ x.accion }}</span></td><td class="small muted" style="max-width:520px">{{ x.entidad ? x.entidad + ' #' + x.entidad_id + ' · ' : '' }}{{ resumen(x) }}</td><td>{{ x.autorizado_por || '' }}</td></tr>
        <tr v-if="!cargando && !datos.filas.length"><td colspan="5" class="empty">Sin movimientos en este periodo.</td></tr></tbody></table></div></div></div>`,
};

// ───────────────────────── Respaldos ─────────────────────────
const Respaldos = {
  props: { cfg: Object },
  emits: ['guardar'],
  setup(p, { emit }) {
    const datos = ref(null), cargando = ref(false);
    async function cargar() { try { datos.value = await api.get('/api/respaldos'); } catch (e) { errorToast(e); } }
    onMounted(cargar);
    async function ahora() {
      cargando.value = true;
      try { const r = await api.post('/api/respaldos'); toast(r.copia_externa ? 'Respaldo hecho y copiado a la carpeta externa.' : 'Respaldo hecho en este computador.' + (r.aviso ? '\n' + r.aviso : ''), r.aviso ? 'warn' : 'ok', 6000); cargar(); }
      catch (e) { errorToast(e); } finally { cargando.value = false; }
    }
    async function restaurar(r) {
      if (!await confirmar('¿Restaurar este respaldo?', `Se reemplazará TODA la información actual por la del ${fechaHora(r.fecha)}.\nLo que se haya hecho después se perderá (se guarda una copia de seguridad de lo actual antes de reemplazar).`, { peligro: true, textoOk: 'Continuar' })) return;
      const pw = await pedirTexto('Confirme con su contraseña', 'Contraseña del administrador', { secreto: true, textoOk: 'Restaurar' }); if (!pw) return;
      try { await api.post('/api/respaldos/restaurar', { archivo: r.archivo, password: pw }); toast('Respaldo restaurado. Inicie sesión de nuevo.', 'ok', 6000); setTimeout(() => location.reload(), 1200); } catch (e) { errorToast(e); }
    }
    async function bajar(r) { try { descargarBlob(await api.blob(`/api/respaldos/${encodeURIComponent(r.archivo)}/descargar`), r.archivo); } catch (e) { errorToast(e); } }
    const mb = b => (b / 1048576).toFixed(1).replace('.', ',') + ' MB';
    return { datos, cargando, ahora, restaurar, bajar, mb, fechaHora };
  },
  template: `
    <div class="stack lg" v-if="datos">
      <div class="alert" :class="datos.estado.alerta ? '' : 'ok'"><Icono :n="datos.estado.alerta ? 'alerta' : 'check'"/><div class="grow">{{ datos.estado.alerta || 'Los respaldos están al día y salen del computador.' }}</div></div>
      <div class="grid c2" style="align-items:start">
        <div class="card stack"><h3><Icono n="base"/> Respaldo automático</h3>
          <p class="muted small">El sistema guarda una copia cada día a la hora indicada (y al cerrar cada turno). Si el computador estaba apagado a esa hora, la hace al encenderlo. Se conservan 30 días y un respaldo por cada mes del último año.</p>
          <div class="grid c2"><div class="field"><label>Hora del respaldo diario</label><input class="input" type="time" v-model="cfg.respaldo_hora"></div>
            <div class="field"><label>Avisar si pasan (días)</label><input class="input num" type="number" min="1" v-model="cfg.respaldo_alerta_dias"></div></div>
          <div class="field"><label>Carpeta externa (USB, disco externo o carpeta sincronizada)</label><input class="input" v-model="cfg.respaldo_carpeta_externa" placeholder="Ej.: E:\\Respaldos  o  C:\\Users\\...\\Google Drive\\Respaldos POS">
            <span class="hint">Copia fuera del computador: si se daña o se lo roban, no se pierde nada. Una carpeta de Google Drive / OneDrive / Dropbox sube sola a la nube.</span></div>
          <div class="row"><button class="btn primary" @click="$emit('guardar', ['respaldo_hora', 'respaldo_alerta_dias', 'respaldo_carpeta_externa'])">Guardar</button>
            <button class="btn" :disabled="cargando" @click="ahora"><Icono n="base"/> Respaldar ahora</button></div></div>
        <div class="card pad0"><div style="padding:16px 20px 6px"><h3>Respaldos disponibles</h3></div><div class="table-wrap" style="max-height:340px"><table class="t compact"><tbody>
          <tr v-for="r in datos.respaldos" :key="r.id"><td>{{ fechaHora(r.fecha) }}<div class="xs muted">{{ r.tipo }} · {{ mb(r.tamano) }}</div></td><td><span class="chip" :class="r.copia_externa ? 'ok' : ''">{{ r.copia_externa ? 'Externa ✓' : 'Solo local' }}</span></td>
            <td class="actions"><template v-if="r.disponible"><button class="btn sm ghost icon" title="Descargar" @click="bajar(r)"><Icono n="bajar"/></button><button class="btn sm" @click="restaurar(r)">Restaurar</button></template><span v-else class="muted xs">no disponible</span></td></tr>
          <tr v-if="!datos.respaldos.length"><td class="empty">Todavía no hay respaldos.</td></tr></tbody></table></div></div>
      </div>
    </div>`,
};

// ───────────────────────── Configuración ─────────────────────────
export const Configuracion = {
  components: { Crud, Auditoria, Respaldos },
  setup() {
    const tab = ref('negocio'), cfg = reactive({}), cargando = ref(true), usuarios = ref([]), probando = ref(false);
    const TABS = [['negocio', 'Negocio'], ['ventas', 'Ventas y caja'], ['cajon', 'Cajón monedero'], ['impuestos', 'Impuestos'], ['medios', 'Medios de pago'], ['catalogos', 'Categorías y proveedores'], ['usuarios', 'Usuarios'], ['respaldos', 'Respaldos'], ['auditoria', 'Auditoría']];
    async function cargar() { await cargarConfig(); Object.assign(cfg, store.config); await cargarCatalogos(); cargando.value = false; }
    async function cargarUsuarios() { try { usuarios.value = await api.get('/api/usuarios'); } catch (e) { errorToast(e); } }
    onMounted(() => { cargar(); cargarUsuarios(); });
    async function guardar(claves) {
      const valores = {}; for (const k of claves) { const v = cfg[k]; valores[k] = typeof v === 'boolean' ? v : String(v ?? ''); }
      try { await api.put('/api/config', { valores }); await cargarConfig(); toast('Configuración guardada.', 'ok'); } catch (e) { errorToast(e); }
    }
    const bool = k => computed({ get: () => cfg[k] === '1', set: v => { cfg[k] = v ? '1' : '0'; } });
    const b = { permitir_stock_negativo: bool('permitir_stock_negativo'), exigir_pin_quitar_linea: bool('exigir_pin_quitar_linea'), retiro_requiere_autorizacion: bool('retiro_requiere_autorizacion') };
    function logo(e) {
      const file = e.target.files[0]; if (!file) return;
      const img = new Image(), url = URL.createObjectURL(file);
      img.onload = () => {
        const max = 160, esc = Math.min(1, max / Math.max(img.width, img.height)), c = document.createElement('canvas');
        c.width = Math.round(img.width * esc); c.height = Math.round(img.height * esc);
        c.getContext('2d').drawImage(img, 0, 0, c.width, c.height); cfg.negocio_logo = c.toDataURL('image/png'); URL.revokeObjectURL(url);
      };
      img.onerror = () => toast('No se pudo leer la imagen.', 'error'); img.src = url;
    }
    async function probarCajon() {
      await guardar(['cajon_modo', 'cajon_puerto']); probando.value = true;
      try { const r = await api.post('/api/cajon/abrir', { motivo: 'Prueba de configuración' }); toast(r.ok ? 'Se envió la orden: el cajón debería abrirse.' : r.mensaje, r.ok ? 'ok' : 'error', 7000); } catch (e) { errorToast(e); }
      probando.value = false;
    }

    // ── catálogos
    const SI_NO = v => v ? 'ok' : '';
    const impuestos = {
      columnas: [{ key: 'nombre', titulo: 'Nombre' }, { key: 'tipo', titulo: 'Tipo' }, { key: 'tarifa_pct', titulo: 'Tarifa', num: true, fmt: v => v + ' %' }, { key: 'valor_fijo', titulo: 'Valor fijo por unidad', num: true, fmt: v => v ? peso(v) : '—' }, { key: 'activo', titulo: 'Estado', chip: SI_NO, fmt: v => v ? 'Activo' : 'Inactivo' }],
      campos: [{ key: 'nombre', label: 'Nombre', tipo: 'texto' }, { key: 'tipo', label: 'Tipo', tipo: 'select', opciones: [['IVA', 'IVA'], ['INC', 'Impuesto al consumo'], ['BOLSA', 'Bolsa plástica'], ['OTRO', 'Otro']], defecto: 'IVA' },
        { key: 'tarifa_pct', label: 'Tarifa (%) incluida en el precio', tipo: 'numero', defecto: 0 }, { key: 'valor_fijo', label: 'o valor fijo por unidad ($)', tipo: 'numero', defecto: 0, ayuda: 'Para impuestos de valor fijo (p. ej. bolsas). Si lo llena, se usa en vez de la tarifa.' },
        { key: 'activo', label: 'Activo', tipo: 'check', defecto: true, soloAlEditar: true }],
      guardar: async (d, id) => { const c = { nombre: d.nombre, tipo: d.tipo, tarifa_pct: Number(d.tarifa_pct) || 0, valor_fijo: Number(d.valor_fijo) || 0, activo: d.activo }; if (id) await api.put('/api/impuestos/' + id, c); else await api.post('/api/impuestos', c); await cargarCatalogos(); toast('Guardado.', 'ok'); },
    };
    const medios = {
      columnas: [{ key: 'nombre', titulo: 'Nombre' }, { key: 'tipo', titulo: 'Tipo', fmt: v => v === 'efectivo' ? 'Efectivo' : 'Banco' }, { key: 'requiere_referencia', titulo: 'Pide referencia', fmt: v => v ? 'Sí' : 'No' }, { key: 'activo', titulo: 'Estado', chip: SI_NO, fmt: v => v ? 'Activo' : 'Inactivo' }],
      campos: [{ key: 'nombre', label: 'Nombre', tipo: 'texto', ayuda: 'Ej.: Nequi, Daviplata, Bancolombia' }, { key: 'tipo', label: 'Tipo', tipo: 'select', opciones: [['banco', 'Banco / datáfono / transferencia'], ['efectivo', 'Efectivo']], defecto: 'banco', soloAlCrear: true },
        { key: 'requiere_referencia', label: 'Exigir número de aprobación / referencia al cobrar', tipo: 'check' }, { key: 'activo', label: 'Activo', tipo: 'check', defecto: true, soloAlEditar: true }],
      guardar: async (d, id) => { const c = { nombre: d.nombre, tipo: d.tipo, requiere_referencia: d.requiere_referencia, activo: d.activo }; if (id) await api.put('/api/medios-pago/' + id, c); else await api.post('/api/medios-pago', c); await cargarCatalogos(); toast('Guardado.', 'ok'); },
    };
    const categorias = {
      columnas: [{ key: 'nombre', titulo: 'Categoría' }, { key: 'padre_id', titulo: 'Dentro de', fmt: v => store.cat.categorias.find(c => c.id === v)?.nombre || '—' }],
      campos: [{ key: 'nombre', label: 'Nombre', tipo: 'texto' }, { key: 'padre_id', label: 'Dentro de la categoría', tipo: 'select', opciones: [['', 'Ninguna (categoría principal)']], defecto: '' }],
      guardar: async (d, id) => { const c = { nombre: d.nombre, padre_id: d.padre_id || null }; if (id) await api.put('/api/categorias/' + id, c); else await api.post('/api/categorias', c); await cargarCatalogos(); toast('Guardado.', 'ok'); },
      borrar: async id => { await api.del('/api/categorias/' + id); await cargarCatalogos(); toast('Categoría eliminada.', 'ok'); },
    };
    const catCampos = computed(() => categorias.campos.map(c => c.key === 'padre_id' ? { ...c, opciones: [['', 'Ninguna (categoría principal)'], ...store.cat.categorias.map(x => [x.id, x.nombre])] } : c));
    const proveedores = {
      columnas: [{ key: 'nombre', titulo: 'Proveedor' }, { key: 'nit', titulo: 'NIT' }, { key: 'telefono', titulo: 'Teléfono' }, { key: 'contacto', titulo: 'Contacto' }, { key: 'activo', titulo: 'Estado', chip: SI_NO, fmt: v => v ? 'Activo' : 'Inactivo' }],
      campos: [{ key: 'nombre', label: 'Nombre', tipo: 'texto' }, { key: 'nit', label: 'NIT', tipo: 'texto' }, { key: 'telefono', label: 'Teléfono', tipo: 'texto' }, { key: 'email', label: 'Correo', tipo: 'texto' }, { key: 'contacto', label: 'Persona de contacto', tipo: 'texto' }, { key: 'activo', label: 'Activo', tipo: 'check', defecto: true, soloAlEditar: true }],
      guardar: async (d, id) => { if (id) await api.put('/api/proveedores/' + id, d); else await api.post('/api/proveedores', d); await cargarCatalogos(); toast('Guardado.', 'ok'); },
    };
    const usr = {
      columnas: [{ key: 'nombre', titulo: 'Nombre' }, { key: 'usuario', titulo: 'Usuario' }, { key: 'rol', titulo: 'Rol', fmt: v => v === 'admin' ? 'Administrador' : 'Cajero' }, { key: 'tiene_pin', titulo: 'PIN', fmt: v => v ? 'Sí' : 'No' }, { key: 'activo', titulo: 'Estado', chip: SI_NO, fmt: v => v ? 'Activo' : 'Inactivo' }],
      campos: [{ key: 'nombre', label: 'Nombre completo', tipo: 'texto' }, { key: 'usuario', label: 'Usuario para ingresar', tipo: 'texto', soloAlCrear: true }, { key: 'rol', label: 'Rol', tipo: 'select', opciones: [['cajero', 'Cajero (vende y cierra su caja)'], ['admin', 'Administrador (todo)']], defecto: 'cajero' },
        { key: 'password', label: 'Contraseña', tipo: 'password', ayuda: 'Mínimo 6 caracteres. Al editar, déjela vacía para no cambiarla.' }, { key: 'pin', label: 'PIN (4 a 6 números)', tipo: 'password', ayuda: 'Obligatorio para administradores; sirve para autorizar y desbloquear.' },
        { key: 'activo', label: 'Activo', tipo: 'check', defecto: true, soloAlEditar: true }],
      guardar: async (d, id) => { const c = { nombre: d.nombre, rol: d.rol, activo: d.activo }; if (d.password) c.password = d.password; if (d.pin) c.pin = d.pin;
        if (id) await api.put('/api/usuarios/' + id, c); else await api.post('/api/usuarios', { ...c, usuario: d.usuario }); await cargarUsuarios(); toast('Guardado.', 'ok'); },
    };
    return { tab, TABS, cfg, cargando, usuarios, probando, b, store, guardar, logo, probarCajon, impuestos, medios, categorias, catCampos, proveedores, usr, setTema };
  },
  template: `
    <div class="page" v-if="!cargando">
      <div class="tabs"><button v-for="t in TABS" :key="t[0]" :class="{ on: tab === t[0] }" @click="tab = t[0]">{{ t[1] }}</button></div>

      <div v-if="tab === 'negocio'" class="card stack" style="max-width:760px">
        <h2>Datos del negocio</h2><p class="muted small">Aparecen en los recibos, los informes y el menú.</p>
        <div class="grid c2"><div class="field"><label>Nombre del supermercado</label><input class="input" v-model="cfg.negocio_nombre"></div><div class="field"><label>NIT</label><input class="input" v-model="cfg.negocio_nit"></div>
          <div class="field"><label>Dirección</label><input class="input" v-model="cfg.negocio_direccion"></div><div class="field"><label>Teléfono</label><input class="input" v-model="cfg.negocio_telefono"></div></div>
        <div class="field"><label>Logo (opcional)</label><div class="row"><div class="brand"><div class="logo" style="width:56px;height:56px"><img v-if="cfg.negocio_logo" :src="cfg.negocio_logo" alt=""><Icono v-else n="tienda" class="ico lg"/></div></div>
          <input type="file" accept="image/*" @change="logo" class="input" style="max-width:300px;height:auto;padding:8px"><button class="btn ghost" v-if="cfg.negocio_logo" @click="cfg.negocio_logo = ''">Quitar</button></div></div>
        <div><button class="btn primary" @click="guardar(['negocio_nombre', 'negocio_nit', 'negocio_direccion', 'negocio_telefono', 'negocio_logo'])">Guardar</button></div>
      </div>

      <div v-if="tab === 'ventas'" class="grid c2" style="align-items:start">
        <div class="card stack"><h2>Ventas</h2>
          <div class="field"><label>Descuento máximo que puede dar un cajero sin autorización (%)</label><input class="input num" type="number" min="0" max="100" v-model="cfg.descuento_max_pct_cajero" style="max-width:140px"><span class="hint">Más de esto pide el PIN del administrador.</span></div>
          <div class="field"><label>Prefijo de los tiquetes</label><input class="input" v-model="cfg.prefijo_venta" style="max-width:140px"><span class="hint">Siguiente tiquete: {{ cfg.prefijo_venta }}-{{ String(cfg.consecutivo_venta).padStart(6, '0') }}</span></div>
          <label class="check"><input type="checkbox" v-model="b.permitir_stock_negativo.value"> Permitir vender aunque el sistema diga que no hay existencias</label>
          <label class="check"><input type="checkbox" v-model="b.exigir_pin_quitar_linea.value"> Pedir PIN del administrador para quitar un producto del carrito</label>
          <div><button class="btn primary" @click="guardar(['descuento_max_pct_cajero', 'prefijo_venta', 'permitir_stock_negativo', 'exigir_pin_quitar_linea'])">Guardar</button></div></div>
        <div class="card stack"><h2>Caja y seguridad</h2>
          <label class="check"><input type="checkbox" v-model="b.retiro_requiere_autorizacion.value"> Los retiros de efectivo requieren PIN del administrador</label>
          <div class="field"><label>Denominaciones para contar el efectivo</label><input class="input" v-model="cfg.denominaciones"><span class="hint">Separadas por comas, de mayor a menor.</span></div>
          <div class="grid c2"><div class="field"><label>Bloquear pantalla tras (minutos)</label><input class="input num" type="number" min="0" v-model="cfg.bloqueo_minutos"><span class="hint">0 = nunca</span></div>
            <div class="field"><label>Recordar conteos con (días)</label><input class="input num" type="number" min="0" v-model="cfg.conteo_recordatorio_dias"></div></div>
          <div><button class="btn primary" @click="guardar(['retiro_requiere_autorizacion', 'denominaciones', 'bloqueo_minutos', 'conteo_recordatorio_dias'])">Guardar</button></div></div>
      </div>

      <div v-if="tab === 'cajon'" class="card stack" style="max-width:760px">
        <h2>Cajón monedero</h2><p class="muted small">Se abre solo al cobrar en efectivo, al abrir la caja y en los retiros. Si falla, la venta no se detiene.</p>
        <div class="field"><label>¿Cómo está conectado el cajón?</label><select class="input" v-model="cfg.cajon_modo">
          <option value="ninguno">No tengo cajón / no abrir</option><option value="serial">Cajón USB o serial propio (puerto COM)</option>
          <option value="escpos_windows">Conectado a una impresora térmica instalada en Windows</option><option value="escpos_archivo">Impresora como archivo / dispositivo (avanzado)</option></select></div>
        <div class="field" v-if="cfg.cajon_modo !== 'ninguno'"><label>{{ { serial: 'Puerto (ej.: COM3 o /dev/ttyUSB0)', escpos_windows: 'Nombre exacto de la impresora en Windows', escpos_archivo: 'Ruta del dispositivo (ej.: /dev/usb/lp0 o LPT1)' }[cfg.cajon_modo] }}</label><input class="input" v-model="cfg.cajon_puerto"></div>
        <div class="alert info" v-if="cfg.cajon_modo === 'escpos_windows'"><Icono n="info"/>La mayoría de los cajones se abren a través de la impresora (cable RJ11). Si usted todavía no tiene impresora, necesita un cajón con conexión USB.</div>
        <div class="row"><button class="btn primary" @click="guardar(['cajon_modo', 'cajon_puerto'])">Guardar</button><button class="btn" :disabled="cfg.cajon_modo === 'ninguno' || probando" @click="probarCajon">Guardar y probar apertura</button></div>
      </div>

      <Crud v-if="tab === 'impuestos'" singular="impuesto" :filas="store.cat.impuestos" v-bind="impuestos" nota="Todos los precios se manejan con el impuesto incluido. Confirme las tarifas vigentes con su contador."/>
      <Crud v-if="tab === 'medios'" singular="medio de pago" :filas="store.cat.medios_pago" v-bind="medios" nota="El efectivo y los medios bancarios se cuadran por separado al cerrar la caja."/>
      <div v-if="tab === 'catalogos'" class="grid c2" style="align-items:start"><div><h3 style="margin-bottom:10px">Categorías</h3><Crud singular="categoría" :filas="store.cat.categorias" v-bind="categorias" :campos="catCampos"/></div>
        <div><h3 style="margin-bottom:10px">Proveedores</h3><Crud singular="proveedor" :filas="store.cat.proveedores" v-bind="proveedores"/></div></div>
      <Crud v-if="tab === 'usuarios'" singular="usuario" :filas="usuarios" v-bind="usr" nota="Los cajeros venden y cierran su caja. Los administradores ven todo y autorizan con su PIN."/>
      <Respaldos v-if="tab === 'respaldos'" :cfg="cfg" @guardar="guardar"/>
      <Auditoria v-if="tab === 'auditoria'"/>
    </div>`,
};

// ───────────────────────── Mi cuenta ─────────────────────────
export const Cuenta = {
  setup() {
    const f = reactive({ password_actual: '', password_nueva: '', pin_nuevo: '' }), cargando = ref(false);
    async function guardar() {
      cargando.value = true;
      try { await api.put('/api/auth/credenciales', { password_actual: f.password_actual, password_nueva: f.password_nueva || null, pin_nuevo: f.pin_nuevo || null });
        toast('Datos actualizados.', 'ok'); f.password_actual = f.password_nueva = f.pin_nuevo = ''; } catch (e) { errorToast(e); } finally { cargando.value = false; }
    }
    return { f, cargando, store, guardar, setTema };
  },
  template: `
    <div class="page"><div style="max-width:560px;margin:0 auto" class="stack lg">
      <div class="card stack"><h2>{{ store.usuario.nombre }}</h2><div class="muted">{{ store.usuario.usuario }} · {{ store.usuario.rol === 'admin' ? 'Administrador' : 'Cajero' }}</div></div>
      <div class="card stack"><h3>Cambiar contraseña o PIN</h3>
        <div class="field"><label>Contraseña actual</label><input class="input" type="password" v-model="f.password_actual" autocomplete="current-password"></div>
        <div class="field"><label>Contraseña nueva (opcional)</label><input class="input" type="password" v-model="f.password_nueva" autocomplete="new-password"></div>
        <div class="field"><label>PIN nuevo, 4 a 6 números (opcional)</label><input class="input" type="password" inputmode="numeric" maxlength="6" v-model="f.pin_nuevo"></div>
        <button class="btn primary" :disabled="cargando || !f.password_actual || (!f.password_nueva && !f.pin_nuevo)" @click="guardar">Guardar cambios</button></div>
      <div class="card row between"><div><h3>Apariencia</h3><div class="muted small">Tema claro u oscuro</div></div>
        <div class="seg"><button :class="{ on: store.tema === 'claro' }" @click="setTema('claro')">Claro</button><button :class="{ on: store.tema === 'oscuro' }" @click="setTema('oscuro')">Oscuro</button></div></div>
    </div></div>`,
};
