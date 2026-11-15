"""App del celular (pantallas servidas por el puerto de celulares), usada como un teléfono: vincular, entrar, consultar,
contar inventario, factura de compra, vender y cobrar, panel y desvincular."""
import re

import pytest

from app.seed_demo import ean13

from .conftest import entrar  # noqa: F401  (la fixture `servidor` y `navegador` vienen de conftest)
from .test_ui_flujos import api, token

pytestmark = pytest.mark.e2e


@pytest.fixture()
def celular(navegador):
    ctx = navegador.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, locale="es-CO")
    pg = ctx.new_page()
    pg.errores = []
    pg.on("pageerror", lambda e: pg.errores.append(f"pageerror: {e}"))
    pg.on("console", lambda m: pg.errores.append(f"{m.type}: {m.text}") if m.type == "error" and "404" not in m.text else None)
    pg.on("dialog", lambda d: d.accept())            # confirm() del navegador
    yield pg
    ctx.close()


def escribir_y_enter(pg, texto):
    campo = pg.locator("input[enterkeyhint=search]").first        # el buscador de productos (lector, teclado o cámara)
    campo.fill(texto)
    campo.press("Enter")


def test_el_celular_hace_todo(celular, servidor):
    pg = celular
    adm = token(servidor, "admin", "demo1234")
    puerto = api(servidor, "api/movil/estado", adm)["puerto"]
    api(servidor, "api/movil/habilitar", adm, {"habilitado": True})
    base = f"http://127.0.0.1:{puerto}"
    turno_abierto_aqui = None
    try:
        # ── vincular con el código del computador
        pg.goto(base + "/m/")
        pg.wait_for_selector("text=Conectar con el computador")
        codigo = api(servidor, "api/movil/codigo", adm, {})["codigo"]
        pg.fill("input[placeholder='000000']", codigo)
        pg.click("button:has-text('Vincular')")
        pg.wait_for_selector("text=Iniciar sesión")
        pg.fill("input[autocomplete=username]", "admin")
        pg.fill("input[type=password]", "demo1234")
        pg.click("button:has-text('Ingresar')")
        pg.wait_for_selector(".tiles")
        assert pg.locator(".tile").count() == 5

        # ── consultar precio y stock
        pg.click("a.tile:has-text('Consultar')")
        escribir_y_enter(pg, ean13(1))
        pg.wait_for_selector("h2:has-text('Leche entera 1 L')")
        assert "$ 4.200" in pg.locator(".tarjeta").inner_text()
        assert "Existencias" in pg.locator(".tarjeta").inner_text()
        pg.goto(base + "/m/#/")

        # ── contar inventario (captura ciega)
        c = api(servidor, "api/conteos", adm, {"nombre": "Conteo desde el celular", "tipo": "total", "alcance": {}})
        api(servidor, f"api/conteos/{c['id']}/iniciar", adm, {})
        pg.click("a.tile:has-text('Contar inventario')")
        pg.wait_for_selector(".barra h1:has-text('Contar inventario')")
        if pg.locator("button.item:has-text('Conteo desde el celular')").count():
            pg.click("button.item:has-text('Conteo desde el celular')")
        pg.wait_for_selector("b:has-text('Conteo desde el celular')")
        escribir_y_enter(pg, ean13(1))
        pg.wait_for_selector(".hoja")
        assert "Leche entera 1 L" in pg.locator(".hoja").inner_text()
        pg.locator(".hoja .paso button:last-child").click()           # 1 → 2
        pg.click(".hoja button:has-text('Registrar')")
        pg.wait_for_selector("text=Últimas capturas")
        assert "+2" in pg.locator(".lista").inner_text()
        assert "debería haber" in pg.locator(".contenido").inner_text()    # no muestra el stock del sistema
        pg.check(".tarjeta input[type=checkbox]")                       # sumar 1 al escanear
        escribir_y_enter(pg, ean13(5))
        pg.wait_for_function("document.querySelectorAll('.lista .item').length >= 2")
        capturas = api(servidor, f"api/conteos/{c['id']}/capturas", adm)
        assert sorted(x["cantidad"] for x in capturas) == [1, 2]
        pg.click(".lista .item >> nth=0 >> button")                      # deshacer la última
        pg.wait_for_function("document.querySelectorAll('.lista .item').length === 1")
        api(servidor, f"api/conteos/{c['id']}/cancelar", adm, {})
        pg.goto(base + "/m/#/")

        # ── factura de compra
        pg.click("a.tile:has-text('Facturas de compra')")
        pg.select_option("select", index=1)
        pg.fill("input[placeholder='Opcional']", "F-MOVIL-1")
        escribir_y_enter(pg, ean13(5))
        pg.wait_for_selector(".linea")
        pg.locator(".linea .paso input").fill("10")
        pg.locator(".linea input[inputmode=decimal]").fill("5000")
        assert "$ 50.000" in pg.locator(".pie").inner_text()
        pg.click(".pie button:has-text('Guardar')")
        pg.wait_for_selector("text=Factura registrada")
        compras = api(servidor, "api/compras", adm)
        assert any(x["numero_factura"] == "F-MOVIL-1" and x["total"] == 50000 for x in compras)
        pg.goto(base + "/m/#/")

        # ── vender y cobrar (turno abierto por el computador)
        if not api(servidor, "api/turnos/actual", adm)["turno"]:
            turno_abierto_aqui = api(servidor, "api/turnos/abrir", adm, {"base": 50000})["turno"]
        pg.click("a.tile:has-text('Vender y cobrar')")
        pg.wait_for_selector("input[enterkeyhint=search]")
        for _ in range(2):
            escribir_y_enter(pg, ean13(1)); pg.wait_for_timeout(300)
        escribir_y_enter(pg, "101")                                      # tomate por peso (código corto)
        pg.wait_for_selector(".hoja:has-text('Precio por kilo')")
        pg.locator(".hoja .paso input").fill("1,25")
        assert "$ 4.375" in pg.locator(".hoja").inner_text()
        pg.click(".hoja button:has-text('Agregar')")
        pg.wait_for_function("document.querySelectorAll('.linea').length === 2")
        assert "$ 12.775" in pg.locator(".pie").inner_text()            # 2 × 4.200 + 1,25 kg × 3.500
        pg.click(".pie button:has-text('Cobrar')")
        pg.locator(".hoja input[inputmode=numeric]").fill("20000")
        assert "Devuelta $ 7.225" in pg.locator(".hoja").inner_text()
        pg.click(".hoja button:has-text('Confirmar')")
        pg.wait_for_selector("text=Venta registrada")
        v = api(servidor, "api/ventas", adm)[0]
        assert v["total"] == 12775
        pg.goto(base + "/m/#/")

        # ── panel de ventas
        pg.click("a.tile:has-text('Panel de ventas')")
        pg.wait_for_selector(".kpis")
        assert "$" in pg.locator(".kpis").inner_text()
        pg.click("button:has-text('7 días')")
        pg.wait_for_selector(".barras")
        assert "Inventario" in pg.locator(".contenido").inner_text()

        # ── si el computador desvincula el celular, la app lo detecta y pide vincular de nuevo
        did = api(servidor, "api/movil/estado", adm)["dispositivos"][0]["id"]
        api(servidor, f"api/movil/dispositivos/{did}", adm, None, "DELETE")
        pg.goto(base + "/m/#/consultar")
        escribir_y_enter(pg, ean13(1))                                    # la primera petición descubre que ya no está vinculado
        pg.wait_for_selector("text=Conectar con el computador", timeout=8000)
        assert [e for e in pg.errores if "401" not in e] == []             # el 401 de arriba es justamente lo que se provocó
    finally:
        if turno_abierto_aqui:
            try:
                api(servidor, f"api/turnos/{turno_abierto_aqui['id']}/cerrar", adm, {"efectivo_contado": 50000 + 12775, "banco_reportado": 0})
            except Exception:  # noqa: BLE001
                pass
        try:
            for d in api(servidor, "api/movil/estado", adm)["dispositivos"]:      # que no quede ningún celular vinculado
                api(servidor, f"api/movil/dispositivos/{d['id']}", adm, None, "DELETE")
            api(servidor, "api/movil/habilitar", adm, {"habilitado": False})
        except Exception:  # noqa: BLE001
            pass
