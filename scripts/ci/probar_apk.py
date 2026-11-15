"""Prueba de la app del celular dentro de un emulador de Android: abre la app instalada, la vincula con el servidor del
computador (que corre en este equipo, visto desde el emulador como 10.0.2.2), entra como administrador y consulta un
producto. Maneja la página de la app por el protocolo de depuración del WebView (CDP).

    python scripts/ci/probar_apk.py --admin http://127.0.0.1:8765 --usuario admin --clave demo1234 --producto 7700000000019 --nombre Leche
"""
import argparse
import json
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

PAQUETE = "com.possupermercado.movil"


def sh(*a, check=True):
    return subprocess.run(a, capture_output=True, text=True, check=check).stdout.strip()


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
    a = ap.parse_args()

    tk = api(a.admin, "/api/auth/login", cuerpo={"usuario": a.usuario, "password": a.clave})["token"]
    api(a.admin, "/api/movil/habilitar", tk, {"habilitado": True})
    puerto = api(a.admin, "/api/movil/estado", tk)["puerto"]
    codigo = api(a.admin, "/api/movil/codigo", tk, {})["codigo"]
    print(f"Servidor de celulares en el puerto {puerto}; código de vinculación generado.")

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
    print("App en ejecución, pid", pid)
    time.sleep(3)
    sh("adb", "forward", "tcp:9222", f"localabstract:webview_devtools_remote_{pid}")

    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        pg = None
        for _ in range(30):
            paginas = [pg_ for c in b.contexts for pg_ in c.pages]
            if paginas:
                pg = paginas[0]
                break
            time.sleep(1)
        if pg is None:
            sys.exit("No se encontró la página de la app (¿depuración del WebView desactivada?).")
        pg.set_default_timeout(25000)
        errores = []
        pg.on("pageerror", lambda e: errores.append(str(e)))
        try:
            pg.wait_for_selector("text=Conectar con el computador")
            print("Pantalla de vinculación visible. URL:", pg.url)
            if not pg.locator("button:has-text('Escanear el QR')").count():     # solo aparece si el plugin de la cámara está en la app
                sys.exit("Falta el botón para escanear el QR: el plugin del lector de códigos no está disponible.")
            pg.fill("input[placeholder='192.168.1.20']", f"{a.direccion}:{puerto}")
            pg.fill("input[placeholder='000000']", codigo)
            pg.click("button:has-text('Vincular')")
            pg.wait_for_selector("text=Iniciar sesión")
            print("Vinculado con el servidor a través de la red (CapacitorHttp + HTTP sin cifrar).")
            pg.fill("input[autocomplete=username]", a.usuario)
            pg.fill("input[type=password]", a.clave)
            pg.click("button:has-text('Ingresar')")
            pg.wait_for_selector(".tiles")
            assert pg.locator(".tile").count() == 5
            pg.click("a.tile:has-text('Consultar')")
            campo = pg.locator("input[enterkeyhint=search]").first
            campo.fill(a.producto)
            campo.press("Enter")
            pg.wait_for_selector(f"h2:has-text('{a.nombre}')")
            print("Consulta de producto OK desde la app instalada.")
            # el lector de cámara: el botón aparece solo si el plugin nativo está registrado
            hay_camara = pg.evaluate("!!(window.Capacitor && window.Capacitor.isNativePlatform() && window.Capacitor.isPluginAvailable('BarcodeScanner'))")
            print("Plugin del lector de códigos disponible:", hay_camara)
            if not hay_camara:
                sys.exit("El plugin del lector de códigos no está registrado en la app.")
            if errores:
                sys.exit("Errores en la página: " + "; ".join(errores[:3]))
        except Exception:
            print(sh("adb", "logcat", "-d", "-t", "120", check=False))
            raise
        finally:
            try:
                api(a.admin, "/api/movil/habilitar", tk, {"habilitado": False})
            except Exception:  # noqa: BLE001
                pass
    print("APP DEL CELULAR OK")


if __name__ == "__main__":
    main()
