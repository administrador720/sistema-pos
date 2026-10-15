"""Punto de entrada del POS: arranca el servidor local y abre la ventana de escritorio.

    python launcher.py                # ventana de escritorio (pywebview)
    python launcher.py --navegador    # abre el navegador predeterminado en vez de la ventana
    python launcher.py --sin-ventana  # solo el servidor (útil para pruebas)
    python launcher.py --pantalla-completa

Todo corre en este computador: el servidor solo escucha en 127.0.0.1 y la información vive en
`C:\\ProgramData\\POSSupermercado` (Windows) o `~/.local/share/pos-supermercado` (Linux).
"""
from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from app import config  # noqa: E402

log = logging.getLogger("pos.launcher")


def configurar_logs():
    destino = config.directorio_datos() / "pos.log"
    manejador = logging.handlers.RotatingFileHandler(destino, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    manejador.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    raiz.addHandler(manejador)
    if sys.stdout and sys.stdout.isatty():
        raiz.addHandler(logging.StreamHandler())


def responde(puerto: int) -> bool:
    """¿Ya hay un POS corriendo en este puerto?"""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/api/salud", timeout=1.5) as r:
            return bool(json.loads(r.read()).get("ok"))
    except Exception:  # noqa: BLE001
        return False


def puerto_disponible(puerto: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", puerto))
            return True
        except OSError:
            return False


def arrancar_servidor(puerto: int):
    import uvicorn

    from app.main import app
    servidor = uvicorn.Server(uvicorn.Config(app, host=config.HOST, port=puerto, log_level="warning", log_config=None))
    hilo = threading.Thread(target=servidor.run, daemon=True, name="pos-servidor")
    hilo.start()
    for _ in range(100):
        if servidor.started:
            return servidor, hilo
        if not hilo.is_alive():
            raise RuntimeError("El servidor no pudo arrancar (revise pos.log).")
        time.sleep(0.1)
    raise RuntimeError("El servidor tardó demasiado en arrancar.")


def abrir_ventana(url: str, pantalla_completa: bool) -> bool:
    """Abre la ventana nativa. Devuelve False si pywebview no está disponible."""
    try:
        import webview
    except Exception as e:  # noqa: BLE001
        log.warning("pywebview no disponible (%s): se usará el navegador", e)
        return False
    try:
        webview.settings["ALLOW_DOWNLOADS"] = True
    except Exception:  # noqa: BLE001
        pass
    try:
        webview.create_window(config.NOMBRE_APP, url + "?escritorio=1", width=1366, height=820, min_size=(1100, 700),
                              fullscreen=pantalla_completa, text_select=False)
        webview.start()      # bloquea hasta que se cierra la ventana
    except Exception as e:  # noqa: BLE001 - sin motor gráfico (WebView2/GTK/Qt) no se puede abrir la ventana nativa
        log.warning("No se pudo abrir la ventana de escritorio (%s): se usará el navegador", e)
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=config.NOMBRE_APP)
    ap.add_argument("--puerto", type=int, default=config.PUERTO)
    ap.add_argument("--navegador", action="store_true", help="usar el navegador en vez de la ventana de escritorio")
    ap.add_argument("--sin-ventana", action="store_true", help="solo el servidor")
    ap.add_argument("--pantalla-completa", action="store_true")
    a = ap.parse_args()
    configurar_logs()
    log.info("Iniciando %s %s (datos en %s)", config.NOMBRE_APP, config.VERSION, config.directorio_datos())

    url = f"http://127.0.0.1:{a.puerto}/"
    servidor = hilo = None
    if responde(a.puerto):
        log.info("Ya hay un POS en ejecución en el puerto %s: se abre otra ventana sobre el mismo.", a.puerto)
    else:
        if not puerto_disponible(a.puerto):
            print(f"El puerto {a.puerto} está ocupado por otro programa. Use --puerto para elegir otro.", file=sys.stderr)
            return 2
        servidor, hilo = arrancar_servidor(a.puerto)
    print(f"{config.NOMBRE_APP} listo en {url}")

    try:
        if a.sin_ventana:
            while True:
                time.sleep(3600)
        elif a.navegador or not abrir_ventana(url, a.pantalla_completa):
            webbrowser.open(url)
            print("Abierto en el navegador. Cierre esta ventana (o presione Ctrl+C) para apagar el sistema.")
            while True:
                time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        if servidor is not None:
            servidor.should_exit = True
            hilo.join(timeout=8)
            log.info("Servidor detenido.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
