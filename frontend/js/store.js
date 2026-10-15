// Estado global compartido por todas las pantallas
import { api, sesion, query } from './api.js';
import { descargarBlob } from './util.js';

const { reactive } = Vue;

function leer(clave, defecto) { try { return localStorage.getItem(clave) ?? defecto; } catch (e) { return defecto; } }

export const store = reactive({
  configurado: null,          // null = aún no se sabe
  usuario: null,
  config: {},
  cat: { categorias: [], proveedores: [], impuestos: [], medios_pago: [], caja: null },
  turno: null, turnoEsMio: false, resumen: null,
  alertas: 0,
  tema: document.documentElement.getAttribute('data-theme') === 'dark' ? 'oscuro' : 'claro',
  escritorio: new URLSearchParams(location.search).has('escritorio') || leer('pos_escritorio', '') === '1',
  mini: false,
  bloqueado: false,
  toasts: [],
  pin: { abierto: false, detalle: '', incorrecto: false, resolver: null },
  confirmacion: null,
  pregunta: null,
  visor: null,
  ruta: '',
});
if (new URLSearchParams(location.search).has('escritorio')) { try { localStorage.setItem('pos_escritorio', '1'); } catch (e) { /* */ } }

export const esAdmin = () => store.usuario?.rol === 'admin';

let idToast = 0;
export function toast(mensaje, tipo = 'info', ms = 4500) {
  const id = ++idToast;
  store.toasts.push({ id, mensaje, tipo });
  setTimeout(() => { store.toasts = store.toasts.filter(t => t.id !== id); }, ms);
}
export function errorToast(e) {
  if (e && e.codigo === 'CANCELADO') return;
  toast(e?.message || 'Ocurrió un error.', 'error', 6000);
}

export function pedirPin(detalle, incorrecto = false) {
  return new Promise(resolver => { store.pin = { abierto: true, detalle, incorrecto, resolver }; });
}

export function confirmar(titulo, mensaje, { peligro = false, textoOk = 'Confirmar', textoNo = 'Cancelar' } = {}) {
  return new Promise(resolver => { store.confirmacion = { titulo, mensaje, peligro, textoOk, textoNo, resolver }; });
}

export function pedirTexto(titulo, etiqueta, { valor = '', multilinea = false, textoOk = 'Aceptar', obligatorio = true, ayuda = '' } = {}) {
  return new Promise(resolver => { store.pregunta = { titulo, etiqueta, valor, multilinea, textoOk, obligatorio, ayuda, resolver }; });
}

export function setTema(tema) {
  store.tema = tema;
  document.documentElement.setAttribute('data-theme', tema === 'oscuro' ? 'dark' : 'light');
  try { localStorage.setItem('pos_tema', tema); } catch (e) { /* */ }
}

export async function cargarCatalogos() { store.cat = await api.get('/api/catalogos'); }
export async function cargarConfig() { store.config = await api.get('/api/config'); }
export async function refrescarTurno() {
  const r = await api.get('/api/turnos/actual');
  store.turno = r.turno; store.turnoEsMio = !!r.es_mio; store.resumen = r.resumen || null;
  return r;
}
export async function refrescarAlertas() {
  if (!esAdmin()) { store.alertas = 0; return; }
  try { store.alertas = (await api.get('/api/inventario/alertas')).total; } catch (e) { /* no crítico */ }
}
export async function iniciarSesionCargada() {
  store.usuario = await api.get('/api/auth/yo');
  await Promise.all([cargarConfig(), cargarCatalogos(), refrescarTurno()]);
  refrescarAlertas();
}
export function cerrarSesionLocal() {
  sesion.limpiar(); store.usuario = null; store.turno = null; store.bloqueado = false;
  location.hash = '#/';
}

// Exporta un informe: en la ventana de escritorio lo guarda y abre; en el navegador lo descarga.
export async function exportarArchivo(urlBase, parametros, formato, nombreBase) {
  const ext = formato === 'xlsx' ? 'xlsx' : 'pdf';
  const url = urlBase + query({ ...parametros, formato });
  if (store.escritorio) {
    const r = await api.get(url + '&guardar=true');
    toast('Guardado en: ' + r.ruta, 'ok', 9000);
    api.post('/api/sistema/abrir', { ruta: r.ruta }).catch(() => {});
  } else {
    descargarBlob(await api.blob(url), `${nombreBase}.${ext}`);
  }
}

export async function verPdf(titulo, url) {
  store.visor = { titulo, url: null, cargando: true };
  try {
    const blob = await api.blob(url);
    store.visor = { titulo, url: URL.createObjectURL(blob), blob, cargando: false };
  } catch (e) { store.visor = null; errorToast(e); }
}
