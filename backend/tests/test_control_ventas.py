"""Anulaciones, devoluciones, descuentos, stock y ventas suspendidas."""
from .conftest import abrir_turno_cajero, volver_admin


def vender(api, items, pagos, pin=None, **extra):
    return api.post("/api/ventas", {"items": items, "pagos": pagos, **extra}, pin=pin)


def test_anular_exige_pin_admin_y_devuelve_stock(tienda):
    t, api = tienda, tienda.api
    ef = t.medios["Efectivo"]
    abrir_turno_cajero(t)
    v = api.ok(vender(api, [{"producto_id": t.leche["id"], "cantidad": 4}], [{"medio_pago_id": ef, "monto": 16800}]))
    assert api.ok(api.get(f"/api/productos/{t.leche['id']}"))["stock_actual"] == 46
    # sin PIN o con PIN equivocado: no
    r = api.post(f"/api/ventas/{v['id']}/anular", {"motivo": "error de cajero"})
    assert r.status_code == 403 and r.json()["codigo"] == "REQUIERE_AUTORIZACION"
    assert api.post(f"/api/ventas/{v['id']}/anular", {"motivo": "x"}, pin="9999").status_code == 403
    # con el PIN del administrador (1234) sí
    a = api.ok(api.post(f"/api/ventas/{v['id']}/anular", {"motivo": "error de cajero"}, pin="1234"))
    assert a["estado"] == "anulada"
    assert api.ok(api.get(f"/api/productos/{t.leche['id']}"))["stock_actual"] == 50
    # no se anula dos veces y ya no cuenta en el turno
    assert api.post(f"/api/ventas/{v['id']}/anular", {"motivo": "x"}, pin="1234").status_code == 409
    assert api.ok(api.get("/api/turnos/actual"))["resumen"]["ventas_n"] == 0
    # quedó auditado con quién autorizó
    volver_admin(t)
    aud = api.ok(api.get("/api/auditoria?accion=ANULACION_VENTA"))["filas"]
    assert aud and aud[0]["usuario"] == "Carlos Cajero" and aud[0]["autorizado_por"] == "Ana Admin"


def test_solo_se_anulan_ventas_del_turno_abierto(tienda):
    t, api = tienda, tienda.api
    ef = t.medios["Efectivo"]
    turno = abrir_turno_cajero(t)
    v = api.ok(vender(api, [{"producto_id": t.leche["id"], "cantidad": 1}], [{"medio_pago_id": ef, "monto": 4200}]))
    api.ok(api.post(f"/api/turnos/{turno['id']}/cerrar", {"efectivo_contado": 104200, "banco_reportado": 0}))
    api.ok(api.post("/api/turnos/abrir", {"base": 50000}))
    r = api.post(f"/api/ventas/{v['id']}/anular", {"motivo": "tarde"}, pin="1234")
    assert r.status_code == 409 and r.json()["codigo"] == "FUERA_DE_TURNO"


def test_devolucion_parcial_danada_y_reintegro(tienda):
    t, api = tienda, tienda.api
    ef, deb = t.medios["Efectivo"], t.medios["Tarjeta débito"]
    turno = abrir_turno_cajero(t, base=100000)
    v = api.ok(vender(api, [{"producto_id": t.aceite["id"], "cantidad": 3}], [{"medio_pago_id": deb, "monto": 34500}]))
    item = v["items"][0]
    # devuelve 1 sano y 1 dañado; el reintegro por banco no puede exceder lo pagado
    d1 = api.ok(api.post(f"/api/ventas/{v['id']}/devolucion", {
        "items": [{"venta_item_id": item["id"], "cantidad": 1}], "medio_reintegro": "banco", "motivo": "no le gustó"}, pin="1234"))
    assert d1["total"] == 11500
    d2 = api.ok(api.post(f"/api/ventas/{v['id']}/devolucion", {
        "items": [{"venta_item_id": item["id"], "cantidad": 1, "danado": True}], "medio_reintegro": "efectivo", "motivo": "llegó roto"}, pin="1234"))
    assert d2["total"] == 11500
    # solo quedaba 1 por devolver: pedir 2 falla; pedir 1 cierra la línea
    r = api.post(f"/api/ventas/{v['id']}/devolucion", {"items": [{"venta_item_id": item["id"], "cantidad": 2}],
                                                         "medio_reintegro": "efectivo", "motivo": "x"}, pin="1234")
    assert r.status_code == 400
    # stock: 20 - 3 vendidos + 1 devuelto sano + 1 devuelto dañado (entra y sale como merma) = 18
    assert api.ok(api.get(f"/api/productos/{t.aceite['id']}"))["stock_actual"] == 18
    # arqueo: el reintegro en efectivo (11.500) sale de la caja; el de banco resta del banco esperado
    z = api.ok(api.post(f"/api/turnos/{turno['id']}/cerrar", {"efectivo_contado": 100000 - 11500, "banco_reportado": 34500 - 11500}))
    assert z["turno"]["efectivo_esperado"] == 88500 and z["turno"]["diferencia_efectivo"] == 0
    assert z["turno"]["banco_esperado"] == 23000 and z["turno"]["diferencia_banco"] == 0
    # la devolución dañada quedó como merma "DANADO"
    volver_admin(t)
    k = api.ok(api.get(f"/api/inventario/kardex?producto_id={t.aceite['id']}"))
    assert any(x["tipo"] == "MERMA" and x["motivo"] == "DANADO" for x in k)


def test_reintegro_por_banco_no_excede_lo_pagado_por_banco(tienda):
    t, api = tienda, tienda.api
    ef = t.medios["Efectivo"]
    abrir_turno_cajero(t)
    v = api.ok(vender(api, [{"producto_id": t.leche["id"], "cantidad": 1}], [{"medio_pago_id": ef, "monto": 4200}]))
    r = api.post(f"/api/ventas/{v['id']}/devolucion", {"items": [{"venta_item_id": v["items"][0]["id"], "cantidad": 1}],
                                                         "medio_reintegro": "banco", "motivo": "x"}, pin="1234")
    assert r.status_code == 400 and "banco" in r.json()["detalle"]


def test_descuento_sobre_el_limite_exige_pin(tienda):
    t, api = tienda, tienda.api
    ef = t.medios["Efectivo"]
    abrir_turno_cajero(t)
    item = [{"producto_id": t.aceite["id"], "cantidad": 1, "descuento": 2300}]  # 20 % de 11.500 (el límite es 10 %)
    pago = [{"medio_pago_id": ef, "monto": 9200}]
    r = vender(api, item, pago)
    assert r.status_code == 403 and r.json()["codigo"] == "REQUIERE_AUTORIZACION"
    v = api.ok(vender(api, item, pago, pin="1234"))
    assert v["descuento_total"] == 2300 and v["total"] == 9200
    # 10 % o menos pasa sin PIN
    api.ok(vender(api, [{"producto_id": t.aceite["id"], "cantidad": 1, "descuento": 1150}], [{"medio_pago_id": ef, "monto": 10350}]))
    # el descuento global se reparte entre las líneas y los impuestos se recalculan sobre el neto
    v = api.ok(vender(api, [{"producto_id": t.aceite["id"], "cantidad": 1}, {"producto_id": t.leche["id"], "cantidad": 1}],
                      [{"medio_pago_id": ef, "monto": 14130}], descuento_global=1570))
    assert sum(i["total"] for i in v["items"]) == 14130 and v["descuento_total"] == 1570


def test_stock_negativo_se_puede_bloquear_por_configuracion(tienda):
    t, api = tienda, tienda.api
    ef = t.medios["Efectivo"]
    abrir_turno_cajero(t)
    pedido = [{"producto_id": t.leche["id"], "cantidad": 60}]
    pago = [{"medio_pago_id": ef, "monto": 252000}]
    api.ok(vender(api, pedido, pago))  # permitido por defecto: queda en -10
    assert api.ok(api.get(f"/api/productos/{t.leche['id']}"))["stock_actual"] == -10
    volver_admin(t)
    api.ok(api.put("/api/config", {"valores": {"permitir_stock_negativo": False}}))
    api.login("carlos", "cajero1")
    r = vender(api, pedido, pago)
    assert r.status_code == 409 and r.json()["codigo"] == "STOCK_INSUFICIENTE"


def test_suspender_y_retomar_venta(tienda):
    t, api = tienda, tienda.api
    turno = abrir_turno_cajero(t)
    carrito = {"items": [{"producto_id": t.leche["id"], "cantidad": 2}], "total": 8400}
    s = api.ok(api.post("/api/ventas-suspendidas", {"carrito": carrito, "etiqueta": "Señora de rojo"}))
    assert api.ok(api.get("/api/ventas-suspendidas"))[0]["etiqueta"] == "Señora de rojo"
    # con una venta suspendida no se puede cerrar el turno
    r = api.post(f"/api/turnos/{turno['id']}/cerrar", {"efectivo_contado": 100000, "banco_reportado": 0})
    assert r.status_code == 409 and r.json()["codigo"] == "VENTAS_SUSPENDIDAS"
    assert api.ok(api.post(f"/api/ventas-suspendidas/{s['id']}/retomar"))["items"][0]["cantidad"] == 2
    assert api.ok(api.get("/api/ventas-suspendidas")) == []


def test_retiros_de_caja_exigen_autorizacion_y_motivo(tienda):
    t, api = tienda, tienda.api
    turno = abrir_turno_cajero(t, base=100000)
    mov = lambda **k: api.post(f"/api/turnos/{turno['id']}/movimientos", k.pop("body"), **k)  # noqa: E731
    assert mov(body={"tipo": "retiro", "monto": 50000, "motivo": "recogida"}).status_code == 403
    assert mov(body={"tipo": "retiro", "monto": 50000, "motivo": ""}, pin="1234").status_code == 400
    api.ok(mov(body={"tipo": "retiro", "monto": 50000, "motivo": "recogida de billetes"}, pin="1234"))
    api.ok(mov(body={"tipo": "ingreso", "monto": 10000, "motivo": "refuerzo de base"}))
    z = api.ok(api.post(f"/api/turnos/{turno['id']}/cerrar", {"efectivo_contado": 60000, "banco_reportado": 0}))
    assert z["turno"]["efectivo_esperado"] == 60000 and z["turno"]["diferencia_efectivo"] == 0
