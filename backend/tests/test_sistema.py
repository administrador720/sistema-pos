"""Robustez: respaldos, intentos fallidos, atomicidad, concurrencia y corte de energía."""
import os
import signal
import sqlite3
import subprocess
import sys
import textwrap
import threading
from pathlib import Path

from app import config, core, db as db_mod
from app.core import ErrorNegocio
from app.services import inventario as inv
from app.services import ventas as ventas_svc

from .conftest import abrir_turno_cajero, volver_admin

BACKEND = Path(__file__).resolve().parents[1]


# ───────────────────────────── Respaldos ─────────────────────────────
def test_respaldo_y_restauracion(tienda, tmp_path):
    t, api = tienda, tienda.api
    externa = tmp_path / "usb"
    api.ok(api.put("/api/config", {"valores": {"respaldo_carpeta_externa": str(externa)}}))
    r = api.ok(api.post("/api/respaldos"))
    assert r["copia_externa"] and (externa / r["archivo"]).exists() and (config.dir_respaldos() / r["archivo"]).exists()
    estado = api.ok(api.get("/api/respaldos"))["estado"]
    assert estado["externa_configurada"] and estado["alerta"] is None

    # después del respaldo se crea un producto y se "daña" el sistema
    api.ok(api.post("/api/productos", {"nombre": "Producto posterior", "precio_venta": 1000}))
    assert api.ok(api.get("/api/productos?q=posterior"))["total"] == 1

    assert api.post("/api/respaldos/restaurar", {"archivo": r["archivo"], "password": "mala"}).status_code == 403
    assert api.post("/api/respaldos/restaurar", {"archivo": "../../etc/passwd", "password": "secreto1"}).status_code == 404
    out = api.ok(api.post("/api/respaldos/restaurar", {"archivo": r["archivo"], "password": "secreto1"}))
    assert out["respaldo_previo"].endswith("previo_restauracion.db.gz")
    api.login("admin", "secreto1")
    assert api.ok(api.get("/api/productos?q=posterior"))["total"] == 0          # volvió al estado del respaldo
    assert api.ok(api.get("/api/productos?q=Leche"))["total"] == 1
    # lo anterior a la restauración quedó guardado y se puede volver a restaurar
    api.ok(api.post("/api/respaldos/restaurar", {"archivo": out["respaldo_previo"], "password": "secreto1"}))
    api.login("admin", "secreto1")
    assert api.ok(api.get("/api/productos?q=posterior"))["total"] == 1


def test_respaldo_corrupto_se_rechaza(tienda):
    api = tienda.api
    malo = config.dir_respaldos() / "pos-20260101-000000-manual.db.gz"
    malo.write_bytes(b"esto no es un respaldo")
    assert api.post("/api/respaldos/restaurar", {"archivo": malo.name, "password": "secreto1"}).status_code in (400, 422, 500)
    assert api.ok(api.get("/api/productos?q=Leche"))["total"] == 1  # la base actual sigue intacta


def test_alerta_si_no_hay_copia_externa(tienda):
    api = tienda.api
    assert "Todavía no" in api.ok(api.get("/api/respaldos"))["estado"]["alerta"]
    api.ok(api.post("/api/respaldos"))
    assert "carpeta externa" in api.ok(api.get("/api/respaldos"))["estado"]["alerta"]


# ───────────────────────────── Seguridad ─────────────────────────────
def test_bloqueo_tras_intentos_fallidos_de_login(tienda):
    api = tienda.api
    api.token = None
    for _ in range(5):
        assert api.login("carlos", "mala").status_code == 401
    assert api.login("carlos", "cajero1").status_code == 429         # bloqueado aunque ahora acierte
    core.limitador.reiniciar()
    assert api.login("carlos", "cajero1").status_code == 200


def test_bloqueo_tras_pines_de_administrador_incorrectos(tienda):
    t, api = tienda, tienda.api
    abrir_turno_cajero(t)
    for _ in range(5):
        assert api.post("/api/auth/autorizar", {"pin": "0000"}).status_code == 403
    r = api.post("/api/auth/autorizar", {"pin": "1234"})
    assert r.status_code == 429


def test_pin_y_password_se_validan(tienda):
    api = tienda.api
    assert api.post("/api/usuarios", {"nombre": "X", "usuario": "x", "password": "12345", "rol": "cajero"}).status_code == 400
    assert api.post("/api/usuarios", {"nombre": "X", "usuario": "x", "password": "123456", "pin": "12", "rol": "cajero"}).status_code == 400
    assert api.post("/api/usuarios", {"nombre": "X", "usuario": "x", "password": "123456", "rol": "admin"}).status_code == 400  # admin sin PIN
    # no se puede dejar al sistema sin administradores
    uid = api.ok(api.get("/api/auth/yo"))["id"]
    assert api.put(f"/api/usuarios/{uid}", {"activo": False}).status_code == 409
    assert api.put(f"/api/usuarios/{uid}", {"rol": "cajero"}).status_code == 409


def test_setup_solo_una_vez_y_host_no_local(tienda):
    api = tienda.api
    r = api.post("/api/setup", {"negocio": {"nombre": "Otro"}, "admin": {"nombre": "Hacker", "usuario": "h", "password": "123456", "pin": "1234"}})
    assert r.status_code == 409
    assert api.c.get("/api/salud", headers={"host": "evil.example.com"}).status_code == 403


# ───────────────────────────── Atomicidad y concurrencia ─────────────────────────────
def test_venta_atomica_si_falla_a_la_mitad_no_queda_nada(tienda, monkeypatch):
    t, api = tienda, tienda.api
    ef = t.medios["Efectivo"]
    abrir_turno_cajero(t)
    original, llamadas = inv.registrar_movimiento, {"n": 0}

    def falla_en_la_segunda(*a, **k):
        llamadas["n"] += 1
        if llamadas["n"] == 2:
            raise ErrorNegocio("fallo simulado a mitad de la venta", 500)
        return original(*a, **k)

    monkeypatch.setattr(inv, "registrar_movimiento", falla_en_la_segunda)
    r = api.post("/api/ventas", {"items": [{"producto_id": t.leche["id"], "cantidad": 2}, {"producto_id": t.aceite["id"], "cantidad": 1}],
                                 "pagos": [{"medio_pago_id": ef, "monto": 19900}]})
    assert r.status_code == 500
    monkeypatch.setattr(inv, "registrar_movimiento", original)
    # ni venta, ni stock descontado, ni consecutivo consumido
    assert api.ok(api.get(f"/api/productos/{t.leche['id']}"))["stock_actual"] == 50
    assert api.ok(api.get("/api/ventas")) == []
    v = api.ok(api.post("/api/ventas", {"items": [{"producto_id": t.leche["id"], "cantidad": 1}], "pagos": [{"medio_pago_id": ef, "monto": 4200}]}))
    assert v["numero"] == "POS-000001"


def test_ventas_concurrentes_no_pierden_stock_ni_repiten_consecutivo(tienda):
    t, api = tienda, tienda.api
    ef = t.medios["Efectivo"]
    abrir_turno_cajero(t)
    errores, numeros = [], []

    def hilo():
        s = None
        try:
            for _ in range(5):
                s = db_mod.nueva_sesion(escritura=True)
                cajero = s.get(core.m.Usuario, 2)
                v = ventas_svc.crear_venta(s, cajero, {"items": [{"producto_id": t.leche["id"], "cantidad": 1}],
                                                       "pagos": [{"medio_pago_id": ef, "monto": 4200}]})
                numeros.append(v.consecutivo)
                s.commit()
                s.close()
        except Exception as e:  # noqa: BLE001
            errores.append(repr(e))
            if s:
                s.rollback()
                s.close()

    hilos = [threading.Thread(target=hilo) for _ in range(8)]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    assert errores == []
    assert sorted(numeros) == list(range(1, 41))                      # 40 ventas, consecutivos sin huecos ni repetidos
    assert api.ok(api.get(f"/api/productos/{t.leche['id']}"))["stock_actual"] == 10


SCRIPT_CORTE = textwrap.dedent("""
    import sys
    sys.path.insert(0, {backend!r})
    from app import db, core
    from app import models as m
    from app.services import ventas
    db.configurar()
    s = db.nueva_sesion(escritura=True)
    cajero = s.get(m.Usuario, 2)
    v = ventas.crear_venta(s, cajero, {{"items": [{{"producto_id": {pid}, "cantidad": 3}}],
                                       "pagos": [{{"medio_pago_id": {ef}, "monto": 12600}}]}})
    if {confirmar!r}:
        s.commit()
    print("LISTO", flush=True)
    import time; time.sleep(60)
""")


def _corte_de_energia(tienda, confirmar: bool):
    t = tienda
    abrir_turno_cajero(t)
    env = {**os.environ, "POS_DATA_DIR": str(config.directorio_datos()), "POS_SIN_JOBS": "1"}
    codigo = SCRIPT_CORTE.format(backend=str(BACKEND), pid=t.leche["id"], ef=t.medios["Efectivo"], confirmar=confirmar)
    p = subprocess.Popen([sys.executable, "-c", codigo], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, text=True)
    try:
        assert p.stdout.readline().strip() == "LISTO", p.stderr.read()
        os.kill(p.pid, signal.SIGKILL)       # corte de luz: el proceso muere sin cerrar nada
    finally:
        p.kill()
        p.wait()
    con = sqlite3.connect(config.ruta_db())
    try:
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        ventas = con.execute("SELECT COUNT(*) FROM ventas").fetchone()[0]
        stock = con.execute("SELECT stock_actual FROM productos WHERE id = ?", (t.leche["id"],)).fetchone()[0]
        consecutivo = con.execute("SELECT valor FROM configuracion WHERE clave = 'consecutivo_venta'").fetchone()
        items = con.execute("SELECT COUNT(*) FROM venta_items").fetchone()[0]
        pagos = con.execute("SELECT COUNT(*) FROM venta_pagos").fetchone()[0]
    finally:
        con.close()
    return ventas, items, pagos, stock, consecutivo


def test_corte_de_energia_antes_de_confirmar_no_deja_ventas_a_medias(tienda):
    ventas, items, pagos, stock, consecutivo = _corte_de_energia(tienda, confirmar=False)
    assert (ventas, items, pagos, stock) == (0, 0, 0, 50)
    assert consecutivo is None or consecutivo[0] == "1"


def test_corte_de_energia_despues_de_confirmar_conserva_la_venta_completa(tienda):
    ventas, items, pagos, stock, consecutivo = _corte_de_energia(tienda, confirmar=True)
    assert (ventas, items, pagos, stock) == (1, 1, 1, 47)
    assert consecutivo[0] == "2"


# ───────────────────────────── Planificador de tareas ─────────────────────────────
def test_planificador_hace_el_respaldo_diario_y_las_fotos_una_sola_vez(tienda):
    from sqlalchemy import func, select

    from app import jobs
    from app import models as m
    api = tienda.api

    def contar(tabla, **cond):
        s = db_mod.nueva_sesion()
        try:
            q = select(func.count()).select_from(tabla)
            for k, v in cond.items():
                q = q.where(getattr(tabla, k) == v)
            return s.scalar(q)
        finally:
            s.close()

    jobs.tick()                      # nunca se había respaldado: lo hace de inmediato (el equipo pudo estar apagado)
    assert contar(m.Respaldo, tipo="diario") == 1
    assert len(list(config.dir_respaldos().glob("pos-*-diario.db.gz"))) == 1
    assert contar(m.InventarioDiario) > 0                                   # foto del inventario de hoy
    jobs.tick()                      # ya está hecho hoy: no se repite
    assert contar(m.Respaldo, tipo="diario") == 1
    assert api.ok(api.get("/api/respaldos"))["estado"]["ultimo"] is not None


def test_el_respaldo_no_bloquea_las_ventas_mientras_copia(tienda, monkeypatch):
    import time as reloj_real

    from app.services import respaldos as resp
    t, api = tienda, tienda.api
    ef = t.medios["Efectivo"]
    abrir_turno_cajero(t)
    original = resp._copiar_sqlite
    monkeypatch.setattr(resp, "_copiar_sqlite", lambda o, d: (reloj_real.sleep(1.5), original(o, d)))   # copia lenta (base grande)

    hilo = threading.Thread(target=resp.crear_respaldo_seguro, args=("manual", None))
    hilo.start()
    reloj_real.sleep(0.3)            # el respaldo ya está copiando
    inicio = reloj_real.perf_counter()
    v = api.ok(api.post("/api/ventas", {"items": [{"producto_id": t.leche["id"], "cantidad": 1}], "pagos": [{"medio_pago_id": ef, "monto": 4200}]}))
    demora = reloj_real.perf_counter() - inicio
    hilo.join()
    assert v["numero"] == "POS-000001"
    assert demora < 1.0, f"la venta esperó {demora:.1f} s al respaldo"
