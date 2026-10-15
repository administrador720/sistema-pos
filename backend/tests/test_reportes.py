"""Dashboard e informes con números verificados a mano."""
from datetime import datetime

import pytest

from app import core

from .conftest import abrir_turno_cajero, crear_tienda, volver_admin


@pytest.fixture()
def historia(api, monkeypatch):
    """10 días: día 2 se venden 10 leches, día 4 se venden 5 aceites. «Hoy» es el día 10."""
    reloj = {"ahora": datetime(2026, 3, 1, 8, 0)}
    monkeypatch.setattr(core, "reloj", lambda: reloj["ahora"])
    t = crear_tienda(api)                      # día 1: se crea todo (SALDO_INICIAL)
    ef = t.medios["Efectivo"]

    def vender_dia(dia, hora, producto, cantidad, total):
        reloj["ahora"] = datetime(2026, 3, dia, hora, 0)
        abrir_turno_cajero(t, base=50000)
        api.ok(api.post("/api/ventas", {"items": [{"producto_id": producto["id"], "cantidad": cantidad}],
                                        "pagos": [{"medio_pago_id": ef, "monto": total, "recibido": total}]}))
        turno = api.ok(api.get("/api/turnos/actual"))["turno"]
        reloj["ahora"] = datetime(2026, 3, dia, hora + 6, 0)
        api.ok(api.post(f"/api/turnos/{turno['id']}/cerrar", {"efectivo_contado": 50000 + total, "banco_reportado": 0}))
        volver_admin(t)

    reloj["ahora"] = datetime(2026, 3, 2, 8, 0)
    vender_dia(2, 8, t.leche, 10, 42000)
    vender_dia(4, 9, t.aceite, 5, 57500)
    reloj["ahora"] = datetime(2026, 3, 10, 20, 0)
    api.login("admin", "secreto1")             # la sesión de 7 días del día 1 ya venció
    t.admin_token = api.token
    return t


def test_dashboard_kpis(historia):
    api = historia.api
    d = api.ok(api.get("/api/dashboard?desde=2026-03-01&hasta=2026-03-10"))
    k = d["kpis"]
    # ventas 42.000 + 57.500; el aceite lleva IVA 19 % incluido: base 48.319, impuesto 9.181
    assert k["ventas"] == 99500 and k["transacciones"] == 2 and k["ticket_promedio"] == 49750
    # costo: 10×3.000 + 5×8.000 = 70.000 ; margen = (99.500 − 9.181) − 70.000 = 20.319
    assert k["costo"] == 70000 and k["margen"] == 20319 and k["margen_pct"] == 22.5
    assert len(d["serie"]) == 10 and d["serie"][1]["ventas"] == 42000 and d["serie"][3]["ventas"] == 57500
    assert {m["medio"]: m["monto"] for m in d["medios"]} == {"Efectivo": 99500}
    assert d["top_ventas"][0]["nombre"] == "Aceite 1 L"
    # inventario hoy: leche 40×3.000 + arroz 40×2.000 + aceite 15×8.000
    assert d["inventario"]["valor"] == 120000 + 80000 + 120000
    assert d["periodo"]["dias"] == 10
    assert len(d["cierres"]) == 2 and d["cierres"][0]["diferencia_efectivo"] == 0


def test_rotacion_con_fotos_diarias_reconstruidas(historia):
    api = historia.api
    r = api.ok(api.get("/api/informes/rotacion?desde=2026-03-01&hasta=2026-03-10&agrupar=total"))
    fila = r["filas"][0]
    # valor del inventario por día: d1 390.000 · d2-3 360.000 · d4-10 320.000 → promedio 335.000
    assert fila["inventario_prom"] == 335000
    assert fila["costo_ventas"] == 70000
    assert fila["rotacion"] == 0.21 and fila["dias_inventario"] == 47.9
    # por categoría/producto el total cuadra
    porprod = api.ok(api.get("/api/informes/rotacion?desde=2026-03-01&hasta=2026-03-10&agrupar=producto"))
    assert {f["nombre"]: f["inventario_prom"] for f in porprod["filas"]} == {
        "Leche 1 L": 3000 * (50 + 40 * 9) // 10, "Arroz 500 g": 80000, "Aceite 1 L": 160000 * 3 // 10 + 120000 * 7 // 10}


def test_abc_ventas_por_dia_y_margen(historia):
    api = historia.api
    abc = api.ok(api.get("/api/informes/abc?desde=2026-03-01&hasta=2026-03-10&base=ventas"))
    assert [(f["nombre"], f["clase"]) for f in abc["filas"]] == [("Aceite 1 L", "A"), ("Leche 1 L", "C")]
    dia = api.ok(api.get("/api/informes/ventas_dia?desde=2026-03-01&hasta=2026-03-10"))
    assert [(f["dia"], f["ventas"], f["tiquetes"]) for f in dia["filas"]] == [("2026-03-02", 42000, 1), ("2026-03-04", 57500, 1)]
    assert dia["totales"]["ventas"] == 99500 and dia["totales"]["margen"] == 20319
    iva = api.ok(api.get("/api/informes/iva?desde=2026-03-01&hasta=2026-03-10"))
    assert {f["nombre"]: (f["base"], f["impuesto"]) for f in iva["filas"]} == {"Tarifa 19.0%": (48319, 9181), "Exento / excluido": (42000, 0)}


def test_sin_movimiento_cobertura_y_sugerido(historia):
    api = historia.api
    sm = api.ok(api.get("/api/informes/sin_movimiento?dias=5"))
    nombres = [f["nombre"] for f in sm["filas"]]
    assert "Arroz 500 g" in nombres and "Leche 1 L" in nombres        # arroz nunca se vendió; leche hace 8 días
    assert sm["filas"][0]["valor"] >= sm["filas"][-1]["valor"]
    sug = api.ok(api.get("/api/informes/sugerido?dias_cobertura=7"))
    assert sug["filas"] == [] or all(f["sugerido"] > 0 for f in sug["filas"])


def test_todos_los_informes_responden_y_exportan(historia):
    api = historia.api
    api.ok(api.post("/api/inventario/mermas", {"producto_id": historia.arroz["id"], "cantidad": 2, "motivo": "VENCIDO"}))
    api.ok(api.post("/api/compras", {"items": [{"producto_id": historia.arroz["id"], "cantidad": 5, "costo_unitario": 2100}]}))
    cat = api.ok(api.get("/api/informes"))
    assert len(cat) >= 20
    for c in cat:
        extra = f"&producto_id={historia.leche['id']}" if c["slug"] == "kardex" else ""
        q = f"?desde=2026-03-01&hasta=2026-03-10{extra}"
        r = api.ok(api.get(f"/api/informes/{c['slug']}{q}"))
        assert r["titulo"] and "filas" in r and "columnas" in r, c["slug"]
        assert api.get(f"/api/informes/{c['slug']}{q}&formato=xlsx").content[:2] == b"PK", c["slug"]
        assert api.get(f"/api/informes/{c['slug']}{q}&formato=pdf").content[:4] == b"%PDF", c["slug"]
    # desde la ventana de escritorio se guarda en la carpeta de exportes
    g = api.ok(api.get("/api/informes/ventas_dia?desde=2026-03-01&hasta=2026-03-10&formato=xlsx&guardar=true"))
    assert g["ruta"].endswith(".xlsx")
    mer = api.ok(api.get("/api/informes/mermas?desde=2026-03-01&hasta=2026-03-31"))
    assert mer["filas"][0]["nombre"] == "Vencido" and mer["filas"][0]["valor"] == 4000
    assert api.get("/api/informes/no_existe").status_code == 404
    assert api.get("/api/informes/ventas_dia?desde=2026-03-10&hasta=2026-03-01").status_code == 400


def test_diferencias_de_caja_por_cajero(historia):
    api = historia.api
    r = api.ok(api.get("/api/informes/dif_cajero?desde=2026-03-01&hasta=2026-03-10"))
    assert r["filas"][0]["nombre"] == "Carlos Cajero" and r["filas"][0]["turnos"] == 2
    c = api.ok(api.get("/api/informes/cierres?desde=2026-03-01&hasta=2026-03-10"))
    assert len(c["filas"]) == 2
