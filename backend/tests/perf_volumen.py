"""Prueba de volumen (no se ejecuta con pytest): ~30.000 productos y un año de ventas (~1 millón de líneas).

    python tests/perf_volumen.py [--productos 30000] [--dias 365] [--ventas-dia 300] [--lineas 9]

Mide lo que importa en la tienda: escanear un código (< 100 ms), vender, y los informes (< 2 s).
"""
import argparse
import os
import random
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--productos", type=int, default=30000)
ap.add_argument("--dias", type=int, default=365)
ap.add_argument("--ventas-dia", type=int, default=300)
ap.add_argument("--lineas", type=int, default=9)
a = ap.parse_args()

datos = Path(tempfile.mkdtemp(prefix="pos-perf-"))
os.environ.update({"POS_DATA_DIR": str(datos), "POS_SIN_JOBS": "1", "POS_EXPORT_DIR": str(datos / "exp")})
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app import db as db_mod  # noqa: E402
from app.main import app  # noqa: E402

rnd = random.Random(1)
t0 = time.time()
db_mod.configurar()
with TestClient(app, base_url="http://localhost") as c:
    tk = c.post("/api/setup", json={"negocio": {"nombre": "Perf"}, "admin": {"nombre": "A", "usuario": "admin", "password": "secreto1", "pin": "1234"}}).json()["token"]
    H = {"Authorization": f"Bearer {tk}"}
    c.post("/api/usuarios", json={"nombre": "Caja", "usuario": "caja", "password": "secreto1", "pin": "4321", "rol": "cajero"}, headers=H)

    # ── carga masiva directa (SQL) ─────────────────────────────────────────
    ruta = datos / "data" / "pos.db"
    con = sqlite3.connect(ruta)
    con.execute("PRAGMA synchronous=OFF")
    fin = datetime.now().replace(hour=21, minute=0, second=0, microsecond=0)
    ini = fin - timedelta(days=a.dias)
    cats = list(range(2, 12))
    con.executemany("INSERT INTO categorias (nombre) VALUES (?)", [(f"Categoría {i}",) for i in range(10)])
    con.executemany("INSERT INTO proveedores (nombre, activo) VALUES (?, 1)", [(f"Proveedor {i}",) for i in range(40)])
    ahora = ini.strftime("%Y-%m-%d %H:%M:%S.000000")
    prod = []
    for i in range(1, a.productos + 1):
        costo = rnd.randint(500, 40000)
        prod.append((f"Producto de prueba número {i}", rnd.choice(cats), rnd.randint(1, 40), 1, costo, int(costo * rnd.uniform(1.15, 1.5)), rnd.randint(20, 300), 10, 600, 1, ahora, ahora))
    con.executemany("INSERT INTO productos (nombre, categoria_id, proveedor_id, impuesto_id, costo_promedio, precio_venta, stock_actual, stock_minimo, stock_maximo, activo, creado_en, actualizado_en) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", prod)
    con.executemany("INSERT INTO codigos_barra (codigo, producto_id, unidades_por_codigo) VALUES (?,?,1)", [(f"7{i:012d}", i) for i in range(1, a.productos + 1)])
    pop = [1 / ((i + 1) ** 0.9) for i in range(min(a.productos, 6000))]
    pids = list(range(1, min(a.productos, 6000) + 1))
    precios = {r[0]: (r[1], r[2]) for r in con.execute("SELECT id, precio_venta, costo_promedio FROM productos")}
    n_venta = 0; n_lineas = 0
    for d in range(a.dias):
        dia = ini + timedelta(days=d)
        con.execute("INSERT INTO turnos (caja_id, usuario_id, abierto_en, base_efectivo, cerrado_en, efectivo_esperado, efectivo_contado, diferencia_efectivo, banco_esperado, banco_reportado, diferencia_banco, estado) "
                    "VALUES (1, 2, ?, 100000, ?, 0, 0, 0, 0, 0, 0, 'cerrado')", (dia.replace(hour=7).strftime("%Y-%m-%d %H:%M:%S.000000"), dia.replace(hour=21).strftime("%Y-%m-%d %H:%M:%S.000000")))
        turno = d + 1
        ventas, items, pagos, movs = [], [], [], []
        for k in range(a.ventas_dia):
            n_venta += 1
            f = dia.replace(hour=rnd.choice([8, 9, 10, 11, 12, 12, 13, 17, 18, 18, 19]), minute=rnd.randint(0, 59), second=rnd.randint(0, 59)).strftime("%Y-%m-%d %H:%M:%S.000000")
            total = 0
            for pid in rnd.choices(pids, pop, k=max(1, int(rnd.expovariate(1 / a.lineas)))):
                cant = rnd.choice([1, 1, 1, 2, 3]); precio, costo = precios[pid]
                total += precio * cant; n_lineas += 1
                items.append((n_venta, pid, "Producto", cant, precio, 0, 0.0, 0, precio * cant, costo))
                movs.append((pid, f, "VENTA", -cant, costo, 0, "venta", n_venta, 2))
            ventas.append((n_venta, "POS", n_venta, turno, 2, f, total, 0, 0, total, "completada", "no_aplica"))
            pagos.append((n_venta, 1 if rnd.random() < .6 else 2, total, total, 0))
        con.executemany("INSERT INTO ventas (id, prefijo, consecutivo, turno_id, usuario_id, fecha, subtotal, descuento_total, impuesto_total, total, estado, estado_dian) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ventas)
        con.executemany("INSERT INTO venta_items (venta_id, producto_id, descripcion, cantidad, precio_unitario, descuento, tarifa_pct, valor_impuesto, total, costo_unitario) VALUES (?,?,?,?,?,?,?,?,?,?)", items)
        con.executemany("INSERT INTO venta_pagos (venta_id, medio_pago_id, monto, recibido, devuelta) VALUES (?,?,?,?,0)", [(p[0], p[1], p[2], p[3]) for p in pagos])
        con.executemany("INSERT INTO movimientos_inventario (producto_id, fecha, tipo, cantidad, costo_unitario, stock_resultante, referencia_tipo, referencia_id, usuario_id) VALUES (?,?,?,?,?,?,?,?,?)",
                        [(m[0], m[1], m[2], m[3], m[4], 100, m[6], m[7], m[8]) for m in movs])
    con.execute("UPDATE configuracion SET valor = ? WHERE clave = 'consecutivo_venta'", (str(n_venta + 1),)) if con.execute("SELECT 1 FROM configuracion WHERE clave='consecutivo_venta'").fetchone() else con.execute("INSERT INTO configuracion VALUES ('consecutivo_venta', ?)", (str(n_venta + 1),))
    con.commit(); con.execute("ANALYZE"); con.close()
    print(f"Carga: {a.productos:,} productos, {n_venta:,} ventas, {n_lineas:,} líneas en {time.time() - t0:.0f} s · base {ruta.stat().st_size / 1e6:.0f} MB")

    # ── mediciones ─────────────────────────────────────────────────────────
    resultados = []

    def medir(nombre, fn, objetivo, repeticiones=1):
        ts = []
        for _ in range(repeticiones):
            t = time.perf_counter(); r = fn(); ts.append((time.perf_counter() - t) * 1000)
            assert r is None or getattr(r, "status_code", 200) < 400, (nombre, r.status_code, r.text[:200])
        ts.sort(); p95 = ts[min(len(ts) - 1, int(len(ts) * .95))]
        resultados.append((nombre, ts[len(ts) // 2], p95, objetivo))

    c.post("/api/auth/login", json={"usuario": "caja", "password": "secreto1"})
    tkc = c.post("/api/auth/login", json={"usuario": "caja", "password": "secreto1"}).json()["token"]; HC = {"Authorization": f"Bearer {tkc}"}
    c.post("/api/turnos/abrir", json={"base": 100000}, headers=HC)
    cods = [f"7{rnd.randint(1, a.productos):012d}" for _ in range(300)]
    medir("Escanear un código de barras", lambda: c.get(f"/api/productos/codigo/{cods.pop()}", headers=HC), 100, 250)
    medir("Buscar por nombre (F2)", lambda: c.get("/api/productos?q=número 2345&limite=30", headers=HC), 300, 30)
    pid = rnd.randint(1, 3000)
    medir("Cobrar una venta de 10 productos (efectivo)", lambda: c.post("/api/ventas", headers=HC, json={"items": [{"producto_id": rnd.randint(1, 3000), "cantidad": 1} for _ in range(10)], "pagos": [{"medio_pago_id": 1, "monto": 1, "recibido": 10**9}]}), 300, 1) if False else None
    items = [{"producto_id": i, "cantidad": 1} for i in rnd.sample(range(1, 3000), 10)]
    total = sum(precios[i["producto_id"]][0] for i in items)
    medir("Cobrar una venta de 10 productos", lambda: c.post("/api/ventas", headers=HC, json={"items": items, "pagos": [{"medio_pago_id": 1, "monto": total, "recibido": total + 5000}]}), 300, 1)
    hoy = datetime.now().date(); h = hoy.isoformat(); d30 = (hoy - timedelta(days=29)).isoformat(); d365 = (hoy - timedelta(days=a.dias)).isoformat()
    medir("Panel de control (30 días)", lambda: c.get(f"/api/dashboard?desde={d30}&hasta={h}", headers=H), 2000)
    medir("Panel de control (1 año)", lambda: c.get(f"/api/dashboard?desde={d365}&hasta={h}", headers=H), 3000)
    for slug, q in [("ventas_dia", ""), ("ventas_producto", ""), ("rentabilidad", "&agrupar=categoria"), ("abc", ""), ("cobertura", ""), ("sin_movimiento", "&dias=60"),
                    ("sugerido", ""), ("valorizacion", ""), ("iva", ""), ("ventas_hora", "")]:
        medir(f"Informe «{slug}» (1 año)", lambda s=slug, q=q: c.get(f"/api/informes/{s}?desde={d365}&hasta={h}{q}", headers=H), 2000)
    medir("Rotación de inventario, 1.ª vez (30 días, crea fotos)", lambda: c.get(f"/api/informes/rotacion?desde={d30}&hasta={h}&agrupar=categoria", headers=H), 20000)
    medir("Rotación de inventario, con fotos (30 días)", lambda: c.get(f"/api/informes/rotacion?desde={d30}&hasta={h}&agrupar=categoria", headers=H), 2000)
    medir("Exportar ventas por producto del año a Excel", lambda: c.get(f"/api/informes/ventas_producto?desde={d365}&hasta={h}&formato=xlsx", headers=H), 5000)
    # conteo total de todo el catálogo
    cid = c.post("/api/conteos", json={"nombre": "Perf", "tipo": "total"}, headers=H).json()["id"]
    medir("Iniciar conteo de todo el inventario", lambda: c.post(f"/api/conteos/{cid}/iniciar", headers=H), 5000)
    for i in rnd.sample(range(1, a.productos), 500):
        c.post(f"/api/conteos/{cid}/capturas", json={"codigo": f"7{i:012d}", "cantidad": 3}, headers=H)
    medir("Cerrar captura del conteo (calcula todo el catálogo)", lambda: c.post(f"/api/conteos/{cid}/cerrar-captura", headers=H), 5000)
    medir("Revisión de inconsistencias del conteo", lambda: c.get(f"/api/conteos/{cid}/revision", headers=H), 3000)
    medir("Respaldo manual de la base", lambda: c.post("/api/respaldos", headers=H), 20000)

    print(f"\n{'Operación':<58}{'mediana':>10}{'p95':>10}{'objetivo':>10}")
    fallos = 0
    for nombre, med, p95, obj in resultados:
        ok = p95 <= obj
        fallos += not ok
        print(f"{nombre:<58}{med:>8.0f}ms{p95:>8.0f}ms{obj:>8}ms  {'OK' if ok else 'LENTO'}")
    print(f"\n{len(resultados) - fallos}/{len(resultados)} dentro del objetivo")
