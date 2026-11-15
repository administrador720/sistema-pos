// Conexión con el programa del computador: dirección, llave del celular, sesión del administrador
const { reactive } = Vue;

export const API_APP = 1;   // versión del protocolo que entiende esta app (debe coincidir con la del programa)
const K = { servidor: 'posm_servidor', llave: 'posm_llave', sesion: 'posm_sesion', negocio: 'posm_negocio', usuario: 'posm_usuario' };
const leer = k => { try { return localStorage.getItem(k) || ''; } catch (e) { return ''; } };
const guardar = (k, v) => { try { if (v) localStorage.setItem(k, v); else localStorage.removeItem(k); } catch (e) { /* */ } };

export const nativo = () => !!(window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform());

export const estado = reactive({
  nativo: nativo(),
  // en la app instalada la dirección se guarda al vincular; abierta desde el navegador es el propio servidor
  servidor: nativo() ? leer(K.servidor) : location.origin,
  llave: leer(K.llave), sesion: leer(K.sesion), negocio: leer(K.negocio),
  usuario: (() => { try { return JSON.parse(leer(K.usuario) || 'null'); } catch (e) { return null; } })(),
  cargando: 0,
});

export class ErrorApp extends Error {
  constructor(mensaje, codigo = null, status = 0) { super(mensaje); this.codigo = codigo; this.status = status; }
}

export function normalizarServidor(texto) {
  let t = String(texto || '').trim().replace(/\/+$/, '');
  if (!t) return '';
  if (!/^https?:\/\//i.test(t)) t = 'http://' + t;
  if (!/:\d+$/.test(t)) t += ':8766';
  return t;
}
export function guardarVinculo({ servidor, llave, negocio }) {
  if (servidor && estado.nativo) { estado.servidor = servidor; guardar(K.servidor, servidor); }
  estado.llave = llave; guardar(K.llave, llave);
  estado.negocio = negocio || ''; guardar(K.negocio, estado.negocio);
}
export function guardarSesion(token, usuario) {
  estado.sesion = token; estado.usuario = usuario;
  guardar(K.sesion, token); guardar(K.usuario, usuario ? JSON.stringify(usuario) : '');
}
export const cerrarSesion = () => guardarSesion('', null);
export function olvidarDispositivo() { cerrarSesion(); estado.llave = ''; guardar(K.llave, ''); }

export async function llamar(metodo, ruta, cuerpo = null, { silencioso = false } = {}) {
  if (!estado.servidor) throw new ErrorApp('Falta la dirección del computador.', 'SIN_SERVIDOR');
  const cab = { Accept: 'application/json' };
  if (cuerpo !== null) cab['Content-Type'] = 'application/json';
  if (estado.llave) cab['X-Dispositivo'] = estado.llave;
  if (estado.sesion) cab.Authorization = 'Bearer ' + estado.sesion;
  const ctl = new AbortController(), t = setTimeout(() => ctl.abort(), 20000);
  if (!silencioso) estado.cargando++;
  let r;
  try {
    r = await fetch(estado.servidor + ruta, { method: metodo, headers: cab, body: cuerpo !== null ? JSON.stringify(cuerpo) : undefined, signal: ctl.signal });
  } catch (e) {
    throw new ErrorApp('No se pudo conectar con el computador. Revise que esté encendido, con el sistema abierto y que el celular use el mismo Wi-Fi.', 'SIN_CONEXION');
  } finally { clearTimeout(t); if (!silencioso) estado.cargando--; }
  let datos = null;
  if ((r.headers.get('content-type') || '').includes('json')) { try { datos = await r.json(); } catch (e) { datos = null; } }
  if (!r.ok) {
    const err = new ErrorApp(datos?.detalle || `Error ${r.status}`, datos?.codigo || null, r.status);
    if (err.codigo === 'DISPOSITIVO_NO_VINCULADO') { olvidarDispositivo(); location.hash = '#/vincular'; }
    else if (err.codigo === 'NO_AUTENTICADO') { cerrarSesion(); location.hash = '#/entrar'; }
    throw err;
  }
  return datos;
}
export const get = (ruta, o) => llamar('GET', ruta, null, o);
export const post = (ruta, cuerpo = {}, o) => llamar('POST', ruta, cuerpo, o);
export const del = (ruta, o) => llamar('DELETE', ruta, null, o);
export const consulta = o => '?' + new URLSearchParams(Object.fromEntries(Object.entries(o).filter(([, v]) => v !== null && v !== undefined && v !== ''))).toString();
