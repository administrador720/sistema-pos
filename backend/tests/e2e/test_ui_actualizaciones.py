"""Pantalla de actualizaciones en el navegador (el servidor de GitHub se simula interceptando las llamadas de la interfaz)."""
import json

import pytest

from .conftest import entrar

pytestmark = pytest.mark.e2e

NUEVA = {"version_actual": "1.1.0", "version_nueva": "9.9.9", "hay_nueva": True, "publicada": "2026-11-01T10:00:00Z",
         "notas": "Qué hay de nuevo:\n- Ventas por peso mejoradas", "descargable": True, "soportado": True, "motivo": None,
         "instalador": {"nombre": "Instalador-POS-Supermercado-9.9.9.exe", "url": "https://x", "tamano": 62_000_000}, "sha256_url": "https://x"}


def responder(ruta, cuerpo, status=200):
    ruta.fulfill(status=status, content_type="application/json", body=json.dumps(cuerpo))


def test_aviso_descarga_e_instalacion(pagina):
    pg = pagina
    pasos = {"estado": 0, "instalar": 0}

    def estado(ruta):
        pasos["estado"] += 1
        if pasos["estado"] < 3:
            return responder(ruta, {"fase": "descargando", "progreso": 0.4, "version": "9.9.9"})
        responder(ruta, {"fase": "listo", "progreso": 1, "version": "9.9.9", "archivo": "x", "sha256": "y"})

    def instalar(ruta):
        pasos["instalar"] += 1
        responder(ruta, {"ok": True, "mensaje": "Instalando la versión 9.9.9. El programa se cerrará."})

    pg.route("**/api/sistema/actualizaciones/buscar", lambda r: responder(r, NUEVA))
    pg.route("**/api/sistema/actualizaciones/descargar", lambda r: responder(r, {"fase": "descargando", "progreso": 0.1, "version": "9.9.9"}))
    pg.route("**/api/sistema/actualizaciones/estado", estado)
    pg.route("**/api/sistema/actualizaciones/instalar", instalar)
    entrar(pg, "admin", "demo1234")

    # aviso en la barra superior y versión en el menú lateral
    pg.wait_for_selector(".nueva-version")
    assert "9.9.9" in pg.locator(".nueva-version").inner_text()
    assert "Versión 1.1.0" in pg.locator(".side-foot").inner_text()

    pg.click(".nueva-version")
    pg.wait_for_selector("h2:has-text('Versión 9.9.9 disponible')")
    assert "Ventas por peso mejoradas" in pg.locator(".page").inner_text()
    pg.click("button:has-text('Descargar actualización')")
    pg.wait_for_selector("text=Descargada y verificada", timeout=8000)
    pg.click("button:has-text('Instalar ahora')")
    pg.wait_for_selector(".modal")
    assert "permiso de administrador" in pg.locator(".modal").inner_text()
    pg.click(".modal button:has-text('Sí, instalar ahora')")
    pg.wait_for_selector("text=Instalando la versión 9.9.9")
    assert pasos["instalar"] == 1
    assert pg.errores == []


def test_sin_internet_se_explica(pagina):
    pg = pagina
    pg.route("**/api/sistema/actualizaciones/buscar", lambda r: responder(
        r, {"detalle": "No se pudo consultar si hay una versión nueva. Revise la conexión a internet.", "codigo": "SIN_CONEXION"}, 502))
    entrar(pg, "admin", "demo1234")
    pg.goto(pg.url_base + "#/config")
    pg.click("button:has-text('Actualizaciones')")
    pg.click("button:has-text('Buscar actualizaciones')")
    pg.wait_for_selector("text=Revise la conexión a internet")
    assert not pg.locator(".nueva-version").count()
