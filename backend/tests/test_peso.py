"""Productos por peso (verduras y frutas): kilos con gramos, venta por peso o por valor, stock sin deriva,
devoluciones parciales, conteos, compras, importación y la migración de bases de datos anteriores."""
import io
import sqlite3

import pytest

from app import core

from .conftest import abrir_turno_cajero, volver_admin


def vender(api, items, total, medio, **extra):
    return api.post("/api/ventas", {"items": items, "pagos": [{"medio_pago_id": medio, "monto": total, "recibido": total}], **extra})


@pytest.fixture()
def verduras(tienda):
    """Tomate ($3.500/kg, 40,5 kg), cebolla y una fruta; el tomate es botón rápido con PLU 101."""
    t = tienda
    t.tomate = t.producto("Tomate chonto", 3500, 2400, 40.5, "", impuesto="Excluido", unidad="kg", rapido=True,
                          codigo_interno="101", codigos=[])
    t.cebolla = t.producto("Cebolla cabezona", 2800, 1800, 25, "", impuesto="Excluido", unidad="kg", codigo_interno="102",
                           codigos=[])
    t.efectivo = t.medios["Efectivo"]
    return t


def stock(api, p):
    return api.ok(api.get(f"/api/productos/{p['id']}"))["stock_actual"]


def test_funciones_de_dinero_exactas():
    assert core.valor_linea(3500, 0.35) == 1225
    assert core.valor_linea(3001, 0.5) == 1501      # 1.500,5 → mitad hacia arriba
    assert core.valor_linea(2900, 3) == 8700        # unidades enteras siguen exactas
    assert core.valor_linea(3500, 1.429) == 5002    # 5.001,5
    assert core.cant(0.1 + 0.2) == 0.3 and core.cant(5.0) == 5 and isinstance(core.cant(5.0), int)
    assert core.cant(1.2346) == 1.235


def test_producto_por_peso_se_crea_y_se_busca_por_plu(verduras):
    t, api = verduras, verduras.api
    assert t.tomate["unidad"] == "kg" and t.tomate["rapido"] is True and t.tomate["stock_actual"] == 40.5
    # el PLU (código interno) funciona como código corto
    r = api.ok(api.get("/api/productos/codigo/101"))
    assert r["nombre"] == "Tomate chonto" and r["unidad"] == "kg"
    # botones rápidos: solo el marcado
    assert [p["nombre"] for p in api.ok(api.get("/api/productos/rapidos"))] == ["Tomate chonto"]
    # un producto por unidad no puede tener stock decimal
    r = api.post("/api/productos", {"nombre": "Galleta", "precio_venta": 1000, "stock_inicial": 2.5})
    assert r.status_code == 400 and "entero" in r.json()["detalle"]


def test_venta_por_peso_y_por_valor(verduras):
    t, api = verduras, verduras.api
    abrir_turno_cajero(t)
    # 0,350 kg × $3.500 = $1.225
    v = api.ok(vender(api, [{"producto_id": t.tomate["id"], "cantidad": 0.35}], 1225, t.efectivo))
    assert v["total"] == 1225
    assert (v["items"][0]["cantidad"], v["items"][0]["unidad"], v["items"][0]["precio_unitario"]) == (0.35, "kg", 3500)
    assert stock(api, t.tomate) == 40.15
    # «$5.000 de tomate»: se cobra exactamente $5.000 y el peso sale del precio por kilo
    v = api.ok(vender(api, [{"producto_id": t.tomate["id"], "valor": 5000}], 5000, t.efectivo))
    assert v["total"] == 5000 and v["items"][0]["cantidad"] == 1.429
    assert stock(api, t.tomate) == 38.721
    # el servidor no acepta un total distinto al que calcula
    assert vender(api, [{"producto_id": t.tomate["id"], "cantidad": 0.35}], 1200, t.efectivo).status_code == 400
    # más de tres decimales se redondean al gramo
    v = api.ok(vender(api, [{"producto_id": t.cebolla["id"], "cantidad": 0.3333}], 932, t.efectivo))  # 0,333 × 2.800 = 932,4
    assert v["items"][0]["cantidad"] == 0.333 and v["total"] == 932


def test_valores_invalidos(verduras):
    t, api = verduras, verduras.api
    abrir_turno_cajero(t)
    ef = t.efectivo
    # cero, negativo y exceso absurdo de peso
    for cantidad in (0, -1, 2500):
        assert vender(api, [{"producto_id": t.tomate["id"], "cantidad": cantidad}], 1000, ef).status_code == 400
    # menos de un gramo
    r = vender(api, [{"producto_id": t.tomate["id"], "cantidad": 0.0004}], 1000, ef)
    assert r.status_code == 400
    # un producto por unidad no admite decimales ni valor en pesos
    r = vender(api, [{"producto_id": t.leche["id"], "cantidad": 1.5}], 6300, ef)
    assert r.status_code == 400 and "entero" in r.json()["detalle"]
    r = vender(api, [{"producto_id": t.leche["id"], "valor": 5000}], 5000, ef)
    assert r.status_code == 400 and "por unidad" in r.json()["detalle"]
    # sin cantidad ni valor
    assert vender(api, [{"producto_id": t.tomate["id"]}], 1000, ef).status_code == 400
    assert stock(api, t.tomate) == 40.5  # nada se descontó


def sin_stock_negativo(api):
    api.ok(api.put("/api/config", {"valores": {"permitir_stock_negativo": False}}))


def test_stock_insuficiente_habla_en_kilos(verduras):
    t, api = verduras, verduras.api
    sin_stock_negativo(api)
    abrir_turno_cajero(t)
    r = vender(api, [{"producto_id": t.tomate["id"], "cantidad": 41}], 143500, t.efectivo)
    assert r.status_code == 409 and r.json()["codigo"] == "STOCK_INSUFICIENTE"
    assert "40,500 kg" in r.json()["detalle"] and "41,000 kg" in r.json()["detalle"]


def test_el_stock_no_acumula_ruido_de_decimales(verduras):
    t, api = verduras, verduras.api
    p = t.producto("Ají", 1000, 500, 1, "", impuesto="Excluido", unidad="kg", codigos=[])
    sin_stock_negativo(api)
    abrir_turno_cajero(t)
    for _ in range(10):  # 10 × 0,1 kg con aritmética de coma flotante común dejaría 1,3e-16
        api.ok(vender(api, [{"producto_id": p["id"], "cantidad": 0.1}], 100, t.efectivo))
    assert stock(api, p) == 0
    assert vender(api, [{"producto_id": p["id"], "cantidad": 0.001}], 1, t.efectivo).status_code == 409


def test_devolucion_parcial_de_producto_por_peso(verduras):
    t, api = verduras, verduras.api
    abrir_turno_cajero(t)
    v = api.ok(vender(api, [{"producto_id": t.tomate["id"], "cantidad": 2}], 7000, t.efectivo))
    item = v["items"][0]["id"]

    def devolver(cantidad, **kw):
        return api.post(f"/api/ventas/{v['id']}/devolucion", {"items": [{"venta_item_id": item, "cantidad": cantidad, **kw}],
                                                              "medio_reintegro": "efectivo", "motivo": "Se pudrió"}, pin="1234")
    d1 = api.ok(devolver(0.75))
    assert d1["total"] == 2625 and stock(api, t.tomate) == 39.25
    # no se puede devolver más de lo que queda (1,250 kg)
    r = devolver(1.5)
    assert r.status_code == 400 and "1,250 kg" in r.json()["detalle"]
    d2 = api.ok(devolver(1.25, danado=True))  # la última devolución cierra la línea sin diferencias de redondeo
    assert d1["total"] + d2["total"] == 7000
    assert stock(api, t.tomate) == 39.25     # lo dañado vuelve y sale enseguida como merma: solo regresan los 0,75 kg buenos
    rec = api.ok(api.get(f"/api/ventas/{v['id']}"))
    assert rec["items"][0]["devuelto"] == 2


def test_compra_merma_y_ajuste_con_decimales(verduras):
    t, api = verduras, verduras.api
    # compra de 9,5 kg a $2.600: costo promedio = (40,5 × 2.400 + 9,5 × 2.600) / 50 = 2.438
    api.ok(api.post("/api/compras", {"items": [{"producto_id": t.tomate["id"], "cantidad": 9.5, "costo_unitario": 2600}]}))
    p = api.ok(api.get(f"/api/productos/{t.tomate['id']}"))
    assert p["stock_actual"] == 50 and p["costo_promedio"] == 2438
    api.ok(api.post("/api/inventario/mermas", {"producto_id": t.tomate["id"], "cantidad": 0.75, "motivo": "DANADO"}))
    assert stock(api, t.tomate) == 49.25
    r = api.ok(api.post("/api/inventario/ajustes", {"producto_id": t.tomate["id"], "nuevo_stock": 48.9, "nota": "Báscula"}))
    assert r["stock_resultante"] == 48.9
    k = api.ok(api.get(f"/api/inventario/kardex?producto_id={t.tomate['id']}"))
    assert [x["cantidad"] for x in k[:2]] == [-0.35, -0.75]
    # un producto por unidad rechaza decimales en compras, mermas y ajustes
    assert api.post("/api/compras", {"items": [{"producto_id": t.leche["id"], "cantidad": 1.5, "costo_unitario": 100}]}).status_code == 400
    assert api.post("/api/inventario/mermas", {"producto_id": t.leche["id"], "cantidad": 0.5, "motivo": "DANADO"}).status_code == 400
    assert api.post("/api/inventario/ajustes", {"producto_id": t.leche["id"], "delta": 0.5, "nota": "x"}).status_code == 400


def test_conteo_de_producto_por_peso(verduras):
    t, api = verduras, verduras.api
    cid = api.ok(api.post("/api/conteos", {"nombre": "Verduras", "tipo": "total", "alcance": {}}))["id"]
    api.ok(api.post(f"/api/conteos/{cid}/iniciar"))
    r = api.ok(api.post(f"/api/conteos/{cid}/capturas", {"codigo": "101", "cantidad": 20.1}))
    assert r["total_contado"] == 20.1
    api.ok(api.post(f"/api/conteos/{cid}/capturas", {"codigo": "101", "cantidad": 20.3}))   # otra caja
    api.ok(api.post(f"/api/conteos/{cid}/capturas", {"codigo": "102", "cantidad": 25}))
    assert api.post(f"/api/conteos/{cid}/capturas", {"codigo": "7701", "cantidad": 2.5}).status_code in (400, 409)
    api.ok(api.post(f"/api/conteos/{cid}/cerrar-captura"))
    rev = api.ok(api.get(f"/api/conteos/{cid}/revision"))
    tom = next(f for f in rev["items"] if f["nombre"] == "Tomate chonto")
    assert (tom["stock_teorico"], tom["contado"], tom["diferencia"], tom["unidad"]) == (40.5, 40.4, -0.1, "kg")
    assert tom["valor_diferencia"] == -240           # 0,1 kg × $2.400
    api.ok(api.post(f"/api/conteos/{cid}/aplicar", {"asumir_cero_no_contados": True}))
    assert stock(api, t.tomate) == 40.4


def test_no_se_cambia_la_unidad_de_un_producto_con_historia(verduras):
    t, api = verduras, verduras.api
    r = api.put(f"/api/productos/{t.tomate['id']}", {"unidad": "u"})
    assert r.status_code == 409 and "movimientos" in r.json()["detalle"]
    nuevo = api.ok(api.post("/api/productos", {"nombre": "Limón", "precio_venta": 3000}))
    assert nuevo["unidad"] == "u"
    assert api.ok(api.put(f"/api/productos/{nuevo['id']}", {"unidad": "kg", "rapido": True}))["unidad"] == "kg"
    assert [p["nombre"] for p in api.ok(api.get("/api/productos/rapidos"))] == ["Limón", "Tomate chonto"]


def test_el_cajero_ve_botones_rapidos_sin_costos(verduras):
    t, api = verduras, verduras.api
    abrir_turno_cajero(t)
    r = api.ok(api.get("/api/productos/rapidos"))
    assert r[0]["nombre"] == "Tomate chonto" and "costo_promedio" not in r[0]


def test_importar_excel_con_unidad(verduras):
    t, api = verduras, verduras.api
    csv = ("nombre;precio;costo;stock_inicial;unidad;plu\n"
           "Pimentón rojo;6000;4000;12,5;kg;201\n"
           "Jabón;2500;1500;10;u;\n"
           "Mal;1000;500;2,5;u;\n").encode()
    r = api.ok(api.post("/api/productos/importar?simular=true", files={"archivo": ("p.csv", io.BytesIO(csv))}))
    assert r["creados"] == 2 and len(r["errores"]) == 1 and "entero" in r["errores"][0]["error"]
    csv_ok = csv.rsplit(b"Mal", 1)[0]
    r = api.ok(api.post("/api/productos/importar?simular=false", files={"archivo": ("p.csv", io.BytesIO(csv_ok))}))
    assert r["creados"] == 2
    pim = api.ok(api.get("/api/productos/codigo/201"))
    assert pim["unidad"] == "kg" and pim["stock_actual"] == 12.5


def test_informes_y_recibo_con_kilos(verduras):
    t, api = verduras, verduras.api
    abrir_turno_cajero(t)
    v = api.ok(vender(api, [{"producto_id": t.tomate["id"], "cantidad": 1.25}, {"producto_id": t.leche["id"], "cantidad": 2}],
                      4375 + 8400, t.efectivo))
    assert api.get(f"/api/ventas/{v['id']}/recibo").content[:4] == b"%PDF"
    volver_admin(t)
    inf = api.ok(api.get("/api/informes/ventas_producto"))
    fila = next(f for f in inf["filas"] if f["nombre"] == "Tomate chonto")
    assert fila["unidades"] == 1.25
    assert any(c["tipo"] == "cantidad" for c in inf["columnas"])
    for fmt in ("xlsx", "pdf"):
        assert api.get(f"/api/informes/ventas_producto?formato={fmt}").status_code == 200
    # el kilo no cuenta como «unidad» en las unidades por tiquete del panel
    d = api.ok(api.get("/api/dashboard"))
    assert d["kpis"]["unidades_por_ticket"] == 2
    al = api.ok(api.get("/api/inventario/alertas"))
    assert "total" in al


def test_migracion_de_una_base_anterior(tmp_path):
    """Una base creada antes de los productos por peso recibe las columnas nuevas y conserva sus datos."""
    ruta = tmp_path / "vieja.db"
    con = sqlite3.connect(ruta)
    con.executescript("""
        CREATE TABLE productos (id INTEGER PRIMARY KEY, nombre VARCHAR(200), stock_actual INTEGER DEFAULT 0);
        INSERT INTO productos (nombre, stock_actual) VALUES ('Leche', 12);
        CREATE TABLE venta_items (id INTEGER PRIMARY KEY, cantidad INTEGER);
        INSERT INTO venta_items (cantidad) VALUES (3);
    """)
    con.commit()
    con.close()
    from app import db as db_mod
    eng = db_mod.configurar(ruta)
    with eng.begin() as c:
        db_mod._m2_productos_por_peso(c)
        db_mod._m2_productos_por_peso(c)  # idempotente
    con = sqlite3.connect(ruta)
    assert con.execute("SELECT nombre, stock_actual, unidad, rapido FROM productos").fetchall() == [("Leche", 12, "u", 0)]
    # una columna INTEGER guarda kilos con decimales sin cambiar el esquema
    con.execute("INSERT INTO venta_items (cantidad) VALUES (1.25)")
    assert con.execute("SELECT cantidad FROM venta_items ORDER BY id").fetchall() == [(3,), (1.25,)]
    con.close()
    eng.dispose()
