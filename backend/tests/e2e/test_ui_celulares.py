"""Configuración → Celulares: activar, vincular con código/QR, ver el celular y desvincularlo (servidor de celulares real)."""
import json
import re
import urllib.error
import urllib.request

import pytest

from .conftest import entrar
from .test_ui_flujos import api, token

pytestmark = pytest.mark.e2e


def test_activar_vincular_y_desvincular_un_celular(pagina, servidor):
    pg = pagina
    entrar(pg, "admin", "demo1234")
    tk = token(servidor, "admin", "demo1234")
    puerto = api(servidor, "api/movil/estado", tk)["puerto"]
    try:
        pg.goto(servidor + "#/config")
        pg.click("button:has-text('Celulares')")
        pg.wait_for_selector("text=Conectar celulares a esta red")
        assert pg.locator(".chip", has_text="Apagado").count() == 1
        pg.click("button:has-text('Activar el acceso de celulares')")
        pg.wait_for_selector(".modal")
        pg.click(".modal button:has-text('Sí, activar')")
        pg.wait_for_selector(".chip:has-text('Activo')")
        assert "192.168.1.20" in pg.locator(".page").inner_text()

        pg.click("button:has-text('Vincular un celular')")
        pg.wait_for_selector(".modal svg")                      # el QR
        codigo = pg.locator(".modal .num").inner_text().strip()
        assert re.fullmatch(r"\d{6}", codigo)

        # el «celular» canjea el código por la red local (otro puerto, solo con su llave)
        req = urllib.request.Request(f"http://127.0.0.1:{puerto}/api/movil/vincular", method="POST",
                                     data=json.dumps({"codigo": codigo, "nombre": "Celular de prueba"}).encode(),
                                     headers={"Content-Type": "application/json"})
        llave = json.loads(urllib.request.urlopen(req, timeout=5).read())["token"]
        pg.wait_for_selector("text=Celular vinculado: Celular de prueba", timeout=8000)
        pg.wait_for_selector("tr:has-text('Celular de prueba')")
        with pytest.raises(urllib.error.HTTPError) as e:          # sin llave no hay API
            urllib.request.urlopen(f"http://127.0.0.1:{puerto}/api/productos", timeout=5)
        assert e.value.code == 401
        login = urllib.request.Request(f"http://127.0.0.1:{puerto}/api/auth/login", method="POST",     # la llave sola no basta: falta entrar como administrador
                                       data=json.dumps({"usuario": "admin", "password": "demo1234"}).encode(),
                                       headers={"Content-Type": "application/json", "X-Dispositivo": llave})
        sesion = json.loads(urllib.request.urlopen(login, timeout=5).read())["token"]
        ok = urllib.request.Request(f"http://127.0.0.1:{puerto}/api/productos/rapidos", headers={"X-Dispositivo": llave, "Authorization": f"Bearer {sesion}"})
        assert urllib.request.urlopen(ok, timeout=5).status == 200

        pg.click("tr:has-text('Celular de prueba') button:has-text('Desvincular')")
        pg.click(".modal button:has-text('Desvincular')")
        pg.wait_for_selector("text=Todavía no hay celulares vinculados")
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(ok, timeout=5)
        assert e.value.code == 401

        pg.click("button:has-text('Apagar el acceso de celulares')")
        pg.wait_for_selector(".chip:has-text('Apagado')")
        with pytest.raises(OSError):
            urllib.request.urlopen(f"http://127.0.0.1:{puerto}/api/movil/info", timeout=2)
        assert pg.errores == []
    finally:
        try:
            api(servidor, "api/movil/habilitar", tk, {"habilitado": False})
        except Exception:  # noqa: BLE001
            pass
