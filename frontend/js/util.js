// Utilidades de formato, sonido y descarga

export function miles(n) {
  const s = String(Math.abs(Math.round(Number(n) || 0)));
  return s.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
}
export function peso(n) {
  if (n === null || n === undefined || n === '' || Number.isNaN(Number(n))) return '';
  const v = Math.round(Number(n));
  return (v < 0 ? '-$ ' : '$ ') + miles(v);
}
export function entero(n) { return n === null || n === undefined ? '' : (Number(n) < 0 ? '-' : '') + miles(n); }
export function decimal(n, d = 2) {
  if (n === null || n === undefined) return '';
  return Number(n).toLocaleString('es-CO', { minimumFractionDigits: d, maximumFractionDigits: d });
}
// Cantidades: 5 → «5», 1,25 → «1,25» (hasta 3 decimales, sin ceros de sobra)
export function cantidadTxt(n) {
  if (n === null || n === undefined || n === '') return '';
  const v = Math.round(Number(n) * 1000) / 1000;
  const [ent, dec] = Math.abs(v).toFixed(3).replace(/0+$/, '').replace(/\.$/, '').split('.');
  return (v < 0 ? '-' : '') + miles(ent) + (dec ? ',' + dec : '');
}
// Kilos como los muestra una balanza: «1,250 kg»
export function kilos(n) {
  if (n === null || n === undefined || n === '') return '';
  const v = Math.round(Number(n) * 1000) / 1000;
  return (v < 0 ? '-' : '') + miles(Math.trunc(Math.abs(v))) + ',' + Math.abs(v).toFixed(3).split('.')[1] + ' kg';
}
export const conUnidad = (n, unidad) => unidad === 'kg' ? kilos(n) : cantidadTxt(n);
// Precio × cantidad en pesos con aritmética entera (igual que el servidor): 0,350 kg × $3.500 = $1.225
export function valorLinea(precio, cantidad) { return Math.floor((precio * Math.round(Number(cantidad) * 1000) + 500) / 1000); }
// Valor bruto de una línea del carrito: lo digitado en pesos («$5.000 de tomate») o precio × cantidad
export function bruta(it) { return it.valor ? it.valor : valorLinea(it.precio, it.cantidad); }
export function porcentaje(n) { return n === null || n === undefined ? '—' : String(Number(n).toFixed(1)).replace('.', ',') + ' %'; }

const pad = x => String(x).padStart(2, '0');
// El servidor manda microsegundos (2026-10-15T21:19:00.123456); algunos motores solo aceptan milisegundos
export function aFecha(iso) { return iso ? new Date(String(iso).length === 10 ? iso + 'T00:00:00' : String(iso).replace(/(\.\d{3})\d+/, '$1')) : null; }
export function fecha(iso) { const d = aFecha(iso); return d ? `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()}` : ''; }
export function hora(iso) {
  const d = aFecha(iso); if (!d) return '';
  const h = d.getHours(); return `${h % 12 || 12}:${pad(d.getMinutes())} ${h < 12 ? 'a. m.' : 'p. m.'}`;
}
export function fechaHora(iso) { return iso ? `${fecha(iso)} ${hora(iso)}` : ''; }
export function isoHoy(desplazar = 0) {
  const d = new Date(); d.setDate(d.getDate() + desplazar);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
export function inicioMes() { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-01`; }
export function diaSemana(iso) { return ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb'][aFecha(iso).getDay()]; }

export function formatear(valor, tipo) {
  if (valor === null || valor === undefined || valor === '') return '';
  switch (tipo) {
    case 'dinero': return peso(valor);
    case 'entero': return entero(valor);
    case 'cantidad': return cantidadTxt(valor);
    case 'decimal': return decimal(valor);
    case 'porcentaje': return porcentaje(valor);
    case 'fecha': return fecha(valor);
    case 'fechahora': return fechaHora(valor);
    default: return String(valor);
  }
}
export const esNumerico = tipo => ['dinero', 'entero', 'cantidad', 'decimal', 'porcentaje'].includes(tipo);

// ── Sonidos (Web Audio: no necesita archivos)
let ctx = null;
export function beep(tipo = 'ok') {
  try {
    ctx = ctx || new (window.AudioContext || window.webkitAudioContext)();
    const tonos = tipo === 'ok' ? [[1040, 0, .07]] : tipo === 'cobro' ? [[660, 0, .09], [880, .1, .12]] : [[220, 0, .16], [180, .2, .22]];
    for (const [f, ini, dur] of tonos) {
      const o = ctx.createOscillator(), g = ctx.createGain();
      o.type = tipo === 'error' ? 'square' : 'sine'; o.frequency.value = f;
      g.gain.setValueAtTime(0.0001, ctx.currentTime + ini);
      g.gain.exponentialRampToValueAtTime(tipo === 'error' ? 0.08 : 0.12, ctx.currentTime + ini + 0.01);
      g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + ini + dur);
      o.connect(g); g.connect(ctx.destination); o.start(ctx.currentTime + ini); o.stop(ctx.currentTime + ini + dur + 0.02);
    }
  } catch (e) { /* sin audio: no pasa nada */ }
}

export function descargarBlob(blob, nombre) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = nombre;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

export function debounce(fn, ms = 250) {
  let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

// Colores del tema actual (para los gráficos)
export function css(nombre) { return getComputedStyle(document.documentElement).getPropertyValue(nombre).trim(); }

export function iniciales(nombre) {
  return (nombre || '?').split(/\s+/).filter(Boolean).slice(0, 2).map(p => p[0].toUpperCase()).join('');
}
export function deepCopy(o) { return JSON.parse(JSON.stringify(o)); }
