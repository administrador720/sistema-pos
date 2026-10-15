import io

from openpyxl import Workbook

from .conftest import abrir_turno_cajero, volver_admin


def test_compra_actualiza_stock_y_costo_promedio_ponderado(tienda):
    t, api = tienda, tienda.api
    # leche: 50 u a costo 3.000. Compra 50 u a 3.600 → costo promedio (50*3000 + 50*3600)/100 = 3.300
    c = api.ok(api.post("/api/compras", {"numero_factura": "F-77", "items": [
        {"producto_id": t.leche["id"], "cantidad": 50, "costo_unitario": 3600, "nuevo_precio": 4500}]}))
    assert c["total"] == 180000
    p = api.ok(api.get(f"/api/productos/{t.leche['id']}"))
    assert p["stock_actual"] == 100 and p["costo_promedio"] == 3300 and p["precio_venta"] == 4500
    hist = api.ok(api.get(f"/api/productos/{t.leche['id']}/historial-precios"))
    assert hist[0]["anterior"] == 4200 and hist[0]["nuevo"] == 4500
    # kardex: saldo inicial + compra, con saldo corrido
    k = api.ok(api.get(f"/api/inventario/kardex?producto_id={t.leche['id']}"))
    assert [(x["tipo"], x["cantidad"], x["stock_resultante"]) for x in reversed(k)] == [("SALDO_INICIAL", 50, 50), ("COMPRA", 50, 100)]


def test_compra_con_stock_cero_o_negativo_toma_el_costo_de_la_compra(tienda):
    t, api = tienda, tienda.api
    api.ok(api.post("/api/inventario/ajustes", {"producto_id": t.arroz["id"], "nuevo_stock": -5, "nota": "descuadre"}))
    api.ok(api.post("/api/compras", {"items": [{"producto_id": t.arroz["id"], "cantidad": 20, "costo_unitario": 2500}]}))
    p = api.ok(api.get(f"/api/productos/{t.arroz['id']}"))
    assert p["stock_actual"] == 15 and p["costo_promedio"] == 2500


def test_mermas_ajustes_y_alertas(tienda):
    t, api = tienda, tienda.api
    api.ok(api.post("/api/inventario/mermas", {"producto_id": t.leche["id"], "cantidad": 3, "motivo": "VENCIDO"}))
    assert api.ok(api.get(f"/api/productos/{t.leche['id']}"))["stock_actual"] == 47
    assert api.post("/api/inventario/mermas", {"producto_id": t.leche["id"], "cantidad": 1, "motivo": "XX"}).status_code == 400
    # un ajuste exige motivo
    assert api.post("/api/inventario/ajustes", {"producto_id": t.leche["id"], "nuevo_stock": 10, "nota": " "}).status_code == 400
    api.ok(api.post("/api/inventario/ajustes", {"producto_id": t.leche["id"], "nuevo_stock": 5, "nota": "conteo rápido"}))
    api.ok(api.put(f"/api/productos/{t.leche['id']}", {"stock_minimo": 10}))
    api.ok(api.put(f"/api/productos/{t.arroz['id']}", {"stock_minimo": 5}))
    api.ok(api.post("/api/inventario/ajustes", {"producto_id": t.arroz["id"], "nuevo_stock": 0, "nota": "agotado"}))
    api.ok(api.post("/api/inventario/ajustes", {"producto_id": t.aceite["id"], "nuevo_stock": -2, "nota": "negativo"}))
    a = api.ok(api.get("/api/inventario/alertas"))
    assert [x["nombre"] for x in a["bajo_minimo"]] == ["Leche 1 L"]
    assert [x["nombre"] for x in a["agotados"]] == ["Arroz 500 g"]
    assert [x["nombre"] for x in a["negativos"]] == ["Aceite 1 L"]


def test_codigo_de_barras_repetido_y_paca_con_varias_unidades(tienda):
    t, api = tienda, tienda.api
    # el mismo código no puede pertenecer a dos productos
    r = api.post("/api/productos", {"nombre": "Otro", "precio_venta": 100, "codigos": [{"codigo": "7701"}]})
    assert r.status_code == 409
    # un código de paca de 6 unidades
    api.ok(api.put(f"/api/productos/{t.leche['id']}", {"codigos": [{"codigo": "7701", "unidades": 1}, {"codigo": "PACA6", "unidades": 6}]}))
    abrir_turno_cajero(t)
    r = api.ok(api.get("/api/productos/codigo/PACA6"))
    assert r["id"] == t.leche["id"] and r["unidades_por_codigo"] == 6
    assert api.get("/api/productos/codigo/NOEXISTE").status_code == 404


def test_cambio_masivo_de_precios_con_simulacion_y_redondeo(tienda):
    t, api = tienda, tienda.api
    sim = api.ok(api.post("/api/productos/precios-masivo", {"porcentaje": 10, "redondeo": 50, "simular": True}))
    assert sim["afectados"] == 3 and not sim["aplicado"]
    assert api.ok(api.get(f"/api/productos/{t.leche['id']}"))["precio_venta"] == 4200  # simular no cambia nada
    api.ok(api.post("/api/productos/precios-masivo", {"porcentaje": 10, "redondeo": 50, "simular": False}))
    # 4.200 * 1,10 = 4.620 → 4.600 ; 2.900 * 1,10 = 3.190 → 3.200 ; 11.500 * 1,10 = 12.650 → 12.650
    assert api.ok(api.get(f"/api/productos/{t.leche['id']}"))["precio_venta"] == 4600
    assert api.ok(api.get(f"/api/productos/{t.arroz['id']}"))["precio_venta"] == 3200
    assert api.ok(api.get(f"/api/productos/{t.aceite['id']}"))["precio_venta"] == 12650


def _xlsx(filas):
    wb = Workbook()
    ws = wb.active
    for f in filas:
        ws.append(f)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_importar_desde_excel_simula_valida_y_aplica(tienda):
    t, api = tienda, tienda.api
    enc = ["codigo_barras", "nombre", "categoria", "proveedor", "impuesto", "costo", "precio", "stock_inicial", "stock_minimo"]
    bueno = _xlsx([enc, ["7790001", "Galletas", "Dulces", "Alimentos SA", "IVA 19%", 1200, 2000, 30, 5],
                   ["7790002", "Sal 1 kg", "Despensa", "", "Excluido", 900, "1.500", 12, 3]])
    files = lambda c: {"archivo": ("p.xlsx", c, "application/octet-stream")}  # noqa: E731
    r = api.ok(api.post("/api/productos/importar?simular=true", files=files(bueno)))
    assert r["creados"] == 2 and r["errores"] == [] and not r["aplicado"]
    assert api.ok(api.get("/api/productos?q=Galletas"))["total"] == 0  # simulación: no creó nada
    r = api.ok(api.post("/api/productos/importar?simular=false", files=files(bueno)))
    assert r["aplicado"]
    sal = api.ok(api.get("/api/productos?q=Sal"))["productos"][0]
    assert sal["precio_venta"] == 1500 and sal["stock_actual"] == 12 and sal["categoria"] == "Despensa"
    # reimportar el mismo código actualiza en vez de duplicar
    otra = _xlsx([enc, ["7790001", "Galletas Saladas", "Dulces", "", "IVA 19%", 1300, 2100, 0, 5]])
    r = api.ok(api.post("/api/productos/importar?simular=false", files=files(otra)))
    assert r["actualizados"] == 1 and r["creados"] == 0
    assert api.ok(api.get("/api/productos?q=Galletas"))["productos"][0]["precio_venta"] == 2100
    # filas con error: no se importa nada
    malo = _xlsx([enc, ["7790009", "Bueno", "", "", "IVA 19%", 1, 2, 1, 1], ["7790010", "Malo", "", "", "IVA 99%", 1, 2, 1, 1]])
    r = api.post("/api/productos/importar?simular=false", files=files(malo))
    assert r.status_code == 422
    assert api.ok(api.get("/api/productos?q=Bueno"))["total"] == 0
    assert api.get("/api/productos/plantilla").status_code == 200
