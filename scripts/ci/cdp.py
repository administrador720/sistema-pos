"""Conductor mínimo del protocolo de depuración de Chrome (CDP) para manejar la página de la app dentro del WebView de
Android. Playwright no sirve aquí: el WebView no soporta la administración de contextos del navegador. Usa solo
`Runtime.evaluate` sobre la página (necesita el paquete websocket-client)."""
import json
import time
import urllib.request

import websocket

AYUDAS = r"""
window.__t = {
  hay: (sel) => !!document.querySelector(sel),
  textoPagina: () => document.body.innerText,
  escribir: (sel, valor) => {
    const e = document.querySelector(sel); if (!e) throw new Error('No existe ' + sel);
    e.focus(); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(e, valor);
    e.dispatchEvent(new Event('input', { bubbles: true })); return true;
  },
  enter: (sel) => {
    const e = document.querySelector(sel); if (!e) throw new Error('No existe ' + sel);
    e.focus(); e.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true })); return true;
  },
  clic: (sel, texto) => {
    const todos = Array.from(document.querySelectorAll(sel));
    const e = texto ? todos.find(x => x.innerText.includes(texto)) : todos[0];
    if (!e) throw new Error('No existe ' + sel + (texto ? ' con «' + texto + '»' : '')); e.click(); return true;
  },
  cuantos: (sel) => document.querySelectorAll(sel).length,
  contiene: (sel, texto) => Array.from(document.querySelectorAll(sel)).some(x => x.innerText.includes(texto)),
};
true
"""


class Pagina:
    def __init__(self, puerto: int, segundos: int = 40):
        fin = time.time() + segundos
        destino = None
        while time.time() < fin and not destino:
            try:
                objetivos = json.load(urllib.request.urlopen(f"http://127.0.0.1:{puerto}/json", timeout=5))
                destino = next((t for t in objetivos if t.get("type") == "page" and t.get("webSocketDebuggerUrl")), None)
            except Exception:  # noqa: BLE001
                pass
            if not destino:
                time.sleep(1)
        if not destino:
            raise RuntimeError("No hay ninguna página para depurar (¿depuración del WebView desactivada?)")
        self.url = destino.get("url", "")
        self.ws = websocket.create_connection(destino["webSocketDebuggerUrl"], timeout=30, suppress_origin=True)   # sin cabecera Origin: Chrome nuevo rechaza las de otros orígenes
        self._n = 0
        self.cmd("Runtime.enable")
        self.preparar()

    def cmd(self, metodo, **params):
        self._n += 1
        self.ws.send(json.dumps({"id": self._n, "method": metodo, "params": params}))
        while True:
            r = json.loads(self.ws.recv())
            if r.get("id") == self._n:
                if "error" in r:
                    raise RuntimeError(f"{metodo}: {r['error']}")
                return r.get("result", {})

    def js(self, expresion: str):
        r = self.cmd("Runtime.evaluate", expression=expresion, returnByValue=True, awaitPromise=True)
        if "exceptionDetails" in r:
            d = r["exceptionDetails"]
            raise RuntimeError((d.get("exception") or {}).get("description") or d.get("text") or "error de JavaScript")
        return r.get("result", {}).get("value")

    def preparar(self):
        self.js(AYUDAS)

    def t(self, funcion: str, *args):
        return self.js(f"window.__t.{funcion}({', '.join(json.dumps(a) for a in args)})")

    def esperar(self, funcion: str, *args, segundos: int = 25, descripcion: str = ""):
        fin = time.time() + segundos
        ultimo = None
        while time.time() < fin:
            try:
                if not self.js("typeof window.__t") == "object":   # la página se recargó
                    self.preparar()
                if self.t(funcion, *args):
                    return True
            except Exception as e:  # noqa: BLE001
                ultimo = e
            time.sleep(0.3)
        raise TimeoutError(f"Se esperaba {descripcion or funcion + str(args)}. Texto de la página: {(self.js('document.body.innerText') or '')[:300]!r} ({ultimo})")

    # atajos
    def esperar_texto(self, texto, segundos=25):
        return self.esperar("contiene", "body", texto, segundos=segundos, descripcion=f"el texto «{texto}»")

    def esperar_sel(self, sel, segundos=25):
        return self.esperar("hay", sel, segundos=segundos, descripcion=f"el elemento {sel}")

    def escribir(self, sel, valor):
        self.esperar_sel(sel)
        self.t("escribir", sel, valor)

    def clic(self, sel, texto=None):
        self.esperar("cuantos", sel, segundos=25, descripcion=f"{sel}") if False else self.esperar_sel(sel)
        self.t("clic", sel, texto)

    def cerrar(self):
        try:
            self.ws.close()
        except Exception:  # noqa: BLE001
            pass
