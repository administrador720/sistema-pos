// Lector de códigos de barras con la cámara. En la app instalada usa el lector de Google (ML Kit) a través de Capacitor;
// en el navegador no hay cámara (el celular se conecta por http, que el navegador no deja usar para la cámara): se escribe el
// código o se usa un lector Bluetooth/USB, que escribe como un teclado.
import { nativo } from './api.js';

const FORMATOS = ['Ean13', 'Ean8', 'UpcA', 'UpcE', 'Code128', 'Code39', 'Itf', 'Codabar', 'QrCode'];

function plugin() {
  const cap = window.Capacitor;
  if (!cap || (cap.isPluginAvailable && !cap.isPluginAvailable('BarcodeScanner'))) return null;   // el plugin nativo no está en la app
  return (cap.Plugins && cap.Plugins.BarcodeScanner) || (cap.registerPlugin ? cap.registerPlugin('BarcodeScanner') : null);
}
export const hayCamara = () => nativo() && !!plugin();

/** Abre el lector y devuelve el texto del código, o null si la persona cancela. Lanza un Error con un mensaje claro. */
export async function escanear({ soloQR = false } = {}) {
  const BS = plugin();
  if (!BS) throw new Error('Este celular no tiene el lector de cámara. Escriba el código.');
  try {
    if (BS.isGoogleBarcodeScannerModuleAvailable) {   // Android: el lector de Google se descarga una vez
      const { available } = await BS.isGoogleBarcodeScannerModuleAvailable();
      if (!available) await BS.installGoogleBarcodeScannerModule();
    }
    const r = await BS.scan({ formats: soloQR ? ['QrCode'] : FORMATOS });
    const b = (r.barcodes || [])[0];
    return b ? String(b.rawValue ?? b.displayValue ?? '').trim() || null : null;
  } catch (e) {
    const m = String(e && (e.message || e)).toLowerCase();
    if (m.includes('cancel') || m.includes('closed') || m.includes('back')) return null;   // la persona cerró el lector
    if (m.includes('permission')) throw new Error('Falta el permiso de la cámara. Actívelo en Ajustes → Aplicaciones → POS Móvil.');
    if (m.includes('module') || m.includes('play services')) throw new Error('El lector de Google aún se está descargando. Intente de nuevo en un momento.');
    throw new Error('No se pudo abrir la cámara. ' + (e && e.message ? e.message : ''));
  }
}
