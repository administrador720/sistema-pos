"""Prueba de la app del celular dentro de un emulador de Android: abre la app instalada, la vincula con el servidor del
computador (que corre en este equipo, visto desde el emulador como 10.0.2.2), entra como administrador y consulta un
producto. Maneja la página de la app por el protocolo de depuración del WebView (CDP, ver cdp.py).

    python scripts/ci/probar_apk.py --admin http://127.0.0.1:8765 --usuario admin --clave demo1234 --producto 7700000000019 --nombre Leche
    # Para validar el conductor en una PC (sin Android): --navegador-cdp 9333 (Chrome con --remote-debugging-port=9333 en /m/)
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp import Pagina  # noqa: E402

PAQUETE = "com.possupermercado.movil"


def sh(*a, check=True):
    return subprocess.run(a, capture_output=True, text=True, check=check, timeout=120).stdout.strip()


def api(base, ruta, token=None, cuerpo=None):
    req = urllib.request.Request(base + ruta, data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
                                 headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})})
    return json.loads(urllib.request.urlopen(req, timeout=20).read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--admin", required=True)
    ap.add_argument("--usuario", required=True)
    ap.add_argument("--clave", required=True)
    ap.add_argument("--producto", required=True)
    ap.add_argument("--nombre", required=True)
    ap.add_argument("--direccion", default="10.0.2.2")
    ap.add_argument("--navegador-cdp", type=int, default=0, help="solo para validar el conductor en una PC: puerto CDP de un Chrome ya abierto")
    a = ap.parse_args()

    tk = api(a.admin, "/api/auth/login", cuerpo={"usuario": a.usuario, "password": a.clave})["token"]
    api(a.admin, "/api/movil/habilitar", tk, {"habilitado": True})
    puerto = api(a.admin, "/api/movil/estado", tk)["puerto"]
    codigo = api(a.admin, "/api/movil/codigo", tk, {})["codigo"]
    print(f"Servidor de celulares en el puerto {puerto}; código de vinculación generado.", flush=True)

    if a.navegador_cdp:
        puerto_cdp = a.navegador_cdp
    else:
        sh("adb", "shell", "am", "start", "-W", "-n", f"{PAQUETE}/.MainActivity")
        pid = ""
        for _ in range(30):
            pid = sh("adb", "shell", "pidof", PAQUETE, check=False)
            if pid:
                break
            time.sleep(1)
        if not pid:
            print(sh("adb", "logcat", "-d", "-t", "200", check=False))
            sys.exit("La app no arrancó (no hay proceso).")
        pid = pid.split()[0]
        print("App en ejecución, pid", pid, flush=True)
        time.sleep(3)
        puerto_cdp = 9222
        sh("adb", "forward", f"tcp:{puerto_cdp}", f"localabstract:webview_devtools_remote_{pid}")

    pg = Pagina(puerto_cdp)
    nativa = not a.navegador_cdp
    errores = []
    try:
        pg.esperar_texto("Conectar con el computador")
        print("Pantalla de vinculación visible. URL:", pg.url, flush=True)
        if nativa:
            if not pg.t("contiene", "button", "Escanear el QR"):    # solo aparece si el plugin de la cámara está en la app
                sys.exit("Falta el botón para escanear el QR: el plugin del lector de códigos no está disponible.")
            pg.escribir("input[placeholder='192.168.1.20']", f"{a.direccion}:{puerto}")
        pg.escribir("input[placeholder='000000']", codigo)
        pg.clic("button", "Vincular")
        pg.esperar_texto("Iniciar sesión")
        print("Vinculado con el servidor a través de la red (CapacitorHttp + HTTP sin cifrar).", flush=True)
        pg.escribir("input[autocomplete=username]", a.usuario)
        pg.escribir("input[type=password]", a.clave)
        pg.clic("button", "Ingresar")
        pg.esperar_sel(".tiles")
        assert pg.t("cuantos", ".tile") == 5, "Faltan opciones en el inicio"
        pg.clic("a.tile", "Consultar")
        pg.escribir("input[enterkeyhint=search]", a.producto)
        pg.t("enter", "input[enterkeyhint=search]")
        pg.esperar("contiene", "h2", a.nombre, descripcion=f"la ficha de «{a.nombre}»")
        print("Consulta de producto OK desde la app.", flush=True)
        if nativa:
            hay = pg.js("!!(window.Capacitor && window.Capacitor.isNativePlatform() && window.Capacitor.isPluginAvailable('BarcodeScanner'))")
            print("Plugin del lector de códigos disponible:", hay, flush=True)
            if not hay:
                sys.exit("El plugin del lector de códigos no está registrado en la app.")
    except BaseException:
        if nativa:
            print(sh("adb", "logcat", "-d", "-t", "150", check=False))
        raise
    finally:
        pg.cerrar()
        try:
            api(a.admin, "/api/movil/habilitar", tk, {"habilitado": False})
        except Exception:  # noqa: BLE001
            pass
    print("APP DEL CELULAR OK")


if __name__ == "__main__":
    main()
