"""Cajón monedero. Tres formas de abrirlo, según cómo esté conectado:

* ``serial``          → cajón USB/serial con su propio puerto (COM3, /dev/ttyUSB0): se envía un pulso.
* ``escpos_windows``  → cajón conectado a una impresora térmica (RJ11) instalada en Windows: se envía el
                         comando ESC/POS a la impresora por su nombre (requiere pywin32).
* ``escpos_archivo``  → impresora/dispositivo accesible como archivo (``/dev/usb/lp0``, ``LPT1``, ``\\\\.\\COM3``).
* ``ninguno``         → no hace nada (la venta nunca se bloquea por el cajón).

Abrir el cajón es siempre «mejor esfuerzo»: un fallo se registra pero no interrumpe la venta.
"""
from __future__ import annotations

import logging

log = logging.getLogger("pos.cajon")

# ESC p m t1 t2: pulso en el pin 2 (el más común). Algunos cajones usan el pin 5 (m=1).
COMANDO_PIN2 = b"\x1b\x70\x00\x19\xfa"
COMANDO_PIN5 = b"\x1b\x70\x01\x19\xfa"


class Cajon:
    def abrir(self) -> tuple[bool, str]:  # pragma: no cover - interfaz
        raise NotImplementedError


class CajonNulo(Cajon):
    def abrir(self):
        return True, "Sin cajón configurado."


class CajonSerial(Cajon):
    def __init__(self, puerto: str):
        self.puerto = puerto

    def abrir(self):
        try:
            import serial  # pyserial
            with serial.Serial(self.puerto, 9600, timeout=1) as s:
                s.write(COMANDO_PIN2)
            return True, "Cajón abierto."
        except Exception as e:  # noqa: BLE001 - hardware: cualquier error es "no se pudo"
            log.warning("Cajón serial %s: %s", self.puerto, e)
            return False, f"No se pudo abrir el cajón ({self.puerto}): {e}"


class CajonEscPosArchivo(Cajon):
    def __init__(self, ruta: str):
        self.ruta = ruta

    def abrir(self):
        try:
            with open(self.ruta, "wb") as f:
                f.write(COMANDO_PIN2)
            return True, "Cajón abierto."
        except OSError as e:
            log.warning("Cajón ESC/POS %s: %s", self.ruta, e)
            return False, f"No se pudo abrir el cajón ({self.ruta}): {e.strerror or e}"


class CajonEscPosWindows(Cajon):
    def __init__(self, impresora: str):
        self.impresora = impresora

    def abrir(self):
        try:
            import win32print  # type: ignore[import-not-found]
            h = win32print.OpenPrinter(self.impresora)
            try:
                win32print.StartDocPrinter(h, 1, ("Apertura de cajón", None, "RAW"))
                win32print.StartPagePrinter(h)
                win32print.WritePrinter(h, COMANDO_PIN2)
                win32print.EndPagePrinter(h)
                win32print.EndDocPrinter(h)
            finally:
                win32print.ClosePrinter(h)
            return True, "Cajón abierto."
        except Exception as e:  # noqa: BLE001
            log.warning("Cajón impresora %s: %s", self.impresora, e)
            return False, f"No se pudo abrir el cajón (impresora «{self.impresora}»): {e}"


def crear(modo: str, puerto: str) -> Cajon:
    puerto = (puerto or "").strip()
    if modo == "serial" and puerto:
        return CajonSerial(puerto)
    if modo == "escpos_archivo" and puerto:
        return CajonEscPosArchivo(puerto)
    if modo == "escpos_windows" and puerto:
        return CajonEscPosWindows(puerto)
    return CajonNulo()
