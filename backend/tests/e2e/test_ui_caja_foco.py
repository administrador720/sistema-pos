"""Un clic en + / − del carrito no debe dejar al botón recibiendo lo que escribe el lector de códigos de barras.

Error reportado: «se registran 2 cigarrillos y luego un chicle y aparece 3 cigarrillos». Con el mouse se subía la
cantidad con el botón +; el botón conservaba el foco y el Enter final del lector lo volvía a apretar (+1 al producto
anterior) mientras el producto nuevo no se registraba.
"""
import pytest

from app.seed_demo import ean13

from .conftest import entrar
from .test_ui_flujos import api, token

pytestmark = pytest.mark.e2e


def filas(pg):
    return [(r.locator("td").nth(1).locator("b").inner_text(), r.locator(".qtybox b").first.inner_text()) for r in pg.locator(".cart tbody tr").all()]


def con_turno(servidor, usuario="luis", clave="luis1234"):
    tk = token(servidor, usuario, clave)
    return tk, api(servidor, "api/turnos/abrir", tk, {"base": 50000})["turno"]


def cerrar(servidor, tk, turno):
    api(servidor, f"api/turnos/{turno['id']}/cerrar", tk, {"efectivo_contado": 50000, "banco_reportado": 0})


def test_subir_cantidad_con_el_mouse_y_escanear_otro_producto(pagina, servidor):
    pg = pagina
    entrar(pg, "luis", "luis1234")
    tk, turno = con_turno(servidor)
    try:
        pg.goto(servidor + "#/caja"); pg.wait_for_selector(".caja")
        scan = pg.locator(".scan input")
        scan.fill(ean13(1)); scan.press("Enter"); pg.wait_for_timeout(300)          # leche
        pg.locator(".cart tbody tr").nth(0).locator("button", has_text="+").click()  # sube con el mouse: 2
        assert pg.evaluate("document.activeElement.tagName") == "INPUT"             # el campo de escaneo recupera el foco
        pg.keyboard.type(ean13(5)); pg.keyboard.press("Enter")                      # el lector escribe sin que nadie toque el campo
        pg.wait_for_function("document.querySelectorAll('.cart tbody tr').length === 2")
        assert filas(pg) == [("Leche entera 1 L", "2"), ("Mantequilla 250 g", "1")]
        assert pg.errores == []
    finally:
        cerrar(servidor, tk, turno)


def test_si_un_boton_del_carrito_conserva_el_foco_el_lector_sigue_funcionando(pagina, servidor):
    pg = pagina
    entrar(pg, "luis", "luis1234")
    tk, turno = con_turno(servidor)
    try:
        pg.goto(servidor + "#/caja"); pg.wait_for_selector(".caja")
        scan = pg.locator(".scan input")
        for _ in range(2):                                                           # 2 leches escaneadas
            scan.fill(ean13(1)); scan.press("Enter"); pg.wait_for_timeout(300)
        pg.evaluate("document.querySelector('.cart .qtybox button:last-child').focus()")   # el botón + con el foco, como tras un clic
        assert pg.evaluate("document.activeElement.tagName") == "BUTTON"
        pg.keyboard.type(ean13(5)); pg.keyboard.press("Enter")
        pg.wait_for_function("document.querySelectorAll('.cart tbody tr').length === 2")
        assert filas(pg) == [("Leche entera 1 L", "2"), ("Mantequilla 250 g", "1")]
        # un Enter suelto con el foco en el botón tampoco suma nada
        pg.evaluate("document.querySelector('.cart .qtybox button:last-child').focus()")
        pg.keyboard.press("Enter"); pg.wait_for_timeout(300)
        assert filas(pg)[0] == ("Leche entera 1 L", "2")
        assert pg.errores == []
    finally:
        cerrar(servidor, tk, turno)


def agregar_a_mano(pg, nombre):
    """Producto sin código de barras: se escribe el nombre en el campo, se abre la lista y se elige con Enter."""
    campo = pg.locator(".scan input")
    campo.fill(nombre); campo.press("Enter")
    pg.wait_for_selector(".modal .res-fila")
    pg.keyboard.press("Enter")
    pg.wait_for_selector(".modal", state="detached")


def test_primer_producto_a_mano_subir_con_el_mouse_y_escanear_otro(pagina, servidor):
    """El caso reportado: «sigue cuando el primer producto se registra manual, sin código de barras»."""
    pg = pagina
    entrar(pg, "luis", "luis1234")
    tk, turno = con_turno(servidor)
    try:
        pg.goto(servidor + "#/caja"); pg.wait_for_selector(".caja")
        agregar_a_mano(pg, "kumis")
        assert filas(pg) == [("Kumis 1 L", "1")]
        pg.locator(".cart tbody tr").nth(0).locator("button", has_text="+").click()      # 2 con el mouse
        pg.keyboard.type(ean13(5)); pg.keyboard.press("Enter")                           # el lector escribe sin tocar el campo
        pg.wait_for_function("document.querySelectorAll('.cart tbody tr').length === 2")
        assert filas(pg) == [("Kumis 1 L", "2"), ("Mantequilla 250 g", "1")]
        assert pg.errores == []
    finally:
        cerrar(servidor, tk, turno)


def test_cantidad_con_asterisco_tambien_vale_para_productos_buscados_por_nombre(pagina, servidor):
    """«2*kumis» antes perdía la cantidad (quedaba 1): por eso se terminaba subiendo con el botón +."""
    pg = pagina
    entrar(pg, "luis", "luis1234")
    tk, turno = con_turno(servidor)
    try:
        pg.goto(servidor + "#/caja"); pg.wait_for_selector(".caja")
        agregar_a_mano(pg, "2*kumis")
        assert filas(pg) == [("Kumis 1 L", "2")]
        scan = pg.locator(".scan input")
        scan.fill("3*"); scan.press("Enter")                                             # y también en dos pasos: «3*» y luego el nombre
        agregar_a_mano(pg, "yogurt")
        assert filas(pg)[-1] == ("Yogurt fresa 1 L", "3")
        scan.fill("2*" + ean13(5)); scan.press("Enter"); pg.wait_for_timeout(400)         # con código sigue igual
        assert filas(pg)[-1] == ("Mantequilla 250 g", "2")
        assert pg.errores == []
    finally:
        cerrar(servidor, tk, turno)
