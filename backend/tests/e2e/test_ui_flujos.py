"""Flujos completos en el navegador: caja (abrir → vender → cobrar → cerrar), conteo de inventario, pantallas, tema y bloqueo."""
import json
import urllib.request

import pytest

from app.seed_demo import ean13

from .conftest import entrar

pytestmark = pytest.mark.e2e


def api(base, ruta, token=None, cuerpo=None, metodo=None):
    req = urllib.request.Request(base + ruta.lstrip("/"), data=json.dumps(cuerpo).encode() if cuerpo is not None else None, method=metodo,
                                 headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})})
    return json.loads(urllib.request.urlopen(req, timeout=10).read())


def token(base, usuario, password):
    return api(base, "api/auth/login", cuerpo={"usuario": usuario, "password": password})["token"]


def test_jornada_de_caja_completa(pagina):
    pg = pagina
    entrar(pg, "ana", "ana1234")
    assert pg.evaluate("location.hash") == "#/apertura"          # la cajera debe abrir caja primero

    # apertura con base contada: 1 billete de 100.000 + 2 de 10.000 = 120.000
    pg.click("text=Contar billetes y monedas")
    pg.locator(".denom").nth(0).locator("input").fill("1")
    pg.locator(".denom").nth(3).locator("input").fill("2")
    pg.click("button:has-text('Abrir caja con')")
    pg.wait_for_selector(".caja")
    assert "Turno #" in pg.locator(".turno-chip").inner_text()

    scan = pg.locator(".scan input")
    # leche (4.200) y aceite (11.500) = 15.700; un código inexistente avisa y no agrega nada
    for n in (1, 13):
        scan.fill(ean13(n)); scan.press("Enter"); pg.wait_for_timeout(250)
    scan.fill("999999999999"); scan.press("Enter")
    pg.wait_for_selector("text=no existe")
    assert pg.locator(".cart tbody tr").count() == 2
    assert pg.locator(".total-card .big").inner_text() == "$ 15.700"

    # cobro en efectivo: recibe 20.000 → devuelta 4.300
    pg.keyboard.press("F9")
    pg.wait_for_selector(".modal")
    pg.locator(".modal input").first.fill("20000")
    assert "4.300" in pg.locator(".change-box").inner_text()
    pg.keyboard.press("Enter")
    pg.wait_for_selector("text=Venta registrada")
    assert "4.300" in pg.locator(".change-box .big").inner_text()
    pg.keyboard.press("Enter")
    pg.wait_for_selector(".modal", state="detached")

    # venta con banco (mantequilla 8.800) por F10
    scan.fill(ean13(5)); scan.press("Enter"); pg.wait_for_timeout(250)
    pg.keyboard.press("F10"); pg.wait_for_selector(".modal")
    pg.keyboard.press("Enter"); pg.wait_for_selector("text=Venta registrada"); pg.keyboard.press("Enter")

    # cierre ciego: nunca muestra el esperado antes de contar
    pg.goto(pg.url_base + "#/cierre"); pg.wait_for_selector("text=Cerrar caja")
    assert "135.700" not in pg.content()
    # esperado = base 120.000 + 15.700 en efectivo = 135.700 → 1×100.000 + 3×10.000 + 1×5.000 + 1×500 + 1×200
    for idx, cant in ((0, 1), (3, 3), (4, 1), (7, 1), (8, 1)):
        pg.locator(".denom").nth(idx).locator("input").fill(str(cant))
    pg.locator("input[placeholder='0']").first.fill("8800")           # lo que reporta el datáfono
    pg.click("button:has-text('Cerrar caja')")
    pg.click(".modal button:has-text('Sí, cerrar caja')")
    pg.wait_for_selector("text=cerrado")
    texto = pg.locator(".page").inner_text()
    assert texto.count("Cuadra") == 2                                  # efectivo y banco cuadran
    assert "$ 135.700" in texto
    assert pg.errores == []


def test_conteo_de_inventario_con_diferencias(pagina, servidor):
    pg = pagina
    entrar(pg, "admin", "demo1234")
    adm = token(servidor, "admin", "demo1234")
    leche = api(servidor, "api/productos/codigo/" + ean13(1), adm)
    stock_antes = api(servidor, f"api/productos/{leche['id']}", adm)["stock_actual"]

    pg.goto(servidor + "#/conteos"); pg.wait_for_selector("text=Nuevo conteo")
    pg.click("button:has-text('Nuevo conteo')")
    pg.fill(".modal input >> nth=0", "Conteo de prueba")
    pg.click(".modal button:has-text('Crear e iniciar')")
    pg.wait_for_selector("text=Contar")

    # se cuenta solo la leche: 3 unidades menos de las que dice el sistema
    scan = pg.locator(".scan input")
    contar = stock_antes - 3
    scan.fill(f"{contar}*"); scan.press("Enter")                         # prefijo de cantidad
    scan.fill(ean13(1)); scan.press("Enter")
    pg.wait_for_selector("text=llevas")
    assert str(stock_antes) not in pg.locator(".card").first.inner_text()   # captura a ciegas: no muestra el stock del sistema

    pg.click("button:has-text('Terminar captura y revisar')")
    pg.click(".modal button:has-text('Terminar y revisar')")
    pg.wait_for_selector("text=Exactitud del inventario")
    fila = pg.locator("tbody tr", has_text="Leche entera 1 L")
    assert "-3" in fila.inner_text()
    assert "Faltantes" in pg.locator(".page").inner_text()

    pg.click("button:has-text('Aplicar ajustes al inventario')")
    pg.click(".modal button:has-text('Sí, aplicar ajustes')")
    pg.wait_for_selector("text=Aplicado")
    despues = api(servidor, f"api/productos/{leche['id']}", adm)["stock_actual"]
    assert despues == stock_antes - 3
    assert pg.errores == []


@pytest.mark.parametrize("ruta", ["dashboard", "productos", "compras", "inventario", "conteos", "informes", "turnos", "config", "cuenta", "caja", "apertura"])
def test_pantallas_del_administrador_cargan_sin_errores(pagina, ruta):
    pg = pagina
    entrar(pg, "admin", "demo1234")
    pg.goto(pg.url_base + "#/" + ruta)
    pg.wait_for_timeout(1500)
    assert pg.locator(".page").count() >= 1
    assert not pg.locator(".toast.error").count(), pg.locator(".toast.error").all_inner_texts()
    assert pg.errores == []


def test_tema_oscuro_y_bloqueo_de_pantalla(pagina):
    pg = pagina
    entrar(pg, "ana", "ana1234")
    pg.click("button[title='Tema oscuro']")
    assert pg.evaluate("document.documentElement.getAttribute('data-theme')") == "dark"
    pg.click("button[title='Tema claro']")
    assert pg.evaluate("document.documentElement.getAttribute('data-theme')") == "light"
    # bloquear: pide el PIN de la propia cajera
    pg.click(".side-foot button")
    pg.wait_for_selector(".lock")
    pg.fill(".lock input", "0000"); pg.keyboard.press("Enter")
    pg.wait_for_selector(".lock .err-text")
    pg.fill(".lock input", "4321"); pg.keyboard.press("Enter")
    pg.wait_for_selector(".lock", state="detached")


def test_cajero_no_ve_menus_de_administracion_ni_puede_entrar(pagina):
    pg = pagina
    entrar(pg, "luis", "luis1234")
    menu = pg.locator(".nav").inner_text()
    assert "Panel de control" not in menu and "Configuración" not in menu and "Productos" not in menu
    pg.goto(pg.url_base + "#/config"); pg.wait_for_timeout(500)
    assert "Configuración" not in pg.locator(".topbar h1").inner_text()      # lo devuelve a su pantalla
