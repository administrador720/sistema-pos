"""Flujo completo de una jornada: apertura con base, ventas (efectivo/banco/mixto), cierre ciego con arqueo."""
from .conftest import abrir_turno_cajero, volver_admin


def vender(api, items, pagos, **extra):
    return api.post("/api/ventas", {"items": items, "pagos": pagos, **extra})


def test_jornada_completa(tienda):
    t, api = tienda, tienda.api
    efectivo, debito = t.medios["Efectivo"], t.medios["Tarjeta débito"]

    # sin turno no se puede vender
    api.login("carlos", "cajero1")
    r = vender(api, [{"producto_id": t.leche["id"], "cantidad": 1}], [{"medio_pago_id": efectivo, "monto": 4200}])
    assert r.status_code == 409 and r.json()["codigo"] == "SIN_TURNO"

    turno = api.ok(api.post("/api/turnos/abrir", {"base": 100000}))["turno"]
    assert turno["base_efectivo"] == 100000
    # un segundo turno en la misma caja no se permite
    assert api.post("/api/turnos/abrir", {"base": 5}).status_code == 409

    # venta 1: efectivo con devuelta. 2 leches (8.400) + 1 aceite (11.500) = 19.900; paga con 20.000
    v1 = api.ok(vender(api, [{"producto_id": t.leche["id"], "cantidad": 2}, {"producto_id": t.aceite["id"], "cantidad": 1}],
                       [{"medio_pago_id": efectivo, "monto": 19900, "recibido": 50000}]))
    assert v1["total"] == 19900 and v1["numero"] == "POS-000001"
    assert v1["pagos"][0]["devuelta"] == 30100
    # IVA 19% incluido solo en el aceite: 11.500 → base 9.664, impuesto 1.836
    assert v1["impuesto_total"] == 1836

    # venta 2: banco exacto
    v2 = api.ok(vender(api, [{"producto_id": t.arroz["id"], "cantidad": 3}], [{"medio_pago_id": debito, "monto": 8700}]))
    assert v2["numero"] == "POS-000002" and v2["pagos"][0]["devuelta"] == 0

    # venta 3: mixta. total 4.200 + 11.500 = 15.700 → banco 10.000 + efectivo 5.700 (recibe 10.000 → devuelta 4.300)
    v3 = api.ok(vender(api, [{"producto_id": t.leche["id"], "cantidad": 1}, {"producto_id": t.aceite["id"], "cantidad": 1}],
                       [{"medio_pago_id": debito, "monto": 10000}, {"medio_pago_id": efectivo, "monto": 5700, "recibido": 10000}]))
    assert sum(p["monto"] for p in v3["pagos"]) == 15700
    assert [p["devuelta"] for p in v3["pagos"] if p["tipo"] == "efectivo"] == [4300]

    # stock descontado: leche 50-2-1, aceite 20-1-1, arroz 40-3
    p = api.ok(api.get(f"/api/productos/{t.leche['id']}"))
    assert p["stock_actual"] == 47
    # el cajero NO ve el efectivo esperado (cierre ciego)
    actual = api.ok(api.get("/api/turnos/actual"))
    assert actual["resumen"]["ciego"] is True and "efectivo_esperado" not in actual["resumen"]

    # efectivo esperado = base 100.000 + 19.900 + 5.700 = 125.600. Cuenta 125.000 → faltante de 600
    # banco esperado = 8.700 + 10.000 = 18.700; el datáfono reporta 18.700 → diferencia 0
    z = api.ok(api.post(f"/api/turnos/{turno['id']}/cerrar", {
        "denominaciones": [{"denominacion": 100000, "cantidad": 1}, {"denominacion": 20000, "cantidad": 1},
                           {"denominacion": 5000, "cantidad": 1}],
        "banco_reportado": 18700}))
    assert z["turno"]["efectivo_esperado"] == 125600
    assert z["turno"]["efectivo_contado"] == 125000
    assert z["turno"]["diferencia_efectivo"] == -600
    assert z["turno"]["diferencia_banco"] == 0
    assert z["totales"]["ventas_n"] == 3 and z["totales"]["ventas_total"] == 19900 + 8700 + 15700

    # turno cerrado: ya no se vende
    assert vender(api, [{"producto_id": t.leche["id"], "cantidad": 1}], [{"medio_pago_id": efectivo, "monto": 4200}]).status_code == 409

    # el administrador ve el reporte y el PDF
    volver_admin(t)
    assert api.ok(api.get(f"/api/turnos/{turno['id']}/reporte"))["turno"]["diferencia_efectivo"] == -600
    pdf = api.get(f"/api/turnos/{turno['id']}/reporte?formato=pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"


def test_precios_los_define_el_servidor_y_validaciones_de_pago(tienda):
    t, api = tienda, tienda.api
    efectivo, debito = t.medios["Efectivo"], t.medios["Tarjeta débito"]
    abrir_turno_cajero(t)
    item = [{"producto_id": t.leche["id"], "cantidad": 1}]
    # la suma de pagos debe igualar el total
    r = vender(api, item, [{"medio_pago_id": efectivo, "monto": 4000, "recibido": 5000}])
    assert r.status_code == 400 and "no coincide" in r.json()["detalle"]
    # efectivo recibido menor al valor
    assert vender(api, item, [{"medio_pago_id": efectivo, "monto": 4200, "recibido": 4000}]).status_code == 400
    # dos pagos en efectivo no
    assert vender(api, item, [{"medio_pago_id": efectivo, "monto": 2000}, {"medio_pago_id": efectivo, "monto": 2200}]).status_code == 400
    # nada se guardó: stock intacto y consecutivo sigue en 1
    assert api.ok(api.get(f"/api/productos/{t.leche['id']}"))["stock_actual"] == 50
    v = api.ok(vender(api, item, [{"medio_pago_id": debito, "monto": 4200}]))
    assert v["numero"] == "POS-000001"


def test_cajero_no_accede_a_administracion(tienda):
    t, api = tienda, tienda.api
    api.login("carlos", "cajero1")
    for url in ("/api/dashboard", "/api/usuarios", "/api/inventario/alertas", "/api/respaldos", "/api/auditoria", "/api/compras"):
        assert api.get(url).status_code == 403, url
    assert api.post("/api/productos", {"nombre": "x", "precio_venta": 1}).status_code == 403
    api.token = None
    assert api.get("/api/productos").status_code == 401
