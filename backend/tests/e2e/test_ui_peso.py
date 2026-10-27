"""Venta de verduras por peso en el navegador: código corto, peso en kilos, valor en pesos, botones rápidos y corrección."""
import pytest

from app.seed_demo import ean13

from .conftest import entrar
from .test_ui_flujos import api, token

pytestmark = pytest.mark.e2e


def test_venta_de_verduras_por_peso(pagina, servidor):
    pg = pagina
    entrar(pg, "luis", "luis1234")
    tk = token(servidor, "luis", "luis1234")
    turno = api(servidor, "api/turnos/abrir", tk, {"base": 50000})["turno"]
    pg.goto(servidor + "#/caja")
    pg.wait_for_selector(".caja")
    scan = pg.locator(".scan input")

    # 1) código corto (PLU 101 = tomate, $3.500/kg) → ventana de peso → 1,25 kg = $4.375
    scan.fill("101"); scan.press("Enter")
    pg.wait_for_selector(".modal")
    assert "Tomate chonto" in pg.locator(".modal-head").inner_text()
    pg.locator(".modal input").first.fill("1,25")
    assert pg.locator(".peso-total .big").inner_text() == "$ 4.375"
    pg.keyboard.press("Enter")
    pg.wait_for_selector(".modal", state="detached")
    fila = pg.locator(".cart tbody tr").nth(0)
    assert "1,250 kg" in fila.inner_text() and "$ 4.375" in fila.inner_text()

    # 2) peso escrito antes del código: «0,5*102» agrega 0,500 kg de cebolla ($3.000/kg) sin preguntar
    scan.fill("0,5*102"); scan.press("Enter")
    pg.wait_for_function("document.querySelectorAll('.cart tbody tr').length === 2")
    assert not pg.locator(".modal").count()
    assert "0,500 kg" in pg.locator(".cart tbody tr").nth(1).inner_text()
    assert pg.locator(".total-card .big").inner_text() == "$ 5.875"

    # 3) botones rápidos (F1) → zanahoria por valor: «$3.000 de zanahoria» (a $2.400/kg → 1,250 kg)
    pg.keyboard.press("F1")
    pg.wait_for_selector(".rapidos .rapido")
    assert pg.locator(".rapido").count() >= 8
    pg.locator(".rapido:has-text('Zanahoria')").first.click()
    pg.wait_for_selector(".modal-head:has-text('Zanahoria')")
    pg.click("button:has-text('Valor en pesos')")
    pg.locator(".modal input").first.fill("3000")
    assert pg.locator(".peso-total .big").inner_text() == "1,250 kg"
    pg.keyboard.press("Enter")
    pg.wait_for_selector(".modal", state="detached")
    ultima = pg.locator(".cart tbody tr").nth(2)
    assert "$ 3.000" in ultima.inner_text() and "por valor" in ultima.inner_text()

    # 4) corregir el peso de una línea con F3 (la cebolla: 0,5 → 0,75 kg = $2.250)
    pg.locator(".cart tbody tr").nth(1).click()
    pg.keyboard.press("F3")
    pg.wait_for_selector(".modal-head:has-text('Cebolla')")
    pg.locator(".modal input").first.fill("0,75")
    pg.keyboard.press("Enter")
    pg.wait_for_selector(".modal", state="detached")
    assert "0,750 kg" in pg.locator(".cart tbody tr").nth(1).inner_text()

    # 5) un producto por unidad sigue igual (leche $4.200) y los decimales no se le aceptan
    scan.fill(ean13(1)); scan.press("Enter"); pg.wait_for_timeout(250)
    scan.fill("1,5*" + ean13(1)); scan.press("Enter")
    pg.wait_for_selector("text=se vende por unidad")
    assert pg.locator(".total-card .big").inner_text() == "$ 13.825"     # 4.375 + 2.250 + 3.000 + 4.200

    # 6) cobrar en efectivo exacto
    pg.keyboard.press("F9"); pg.wait_for_selector(".modal")
    pg.keyboard.press("Enter")
    pg.wait_for_selector("text=Venta registrada"); pg.keyboard.press("Enter")

    # el servidor guardó kilos, gramos y el valor digitado
    v = api(servidor, "api/ventas?turno_id=%d" % turno["id"], tk)[0]
    detalle = api(servidor, f"api/ventas/{v['id']}", tk)
    por_nombre = {i["descripcion"]: i for i in detalle["items"]}
    assert por_nombre["Tomate chonto"]["cantidad"] == 1.25 and por_nombre["Tomate chonto"]["unidad"] == "kg"
    assert por_nombre["Cebolla cabezona blanca"]["cantidad"] == 0.75 and por_nombre["Cebolla cabezona blanca"]["total"] == 2250
    assert por_nombre["Zanahoria"]["cantidad"] == 1.25 and por_nombre["Zanahoria"]["total"] == 3000
    assert detalle["total"] == 13825
    assert pg.errores == []

    api(servidor, f"api/turnos/{turno['id']}/cerrar", tk, {"efectivo_contado": 50000 + 13825, "banco_reportado": 0})
