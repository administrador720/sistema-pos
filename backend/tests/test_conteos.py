"""Tomas de inventario: captura ciega, stock teórico al momento de contar, inconsistencias y ajustes."""
from datetime import date, datetime, timedelta

from app import core

from .conftest import abrir_turno_cajero, volver_admin


def nuevo_conteo(api, nombre="Conteo", tipo="total", alcance=None, iniciar=True):
    c = api.ok(api.post("/api/conteos", {"nombre": nombre, "tipo": tipo, "alcance": alcance or {}}))
    if iniciar:
        api.ok(api.post(f"/api/conteos/{c['id']}/iniciar"))
    return c["id"]


def contar(api, cid, codigo, cantidad):
    return api.ok(api.post(f"/api/conteos/{cid}/capturas", {"codigo": codigo, "cantidad": cantidad}))


def fila(rev, nombre):
    return next(f for f in rev["items"] if f["nombre"] == nombre)


def test_conteo_total_con_inconsistencias_y_ajuste(tienda):
    t, api = tienda, tienda.api
    cid = nuevo_conteo(api)
    # captura ciega: la respuesta no revela el stock del sistema
    r = contar(api, cid, "7701", 45)  # leche: sistema 50
    assert "stock" not in str(r).lower() and r["total_contado"] == 45
    contar(api, cid, "7701", 2)       # otra góndola: se suma → 47
    contar(api, cid, "7702", 41)      # arroz: sistema 40 → sobrante 1
    contar(api, cid, "7703", 20)      # aceite: sistema 20 → exacto
    api.ok(api.post(f"/api/conteos/{cid}/cerrar-captura"))
    rev = api.ok(api.get(f"/api/conteos/{cid}/revision"))
    leche, arroz, aceite = fila(rev, "Leche 1 L"), fila(rev, "Arroz 500 g"), fila(rev, "Aceite 1 L")
    assert (leche["stock_teorico"], leche["contado"], leche["diferencia"]) == (50, 47, -3)
    assert leche["valor_diferencia"] == -9000          # 3 u × costo 3.000
    assert (arroz["diferencia"], arroz["valor_diferencia"]) == (1, 2000)
    assert aceite["diferencia"] == 0
    s = rev["resumen"]
    assert (s["contados"], s["con_diferencia"], s["faltantes"], s["sobrantes"]) == (3, 2, 1, 1)
    assert s["valor_faltantes"] == -9000 and s["valor_sobrantes"] == 2000 and s["valor_neto"] == -7000
    assert s["exactitud_pct"] == 33.3

    # nada cambió hasta aplicar
    assert api.ok(api.get(f"/api/productos/{t.leche['id']}"))["stock_actual"] == 50
    c = api.ok(api.post(f"/api/conteos/{cid}/aplicar", {}))
    assert c["estado"] == "aplicado" and c["exactitud_pct"] == 33.3
    assert api.ok(api.get(f"/api/productos/{t.leche['id']}"))["stock_actual"] == 47
    assert api.ok(api.get(f"/api/productos/{t.arroz['id']}"))["stock_actual"] == 41
    k = api.ok(api.get(f"/api/inventario/kardex?producto_id={t.leche['id']}"))
    assert k[0]["tipo"] == "AJUSTE_CONTEO" and k[0]["cantidad"] == -3
    # un conteo aplicado es inmutable
    assert api.post(f"/api/conteos/{cid}/aplicar", {}).status_code == 409
    assert api.post(f"/api/conteos/{cid}/capturas", {"codigo": "7701", "cantidad": 1}).status_code == 409
    assert api.post(f"/api/conteos/{cid}/cancelar").status_code == 409
    # informe exportable
    assert api.get(f"/api/conteos/{cid}/informe?formato=pdf").content[:4] == b"%PDF"
    assert api.get(f"/api/conteos/{cid}/informe?formato=xlsx").status_code == 200


def test_ventas_durante_el_conteo_no_generan_diferencias_falsas(tienda):
    """Se cuenta con la tienda abierta: el stock teórico es el del momento en que se contó."""
    t, api = tienda, tienda.api
    ef = t.medios["Efectivo"]
    abrir_turno_cajero(t)
    # 1) se vende ANTES de contar → el conteo lo refleja
    api.ok(api.post("/api/ventas", {"items": [{"producto_id": t.leche["id"], "cantidad": 5}], "pagos": [{"medio_pago_id": ef, "monto": 21000}]}))
    volver_admin(t)
    cid = nuevo_conteo(api)
    contar(api, cid, "7701", 45)   # contó 45 y el sistema decía 45 → exacto
    contar(api, cid, "7703", 20)
    # 2) se vende DESPUÉS de contar (mientras otros siguen contando) → no debe verse como faltante
    api.login("carlos", "cajero1")
    api.ok(api.post("/api/ventas", {"items": [{"producto_id": t.leche["id"], "cantidad": 3}, {"producto_id": t.aceite["id"], "cantidad": 2}],
                                    "pagos": [{"medio_pago_id": ef, "monto": 12600 + 23000}]}))
    volver_admin(t)
    api.ok(api.post(f"/api/conteos/{cid}/cerrar-captura"))
    rev = api.ok(api.get(f"/api/conteos/{cid}/revision"))
    assert fila(rev, "Leche 1 L")["stock_teorico"] == 45 and fila(rev, "Leche 1 L")["diferencia"] == 0
    assert fila(rev, "Aceite 1 L")["stock_teorico"] == 20 and fila(rev, "Aceite 1 L")["diferencia"] == 0
    api.ok(api.post(f"/api/conteos/{cid}/aplicar", {}))
    # las ventas posteriores al conteo se respetan: 45 - 3 = 42 y 20 - 2 = 18
    assert api.ok(api.get(f"/api/productos/{t.leche['id']}"))["stock_actual"] == 42
    assert api.ok(api.get(f"/api/productos/{t.aceite['id']}"))["stock_actual"] == 18


def test_productos_no_contados_se_dejan_igual_o_se_asumen_en_cero(tienda):
    t, api = tienda, tienda.api
    cid = nuevo_conteo(api)
    contar(api, cid, "7701", 50)
    api.ok(api.post(f"/api/conteos/{cid}/cerrar-captura"))
    rev = api.ok(api.get(f"/api/conteos/{cid}/revision"))
    assert rev["resumen"]["no_contados"] == 2 and fila(rev, "Arroz 500 g")["no_contado"]
    api.ok(api.post(f"/api/conteos/{cid}/aplicar", {"asumir_cero_no_contados": False}))
    assert api.ok(api.get(f"/api/productos/{t.arroz['id']}"))["stock_actual"] == 40

    cid2 = nuevo_conteo(api, "Segundo")
    contar(api, cid2, "7701", 50)
    api.ok(api.post(f"/api/conteos/{cid2}/cerrar-captura"))
    api.ok(api.post(f"/api/conteos/{cid2}/aplicar", {"asumir_cero_no_contados": True}))
    assert api.ok(api.get(f"/api/productos/{t.arroz['id']}"))["stock_actual"] == 0
    assert api.ok(api.get(f"/api/productos/{t.aceite['id']}"))["stock_actual"] == 0


def test_reconteo_reemplaza_las_capturas_anteriores(tienda):
    t, api = tienda, tienda.api
    cid = nuevo_conteo(api)
    contar(api, cid, "7701", 30)  # error grande de conteo
    contar(api, cid, "7702", 40)
    contar(api, cid, "7703", 20)
    api.ok(api.post(f"/api/conteos/{cid}/cerrar-captura"))
    assert fila(api.ok(api.get(f"/api/conteos/{cid}/revision")), "Leche 1 L")["diferencia"] == -20
    api.ok(api.post(f"/api/conteos/{cid}/reconteo", {"producto_ids": [t.leche["id"]]}))
    # mientras hay un reconteo pendiente no se puede aplicar
    assert api.ok(api.get(f"/api/conteos/{cid}")) ["estado"] == "en_conteo"
    contar(api, cid, "7701", 50)
    api.ok(api.post(f"/api/conteos/{cid}/cerrar-captura"))
    rev = api.ok(api.get(f"/api/conteos/{cid}/revision"))
    assert fila(rev, "Leche 1 L")["contado"] == 50 and fila(rev, "Leche 1 L")["diferencia"] == 0
    assert rev["resumen"]["con_diferencia"] == 0 and rev["resumen"]["exactitud_pct"] == 100.0


def test_solo_un_conteo_en_curso_y_cancelar(tienda):
    t, api = tienda, tienda.api
    cid = nuevo_conteo(api)
    otro = nuevo_conteo(api, "Otro", iniciar=False)
    assert api.post(f"/api/conteos/{otro}/iniciar").status_code == 409
    api.ok(api.post(f"/api/conteos/{cid}/cancelar"))
    api.ok(api.post(f"/api/conteos/{otro}/iniciar"))


def test_faltantes_recurrentes_en_conteos_seguidos(tienda):
    t, api = tienda, tienda.api
    for n, contado in enumerate((48, 45, 40), start=1):  # faltante creciente en la leche
        cid = nuevo_conteo(api, f"Conteo {n}")
        contar(api, cid, "7701", contado)
        contar(api, cid, "7702", api.ok(api.get(f"/api/productos/{t.arroz['id']}"))["stock_actual"])
        api.ok(api.post(f"/api/conteos/{cid}/cerrar-captura"))
        rev = api.ok(api.get(f"/api/conteos/{cid}/revision"))
        leche = fila(rev, "Leche 1 L")
        if n == 1:
            assert leche["racha_faltantes"] == 0
        if n == 3:
            assert leche["racha_faltantes"] == 3 and rev["resumen"]["recurrentes"] == 1
        api.ok(api.post(f"/api/conteos/{cid}/aplicar", {}))
        # el stock del sistema baja a lo contado: para que haya nuevo faltante, se "repone" en el sistema
        api.ok(api.post("/api/inventario/ajustes", {"producto_id": t.leche["id"], "nuevo_stock": 50, "nota": "reposición de prueba"}))


def test_conteo_ciclico_prioriza_diferencias_previas_y_nunca_contados(tienda):
    t, api = tienda, tienda.api
    for i in range(5):  # Prod 0..4, nunca contados, de poco valor
        t.producto(f"Prod {i}", 1000, 500, 10 + i, f"88{i}")
    # primer conteo: leche con diferencia y arroz exacto (quedan "contados" con fecha)
    cid = nuevo_conteo(api, "Base")
    contar(api, cid, "7701", 40)
    contar(api, cid, "7702", 40)
    api.ok(api.post(f"/api/conteos/{cid}/cerrar-captura"))
    api.ok(api.post(f"/api/conteos/{cid}/aplicar", {}))
    # cíclico de 3: 1º lo que tuvo diferencia (leche); 2º lo nunca contado, el de mayor valor primero
    # (aceite 20×8.000, luego "Prod 4" 14×500); el arroz, contado y exacto, queda para otra vez
    cid2 = nuevo_conteo(api, "Cíclico", tipo="ciclico", alcance={"n": 3})
    assert api.ok(api.get(f"/api/conteos/{cid2}"))["progreso"]["productos"] == 3
    for codigo in ("7701", "7703", "884"):
        contar(api, cid2, codigo, 1)
    for fuera in ("7702", "880"):
        assert api.post(f"/api/conteos/{cid2}/capturas", {"codigo": fuera, "cantidad": 1}).status_code == 409


def test_programacion_recordatorios_y_siguiente_fecha(tienda, monkeypatch):
    t, api = tienda, tienda.api
    hoy = datetime(2026, 3, 10, 9, 0)
    monkeypatch.setattr(core, "reloj", lambda: hoy)
    p = api.ok(api.post("/api/conteos/programaciones", {"nombre": "Conteo mensual", "tipo": "total", "frecuencia": "mensual",
                                                         "intervalo": 1, "proxima_fecha": "2026-03-12"}))
    far = api.ok(api.post("/api/conteos/programaciones", {"nombre": "Lejano", "tipo": "total", "frecuencia": "semanal",
                                                           "proxima_fecha": "2026-05-01"}))
    d = api.ok(api.get("/api/dashboard"))
    rec = d["conteos"]["recordatorios"]
    assert [r["nombre"] for r in rec] == ["Conteo mensual"] and rec[0]["dias_restantes"] == 2 and not rec[0]["vencida"]
    # el administrador lo inicia cuando quiere → la próxima fecha se calcula desde hoy
    c = api.ok(api.post(f"/api/conteos/programaciones/{p['id']}/iniciar"))
    assert c["estado"] == "en_conteo"
    prog = {x["id"]: x for x in api.ok(api.get("/api/conteos/programaciones"))}
    assert prog[p["id"]]["proxima_fecha"] == "2026-04-10"
    # una_vez se desactiva solo
    u = api.ok(api.post("/api/conteos/programaciones", {"nombre": "Única", "frecuencia": "una_vez", "proxima_fecha": "2026-03-11"}))
    api.ok(api.post(f"/api/conteos/{c['id']}/cancelar"))
    api.ok(api.post(f"/api/conteos/programaciones/{u['id']}/iniciar"))
    assert {x["id"]: x for x in api.ok(api.get("/api/conteos/programaciones"))}[u["id"]]["activo"] is False
    # vencida: se marca
    monkeypatch.setattr(core, "reloj", lambda: datetime(2026, 4, 20, 9, 0))
    rec = api.ok(api.get("/api/dashboard"))["conteos"]["recordatorios"]
    assert any(r["nombre"] == "Conteo mensual" and r["vencida"] for r in rec)


def test_el_cajero_puede_contar_pero_no_ve_la_revision(tienda):
    t, api = tienda, tienda.api
    cid = nuevo_conteo(api)
    api.login("carlos", "cajero1")
    assert [c["id"] for c in api.ok(api.get("/api/conteos"))] == [cid]
    contar(api, cid, "7701", 10)
    assert api.get(f"/api/conteos/{cid}/revision").status_code == 403
    assert api.post(f"/api/conteos/{cid}/aplicar", {}).status_code == 403
    assert api.post("/api/conteos", {"nombre": "x"}).status_code == 403
    assert api.post(f"/api/conteos/{cid}/capturas", {"codigo": "NOEXISTE", "cantidad": 1}).status_code == 404
