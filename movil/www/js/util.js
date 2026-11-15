// Formatos y utilidades (mismas reglas que el programa del computador)
export const miles = n => String(Math.abs(Math.round(Number(n) || 0))).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
export const peso = n => (n === null || n === undefined || n === '' || Number.isNaN(Number(n))) ? '' : (Math.round(n) < 0 ? '-$ ' : '$ ') + miles(n);

// 5 → «5», 1,25 → «1,25»
export function cantidadTxt(n) {
  if (n === null || n === undefined || n === '') return '';
  const v = Math.round(Number(n) * 1000) / 1000;
  const [ent, dec] = Math.abs(v).toFixed(3).replace(/0+$/, '').replace(/\.$/, '').split('.');
  return (v < 0 ? '-' : '') + miles(ent) + (dec ? ',' + dec : '');
}
export function kilos(n) {
  if (n === null || n === undefined || n === '') return '';
  const v = Math.round(Number(n) * 1000) / 1000;
  return (v < 0 ? '-' : '') + miles(Math.trunc(Math.abs(v))) + ',' + Math.abs(v).toFixed(3).split('.')[1] + ' kg';
}
export const conUnidad = (n, unidad) => unidad === 'kg' ? kilos(n) : cantidadTxt(n);
// Precio × cantidad en pesos con aritmética entera, igual que el servidor
export const valorLinea = (precio, cantidad) => Math.floor((precio * Math.round(Number(cantidad) * 1000) + 500) / 1000);
export const bruta = it => it.valor ? it.valor : valorLinea(it.precio, it.cantidad);
// «1,25» o «1.25» → 1.25
export const aNumero = t => { const n = parseFloat(String(t ?? '').replace(',', '.')); return Number.isFinite(n) ? n : null; };

const pad = x => String(x).padStart(2, '0');
export const isoHoy = (desplazar = 0) => { const d = new Date(); d.setDate(d.getDate() + desplazar); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; };
export const inicioMes = () => { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-01`; };
export function fechaHora(iso) {
  if (!iso) return '';
  const d = new Date(String(iso).replace(/(\.\d{3})\d+/, '$1'));
  const h = d.getHours();
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)} ${h % 12 || 12}:${pad(d.getMinutes())} ${h < 12 ? 'a. m.' : 'p. m.'}`;
}
export const debounce = (fn, ms = 250) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

let ctx = null;
export function pitido(tipo = 'ok') {
  try {
    ctx = ctx || new (window.AudioContext || window.webkitAudioContext)();
    const tonos = tipo === 'ok' ? [[1040, 0, .07]] : tipo === 'cobro' ? [[660, 0, .09], [880, .1, .12]] : [[220, 0, .16], [180, .2, .22]];
    for (const [f, ini, dur] of tonos) {
      const o = ctx.createOscillator(), g = ctx.createGain();
      o.type = tipo === 'error' ? 'square' : 'sine'; o.frequency.value = f;
      g.gain.setValueAtTime(0.0001, ctx.currentTime + ini);
      g.gain.exponentialRampToValueAtTime(0.12, ctx.currentTime + ini + 0.01);
      g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + ini + dur);
      o.connect(g); g.connect(ctx.destination); o.start(ctx.currentTime + ini); o.stop(ctx.currentTime + ini + dur + 0.02);
    }
  } catch (e) { /* sin audio */ }
  try { if (navigator.vibrate) navigator.vibrate(tipo === 'error' ? [60, 40, 60] : 25); } catch (e) { /* */ }
}
