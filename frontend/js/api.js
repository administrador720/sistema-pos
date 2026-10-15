// Cliente de la API local. Maneja el token, los errores en español y el PIN de administrador.

export class ApiError extends Error {
  constructor(mensaje, status, codigo, datos) { super(mensaje); this.status = status; this.codigo = codigo; this.datos = datos; }
}

let token = null;
try { token = sessionStorage.getItem('pos_token'); } catch (e) { /* sin almacenamiento */ }
export const sesion = {
  get token() { return token; },
  guardar(t) { token = t; try { sessionStorage.setItem('pos_token', t); } catch (e) { /* */ } },
  limpiar() { token = null; try { sessionStorage.removeItem('pos_token'); } catch (e) { /* */ } },
};

let manejadorPin = null;   // (detalle, incorrecto) => Promise<string|null>
let alExpirar = null;      // () => void
export function configurarApi({ pin, expirar }) { manejadorPin = pin; alExpirar = expirar; }

async function pedir(metodo, url, cuerpo, opciones = {}) {
  let pin = opciones.pin || null;
  for (let intento = 0; intento < 5; intento++) {
    const headers = {};
    if (token) headers.Authorization = 'Bearer ' + token;
    if (pin) headers['X-Autorizacion-Pin'] = pin;
    const init = { method: metodo, headers };
    if (cuerpo instanceof FormData) init.body = cuerpo;
    else if (cuerpo !== null && cuerpo !== undefined) { headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(cuerpo); }

    let resp;
    try { resp = await fetch(url, init); }
    catch (e) { throw new ApiError('No se pudo conectar con el sistema. ¿Se cerró la aplicación?', 0, 'RED'); }

    if (resp.ok) {
      if (opciones.blob) return resp.blob();
      const tipo = resp.headers.get('content-type') || '';
      return tipo.includes('json') ? resp.json() : resp.text();
    }
    const datos = await resp.json().catch(() => ({}));
    if (resp.status === 401 && datos.codigo === 'NO_AUTENTICADO') {
      if (alExpirar) alExpirar();
      throw new ApiError(datos.detalle || 'La sesión expiró.', 401, datos.codigo, datos);
    }
    if (resp.status === 403 && (datos.codigo === 'REQUIERE_AUTORIZACION' || datos.codigo === 'PIN_INCORRECTO') && manejadorPin) {
      const nuevo = await manejadorPin(datos.detalle, datos.codigo === 'PIN_INCORRECTO');
      if (nuevo) { pin = nuevo; continue; }
      throw new ApiError('Acción cancelada.', 403, 'CANCELADO', datos);
    }
    throw new ApiError(datos.detalle || `Error ${resp.status}`, resp.status, datos.codigo, datos);
  }
  throw new ApiError('Demasiados intentos.', 403, 'PIN_INCORRECTO');
}

export const api = {
  get: (url, o) => pedir('GET', url, null, o),
  post: (url, cuerpo, o) => pedir('POST', url, cuerpo === undefined ? {} : cuerpo, o),
  put: (url, cuerpo, o) => pedir('PUT', url, cuerpo, o),
  del: (url, o) => pedir('DELETE', url, null, o),
  blob: (url) => pedir('GET', url, null, { blob: true }),
  upload: (url, formData) => pedir('POST', url, formData),
};

export function query(params) {
  const q = Object.entries(params || {}).filter(([, v]) => v !== null && v !== undefined && v !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join('&');
  return q ? '?' + q : '';
}
