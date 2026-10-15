"""Dashboard e informes administrativos.

Todos los informes devuelven {titulo, columnas:[{key,titulo,tipo}], filas:[...], totales?, nota?} para que la
misma estructura sirva a la pantalla, a Excel y a PDF. Las ventas se calculan *netas de devoluciones* y con el
costo congelado en cada línea vendida.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from .. import models as m
from ..core import ErrorNegocio, hoy
from . import conteos as conteos_svc
from . import inventario as inv

# Líneas de venta (+) y de devolución (−): base de casi todos los informes
LINEAS = """
WITH lineas AS (
  SELECT v.fecha AS fecha, vi.producto_id AS producto_id, vi.cantidad AS cantidad, vi.total AS total,
         vi.valor_impuesto AS impuesto, vi.cantidad * vi.costo_unitario AS costo, vi.tarifa_pct AS tarifa,
         v.usuario_id AS usuario_id, v.id AS venta_id
    FROM venta_items vi JOIN ventas v ON v.id = vi.venta_id
   WHERE v.estado = 'completada' AND v.fecha >= :d AND v.fecha < :h
  UNION ALL
  SELECT dv.fecha, di.producto_id, -di.cantidad, -di.total, -di.valor_impuesto,
         -di.cantidad * di.costo_unitario, vi.tarifa_pct, dv.usuario_id, dv.venta_id
    FROM devolucion_items di JOIN devoluciones dv ON dv.id = di.devolucion_id
    JOIN venta_items vi ON vi.id = di.venta_item_id
   WHERE dv.fecha >= :d AND dv.fecha < :h
)
"""


def Q(db: Session, sql: str, **p) -> list[dict]:
    return [dict(r) for r in db.execute(text(sql), p).mappings()]


def rango(desde: date | None, hasta: date | None, dias_defecto: int | None = None) -> tuple[date, date]:
    h = hasta or hoy()
    d = desde or (h - timedelta(days=dias_defecto - 1) if dias_defecto else h.replace(day=1))
    if d > h:
        raise ErrorNegocio("La fecha inicial es posterior a la final.")
    if (h - d).days > 1100:
        raise ErrorNegocio("El rango máximo es de 3 años.")
    return d, h


def _par(d: date, h: date) -> dict:
    return {"d": datetime.combine(d, time.min).isoformat(sep=" "),
            "h": datetime.combine(h + timedelta(days=1), time.min).isoformat(sep=" ")}


def _pct(a: float, b: float) -> float | None:
    return round(a * 100 / b, 1) if b else None


def _col(key, titulo, tipo="texto"):
    return {"key": key, "titulo": titulo, "tipo": tipo}


# ───────────────────────────── Dashboard ─────────────────────────────
def _kpis(db: Session, d: date, h: date) -> dict:
    p = _par(d, h)
    r = Q(db, LINEAS + "SELECT COALESCE(SUM(total),0) ventas, COALESCE(SUM(impuesto),0) imp, "
                       "COALESCE(SUM(costo),0) costo FROM lineas", **p)[0]
    t = Q(db, "SELECT COUNT(*) n, COALESCE(SUM(total),0) bruto FROM ventas WHERE estado='completada' "
              "AND fecha >= :d AND fecha < :h", **p)[0]
    u = Q(db, "SELECT COALESCE(SUM(vi.cantidad),0) u FROM venta_items vi JOIN ventas v ON v.id=vi.venta_id "
              "WHERE v.estado='completada' AND v.fecha >= :d AND v.fecha < :h", **p)[0]["u"]
    sin_imp = r["ventas"] - r["imp"]
    margen = sin_imp - r["costo"]
    return {"ventas": int(r["ventas"]), "transacciones": t["n"],
            "ticket_promedio": round(t["bruto"] / t["n"]) if t["n"] else 0,
            "unidades_por_ticket": round(u / t["n"], 1) if t["n"] else 0,
            "margen": round(margen), "margen_pct": _pct(margen, sin_imp), "costo": round(r["costo"])}


def _variacion(actual: float, previo: float) -> float | None:
    return round((actual - previo) * 100 / previo, 1) if previo else None


def dashboard(db: Session, desde: date | None, hasta: date | None) -> dict:
    d, h = rango(desde, hasta, dias_defecto=30)
    dias = (h - d).days + 1
    dp, hp = d - timedelta(days=dias), d - timedelta(days=1)
    actual, previo = _kpis(db, d, h), _kpis(db, dp, hp)
    p = _par(d, h)
    for k in ("ventas", "transacciones", "ticket_promedio", "margen"):
        actual[f"{k}_var"] = _variacion(actual[k], previo[k])
    actual["margen_pct_prev"] = previo["margen_pct"]

    por_dia = {r["dia"]: r for r in Q(db, "SELECT date(fecha) dia, SUM(total) ventas, COUNT(*) tiquetes FROM ventas "
                                          "WHERE estado='completada' AND fecha >= :d AND fecha < :h GROUP BY 1", **p)}
    serie = []
    for i in range(dias):
        dia = (d + timedelta(days=i)).isoformat()
        serie.append({"fecha": dia, "ventas": int(por_dia.get(dia, {}).get("ventas", 0)),
                      "tiquetes": por_dia.get(dia, {}).get("tiquetes", 0)})

    calor = Q(db, "SELECT CAST(strftime('%w', fecha) AS INTEGER) dia, CAST(strftime('%H', fecha) AS INTEGER) hora, "
                  "COUNT(*) tiquetes, SUM(total) ventas FROM ventas WHERE estado='completada' AND fecha >= :d AND fecha < :h "
                  "GROUP BY 1, 2", **p)
    medios = Q(db, "SELECT mp.nombre medio, mp.tipo tipo, SUM(vp.monto) monto FROM venta_pagos vp "
                   "JOIN ventas v ON v.id = vp.venta_id JOIN medios_pago mp ON mp.id = vp.medio_pago_id "
                   "WHERE v.estado='completada' AND v.fecha >= :d AND v.fecha < :h GROUP BY mp.id ORDER BY monto DESC", **p)
    top_ventas = Q(db, LINEAS + "SELECT pr.nombre, SUM(l.total) ventas, SUM(l.cantidad) unidades FROM lineas l "
                                "JOIN productos pr ON pr.id = l.producto_id GROUP BY pr.id ORDER BY ventas DESC LIMIT 10", **p)
    top_margen = Q(db, LINEAS + "SELECT pr.nombre, ROUND(SUM(l.total - l.impuesto - l.costo)) margen FROM lineas l "
                                "JOIN productos pr ON pr.id = l.producto_id GROUP BY pr.id ORDER BY margen DESC LIMIT 10", **p)
    top_cat = Q(db, LINEAS + "SELECT COALESCE(c.nombre,'Sin categoría') nombre, SUM(l.total) ventas, "
                              "ROUND(SUM(l.total - l.impuesto - l.costo)) margen FROM lineas l "
                              "JOIN productos pr ON pr.id = l.producto_id LEFT JOIN categorias c ON c.id = pr.categoria_id "
                              "GROUP BY c.id ORDER BY ventas DESC LIMIT 8", **p)
    stock = Q(db, "SELECT COALESCE(SUM(CASE WHEN stock_actual > 0 THEN stock_actual * costo_promedio END),0) valor, "
                  "SUM(CASE WHEN stock_actual = 0 AND stock_minimo > 0 THEN 1 ELSE 0 END) agotados, "
                  "SUM(CASE WHEN stock_actual > 0 AND stock_actual <= stock_minimo THEN 1 ELSE 0 END) bajo, "
                  "SUM(CASE WHEN stock_actual < 0 THEN 1 ELSE 0 END) negativos, COUNT(*) productos "
                  "FROM productos WHERE activo = 1")[0]
    ultimo_conteo = Q(db, "SELECT id, nombre, cerrado_en, exactitud_pct FROM conteos WHERE estado='aplicado' "
                          "ORDER BY cerrado_en DESC LIMIT 1")
    en_curso = Q(db, "SELECT id, nombre, estado FROM conteos WHERE estado IN ('en_conteo','en_revision') LIMIT 1")
    cierres = Q(db, "SELECT t.id, u.nombre cajero, t.cerrado_en, t.diferencia_efectivo, t.diferencia_banco "
                    "FROM turnos t JOIN usuarios u ON u.id = t.usuario_id WHERE t.estado='cerrado' "
                    "ORDER BY t.cerrado_en DESC LIMIT 8")
    return {
        "periodo": {"desde": d.isoformat(), "hasta": h.isoformat(), "dias": dias,
                    "previo_desde": dp.isoformat(), "previo_hasta": hp.isoformat()},
        "kpis": actual, "serie": serie, "calor": calor, "medios": [{**x, "monto": int(x["monto"])} for x in medios],
        "top_ventas": top_ventas, "top_margen": top_margen, "top_categorias": top_cat,
        "inventario": {"valor": round(stock["valor"]), "agotados": stock["agotados"] or 0, "bajo_minimo": stock["bajo"] or 0,
                       "negativos": stock["negativos"] or 0, "productos": stock["productos"] or 0},
        "conteos": {"recordatorios": conteos_svc.recordatorios(db), "ultimo": ultimo_conteo[0] if ultimo_conteo else None,
                    "en_curso": en_curso[0] if en_curso else None},
        "cierres": cierres,
    }


# ───────────────────────────── Informes ─────────────────────────────
def _tabla(titulo, columnas, filas, totales=None, nota=None):
    return {"titulo": titulo, "columnas": columnas, "filas": filas, "totales": totales or {}, "nota": nota}


def _suma(filas, *claves):
    return {k: sum((f.get(k) or 0) for f in filas) for k in claves}


def r_ventas_dia(db, d, h, **_):
    p = _par(d, h)
    lin = {r["dia"]: r for r in Q(db, LINEAS + "SELECT date(fecha) dia, SUM(cantidad) unidades, SUM(total) neto, "
                                              "SUM(impuesto) imp, SUM(costo) costo FROM lineas GROUP BY 1", **p)}
    tiq = {r["dia"]: r for r in Q(db, "SELECT date(fecha) dia, COUNT(*) n, SUM(descuento_total) dsc FROM ventas "
                                      "WHERE estado='completada' AND fecha >= :d AND fecha < :h GROUP BY 1", **p)}
    filas = []
    for dia in sorted(set(lin) | set(tiq)):
        l, t = lin.get(dia, {}), tiq.get(dia, {})
        sin_imp = (l.get("neto") or 0) - (l.get("imp") or 0)
        margen = sin_imp - (l.get("costo") or 0)
        filas.append({"dia": dia, "tiquetes": t.get("n", 0), "unidades": l.get("unidades") or 0,
                      "descuentos": t.get("dsc") or 0, "impuestos": l.get("imp") or 0, "ventas": l.get("neto") or 0,
                      "costo": round(l.get("costo") or 0), "margen": round(margen), "margen_pct": _pct(margen, sin_imp)})
    tot = _suma(filas, "tiquetes", "unidades", "descuentos", "impuestos", "ventas", "costo", "margen")
    tot["margen_pct"] = _pct(tot["margen"], tot["ventas"] - tot["impuestos"])
    return _tabla("Ventas por día", [_col("dia", "Día", "fecha"), _col("tiquetes", "Tiquetes", "entero"),
                                     _col("unidades", "Unidades", "entero"), _col("descuentos", "Descuentos", "dinero"),
                                     _col("impuestos", "Impuestos", "dinero"), _col("ventas", "Ventas netas", "dinero"),
                                     _col("costo", "Costo", "dinero"), _col("margen", "Margen $", "dinero"),
                                     _col("margen_pct", "Margen %", "porcentaje")], filas, tot,
                  "Ventas netas de devoluciones, con impuestos incluidos. El margen se calcula sobre ventas sin impuestos.")


def _agrupado(db, d, h, por: str):
    p = _par(d, h)
    if por == "categoria":
        sel, join, grupo, nom = "COALESCE(c.nombre,'Sin categoría')", "LEFT JOIN categorias c ON c.id = pr.categoria_id", "c.id", "categoria"
    else:
        sel, join, grupo, nom = "pr.nombre", "LEFT JOIN categorias c ON c.id = pr.categoria_id", "pr.id", "producto"
    filas = Q(db, LINEAS + f"SELECT {sel} nombre, COALESCE(c.nombre,'Sin categoría') categoria, SUM(l.cantidad) unidades, "
                           f"SUM(l.total) ventas, SUM(l.impuesto) imp, SUM(l.costo) costo FROM lineas l "
                           f"JOIN productos pr ON pr.id = l.producto_id {join} GROUP BY {grupo} ORDER BY ventas DESC", **p)
    total = sum(f["ventas"] for f in filas) or 0
    for f in filas:
        sin = f["ventas"] - f["imp"]
        f["margen"] = round(sin - f["costo"])
        f["margen_pct"] = _pct(sin - f["costo"], sin)
        f["costo"] = round(f["costo"])
        f["participacion"] = _pct(f["ventas"], total)
    return filas, nom


COLS_AGRUPADO = [_col("unidades", "Unidades", "entero"), _col("ventas", "Ventas", "dinero"), _col("costo", "Costo", "dinero"),
                 _col("margen", "Margen $", "dinero"), _col("margen_pct", "Margen %", "porcentaje"),
                 _col("participacion", "% de ventas", "porcentaje")]


def r_ventas_producto(db, d, h, **_):
    filas, _n = _agrupado(db, d, h, "producto")
    return _tabla("Ventas por producto", [_col("nombre", "Producto"), _col("categoria", "Categoría")] + COLS_AGRUPADO, filas,
                  _suma(filas, "unidades", "ventas", "costo", "margen"))


def r_ventas_categoria(db, d, h, **_):
    filas, _n = _agrupado(db, d, h, "categoria")
    return _tabla("Ventas por categoría", [_col("nombre", "Categoría")] + COLS_AGRUPADO, filas,
                  _suma(filas, "unidades", "ventas", "costo", "margen"))


def r_rentabilidad(db, d, h, agrupar="producto", **_):
    filas, _n = _agrupado(db, d, h, "categoria" if agrupar == "categoria" else "producto")
    filas.sort(key=lambda f: f["margen"], reverse=True)
    cols = [_col("nombre", "Categoría" if agrupar == "categoria" else "Producto")] + COLS_AGRUPADO
    return _tabla("Rentabilidad por " + ("categoría" if agrupar == "categoria" else "producto"), cols, filas,
                  _suma(filas, "unidades", "ventas", "costo", "margen"),
                  "Usa el costo congelado en cada venta, no el costo de hoy. Ordenado por margen en pesos.")


def r_ventas_cajero(db, d, h, **_):
    filas = Q(db, "SELECT u.nombre nombre, COUNT(*) tiquetes, SUM(v.total) ventas, SUM(v.descuento_total) descuentos, "
                  "ROUND(AVG(v.total)) ticket FROM ventas v JOIN usuarios u ON u.id = v.usuario_id "
                  "WHERE v.estado='completada' AND v.fecha >= :d AND v.fecha < :h GROUP BY u.id ORDER BY ventas DESC", **_par(d, h))
    return _tabla("Ventas por cajero", [_col("nombre", "Cajero"), _col("tiquetes", "Tiquetes", "entero"),
                                        _col("ventas", "Ventas", "dinero"), _col("descuentos", "Descuentos", "dinero"),
                                        _col("ticket", "Ticket promedio", "dinero")], filas, _suma(filas, "tiquetes", "ventas", "descuentos"))


def r_ventas_medio_pago(db, d, h, **_):
    filas = Q(db, "SELECT mp.nombre nombre, mp.tipo tipo, COUNT(*) pagos, SUM(vp.monto) monto FROM venta_pagos vp "
                  "JOIN ventas v ON v.id = vp.venta_id JOIN medios_pago mp ON mp.id = vp.medio_pago_id "
                  "WHERE v.estado='completada' AND v.fecha >= :d AND v.fecha < :h GROUP BY mp.id ORDER BY monto DESC", **_par(d, h))
    total = sum(f["monto"] for f in filas)
    for f in filas:
        f["participacion"] = _pct(f["monto"], total)
    return _tabla("Ventas por medio de pago", [_col("nombre", "Medio de pago"), _col("tipo", "Tipo"), _col("pagos", "Pagos", "entero"),
                                               _col("monto", "Monto", "dinero"), _col("participacion", "%", "porcentaje")],
                  filas, _suma(filas, "pagos", "monto"))


def r_ventas_hora(db, d, h, **_):
    filas = Q(db, "SELECT strftime('%H', fecha) || ':00' hora, COUNT(*) tiquetes, SUM(total) ventas, ROUND(AVG(total)) ticket "
                  "FROM ventas WHERE estado='completada' AND fecha >= :d AND fecha < :h GROUP BY 1 ORDER BY 1", **_par(d, h))
    return _tabla("Ventas por hora", [_col("hora", "Hora"), _col("tiquetes", "Tiquetes", "entero"), _col("ventas", "Ventas", "dinero"),
                                      _col("ticket", "Ticket promedio", "dinero")], filas, _suma(filas, "tiquetes", "ventas"),
                  "Útil para decidir turnos de personal.")


def r_tiquetes(db, d, h, **_):
    filas = Q(db, "SELECT v.prefijo || '-' || printf('%06d', v.consecutivo) numero, v.fecha fecha, u.nombre cajero, "
                  "v.subtotal subtotal, v.descuento_total descuento, v.impuesto_total impuesto, v.total total, v.estado estado, "
                  "(SELECT GROUP_CONCAT(mp.nombre, ' + ') FROM venta_pagos vp JOIN medios_pago mp ON mp.id = vp.medio_pago_id "
                  "  WHERE vp.venta_id = v.id) medios FROM ventas v JOIN usuarios u ON u.id = v.usuario_id "
                  "WHERE v.fecha >= :d AND v.fecha < :h ORDER BY v.id DESC LIMIT 5000", **_par(d, h))
    ok = [f for f in filas if f["estado"] == "completada"]
    return _tabla("Detalle de tiquetes", [_col("numero", "Tiquete"), _col("fecha", "Fecha", "fechahora"), _col("cajero", "Cajero"),
                                          _col("subtotal", "Subtotal", "dinero"), _col("descuento", "Descuento", "dinero"),
                                          _col("impuesto", "Impuesto", "dinero"), _col("total", "Total", "dinero"),
                                          _col("estado", "Estado"), _col("medios", "Medios de pago")], filas,
                  _suma(ok, "subtotal", "descuento", "impuesto", "total"), "Los totales excluyen tiquetes anulados. Máximo 5.000 filas.")


def r_anulaciones(db, d, h, **_):
    filas = Q(db, "SELECT v.prefijo || '-' || printf('%06d', v.consecutivo) numero, v.fecha fecha, u.nombre cajero, v.total total, "
                  "a.nombre anulada_por, v.anulada_en anulada_en, v.motivo_anulacion motivo FROM ventas v "
                  "JOIN usuarios u ON u.id = v.usuario_id LEFT JOIN usuarios a ON a.id = v.anulada_por "
                  "WHERE v.estado='anulada' AND v.anulada_en >= :d AND v.anulada_en < :h ORDER BY v.anulada_en DESC", **_par(d, h))
    return _tabla("Anulaciones", [_col("numero", "Tiquete"), _col("fecha", "Venta", "fechahora"), _col("cajero", "Cajero"),
                                  _col("total", "Total", "dinero"), _col("anulada_por", "Anulada por"),
                                  _col("anulada_en", "Anulada el", "fechahora"), _col("motivo", "Motivo")], filas, _suma(filas, "total"))


def r_devoluciones(db, d, h, **_):
    filas = Q(db, "SELECT dv.fecha fecha, v.prefijo || '-' || printf('%06d', v.consecutivo) numero, u.nombre cajero, "
                  "a.nombre autorizado, dv.total total, dv.medio_reintegro medio, dv.motivo motivo, "
                  "(SELECT SUM(cantidad) FROM devolucion_items WHERE devolucion_id = dv.id) unidades FROM devoluciones dv "
                  "JOIN ventas v ON v.id = dv.venta_id JOIN usuarios u ON u.id = dv.usuario_id "
                  "LEFT JOIN usuarios a ON a.id = dv.autorizado_por WHERE dv.fecha >= :d AND dv.fecha < :h ORDER BY dv.fecha DESC", **_par(d, h))
    return _tabla("Devoluciones", [_col("fecha", "Fecha", "fechahora"), _col("numero", "Tiquete"), _col("cajero", "Cajero"),
                                   _col("autorizado", "Autorizó"), _col("unidades", "Unidades", "entero"), _col("total", "Total", "dinero"),
                                   _col("medio", "Reintegro"), _col("motivo", "Motivo")], filas, _suma(filas, "unidades", "total"))


def r_descuentos(db, d, h, **_):
    filas = Q(db, "SELECT v.prefijo || '-' || printf('%06d', v.consecutivo) numero, v.fecha fecha, u.nombre cajero, v.subtotal subtotal, "
                  "v.descuento_total descuento, ROUND(v.descuento_total * 100.0 / v.subtotal, 1) pct FROM ventas v "
                  "JOIN usuarios u ON u.id = v.usuario_id WHERE v.estado='completada' AND v.descuento_total > 0 "
                  "AND v.fecha >= :d AND v.fecha < :h ORDER BY v.descuento_total DESC", **_par(d, h))
    return _tabla("Descuentos otorgados", [_col("numero", "Tiquete"), _col("fecha", "Fecha", "fechahora"), _col("cajero", "Cajero"),
                                           _col("subtotal", "Subtotal", "dinero"), _col("descuento", "Descuento", "dinero"),
                                           _col("pct", "%", "porcentaje")], filas, _suma(filas, "subtotal", "descuento"))


def _inventario_promedio(db, d, h):
    """Promedio diario del inventario a costo (por producto y total) a partir de las fotos diarias."""
    p = {"a": d.isoformat(), "b": h.isoformat()}
    ndias = Q(db, "SELECT COUNT(DISTINCT fecha) n FROM inventario_diario WHERE fecha BETWEEN :a AND :b", **p)[0]["n"]
    if not ndias:
        return {}, 0
    por_prod = {r["producto_id"]: r["prom"] for r in Q(
        db, "SELECT producto_id, SUM(CASE WHEN stock > 0 THEN stock * costo_promedio ELSE 0 END) / :n prom "
            "FROM inventario_diario WHERE fecha BETWEEN :a AND :b GROUP BY producto_id", n=ndias, **p)}
    return por_prod, ndias


def r_rotacion(db, d, h, agrupar="categoria", **_):
    dias = (h - d).days + 1
    inv_prom, ndias = _inventario_promedio(db, d, h)
    if not ndias:
        return _tabla("Rotación de inventario", [], [], nota="Aún no hay fotos diarias del inventario para este periodo.")
    p = _par(d, h)
    ventas = Q(db, LINEAS + "SELECT pr.id pid, pr.nombre nombre, COALESCE(c.nombre,'Sin categoría') categoria, "
                            "SUM(l.costo) costo, SUM(l.total - l.impuesto) neto FROM lineas l JOIN productos pr ON pr.id = l.producto_id "
                            "LEFT JOIN categorias c ON c.id = pr.categoria_id GROUP BY pr.id", **p)
    cat_de = {r["id"]: r["categoria"] for r in Q(
        db, "SELECT pr.id, COALESCE(c.nombre,'Sin categoría') categoria FROM productos pr LEFT JOIN categorias c ON c.id = pr.categoria_id")}
    nom = {v["pid"]: v["nombre"] for v in ventas}
    grupos: dict[str, dict] = defaultdict(lambda: {"costo": 0.0, "neto": 0.0, "inv": 0.0})
    for v in ventas:
        k = v["nombre"] if agrupar == "producto" else (v["categoria"] if agrupar == "categoria" else "Todo el inventario")
        grupos[k]["costo"] += v["costo"]
        grupos[k]["neto"] += v["neto"]
    nombres_prod = {r["id"]: r["nombre"] for r in Q(db, "SELECT id, nombre FROM productos")} if agrupar == "producto" else {}
    for pid, prom in inv_prom.items():
        k = nombres_prod.get(pid, nom.get(pid, "")) if agrupar == "producto" else (cat_de.get(pid, "Sin categoría") if agrupar == "categoria" else "Todo el inventario")
        if k:
            grupos[k]["inv"] += prom
    filas = []
    for k, g in grupos.items():
        rot = g["costo"] / g["inv"] if g["inv"] else None
        margen = g["neto"] - g["costo"]
        filas.append({"nombre": k, "costo_ventas": round(g["costo"]), "inventario_prom": round(g["inv"]),
                      "rotacion": round(rot, 2) if rot else None, "dias_inventario": round(dias / rot, 1) if rot else None,
                      "gmroi": round(margen / g["inv"], 2) if g["inv"] else None})
    filas.sort(key=lambda f: (f["rotacion"] is None, -(f["rotacion"] or 0)))
    tot_c, tot_i = sum(f["costo_ventas"] for f in filas), sum(f["inventario_prom"] for f in filas)
    rot_t = tot_c / tot_i if tot_i else None
    return _tabla("Rotación de inventario por " + {"producto": "producto", "total": "total"}.get(agrupar, "categoría"),
                  [_col("nombre", "Producto" if agrupar == "producto" else "Categoría" if agrupar == "categoria" else "Concepto"),
                   _col("costo_ventas", "Costo de ventas", "dinero"), _col("inventario_prom", "Inventario promedio", "dinero"),
                   _col("rotacion", "Rotación (veces)", "decimal"), _col("dias_inventario", "Días de inventario", "decimal"),
                   _col("gmroi", "GMROI", "decimal")], filas,
                  {"costo_ventas": tot_c, "inventario_prom": tot_i, "rotacion": round(rot_t, 2) if rot_t else None,
                   "dias_inventario": round(dias / rot_t, 1) if rot_t else None},
                  f"Periodo de {dias} días; inventario promedio calculado con {ndias} foto(s) diaria(s). "
                  "Rotación = costo de ventas / inventario promedio. GMROI = margen bruto / inventario promedio.")


def r_cobertura(db, d, h, **_):
    ref = hoy()
    p = _par(ref - timedelta(days=29), ref)
    filas = Q(db, LINEAS + "SELECT pr.nombre nombre, pr.stock_actual stock, pr.stock_minimo minimo, COALESCE(SUM(l.cantidad),0) u30, "
                           "ROUND(COALESCE(SUM(l.cantidad),0) / 30.0, 2) diaria FROM productos pr "
                           "LEFT JOIN lineas l ON l.producto_id = pr.id WHERE pr.activo = 1 GROUP BY pr.id "
                           "HAVING u30 > 0 ORDER BY pr.stock_actual / (u30 / 30.0) ASC LIMIT 1000", **p)
    for f in filas:
        f["cobertura"] = round(max(f["stock"], 0) / f["diaria"], 1) if f["diaria"] else None
    return _tabla("Cobertura de inventario", [_col("nombre", "Producto"), _col("stock", "Stock", "entero"), _col("minimo", "Mínimo", "entero"),
                                              _col("u30", "Vendido 30 días", "entero"), _col("diaria", "Venta diaria", "decimal"),
                                              _col("cobertura", "Cobertura (días)", "decimal")], filas,
                  nota="Cuántos días alcanza el stock actual al ritmo de venta de los últimos 30 días. Primero los más urgentes.")


def r_abc(db, d, h, base="ventas", **_):
    filas, _n = _agrupado(db, d, h, "producto")
    clave = "margen" if base == "margen" else "ventas"
    filas = [f for f in filas if f[clave] > 0]
    filas.sort(key=lambda f: f[clave], reverse=True)
    total, acum = sum(f[clave] for f in filas), 0
    for f in filas:
        acum += f[clave]
        f["acumulado"] = _pct(acum, total)
        f["clase"] = "A" if f["acumulado"] <= 80 else "B" if f["acumulado"] <= 95 else "C"
    resumen = ", ".join(f"{c}: {sum(1 for f in filas if f['clase'] == c)} productos" for c in "ABC")
    return _tabla("Análisis ABC (Pareto) por " + clave, [_col("nombre", "Producto"), _col("categoria", "Categoría"),
                                                          _col(clave, "Margen $" if clave == "margen" else "Ventas", "dinero"),
                                                          _col("acumulado", "% acumulado", "porcentaje"), _col("clase", "Clase")],
                  filas, {clave: total}, f"A = hasta 80 % acumulado, B = hasta 95 %, C = el resto. {resumen}.")


def r_sin_movimiento(db, d, h, dias=60, **_):
    dias = int(dias)
    corte = datetime.combine(hoy() - timedelta(days=dias), time.min).isoformat(sep=" ")
    filas = Q(db, "SELECT pr.nombre nombre, COALESCE(c.nombre,'Sin categoría') categoria, pr.stock_actual stock, "
                  "ROUND(pr.stock_actual * pr.costo_promedio) valor, "
                  "(SELECT MAX(v.fecha) FROM venta_items vi JOIN ventas v ON v.id = vi.venta_id "
                  "  WHERE vi.producto_id = pr.id AND v.estado='completada') ultima FROM productos pr "
                  "LEFT JOIN categorias c ON c.id = pr.categoria_id WHERE pr.activo = 1 AND pr.stock_actual > 0 "
                  "AND NOT EXISTS (SELECT 1 FROM venta_items vi JOIN ventas v ON v.id = vi.venta_id WHERE vi.producto_id = pr.id "
                  "  AND v.estado='completada' AND v.fecha >= :corte) ORDER BY valor DESC", corte=corte)
    for f in filas:
        f["dias"] = (hoy() - date.fromisoformat(f["ultima"][:10])).days if f["ultima"] else None
    return _tabla(f"Productos sin movimiento ({dias} días)", [_col("nombre", "Producto"), _col("categoria", "Categoría"),
                                                              _col("stock", "Stock", "entero"), _col("valor", "Dinero inmovilizado", "dinero"),
                                                              _col("ultima", "Última venta", "fechahora"), _col("dias", "Días sin vender", "entero")],
                  filas, _suma(filas, "stock", "valor"), "Dinero detenido en estantería: candidatos a promoción o a no volver a comprar.")


def r_sugerido(db, d, h, dias_cobertura=7, **_):
    dias_cobertura = max(1, int(dias_cobertura))
    ref = hoy()
    p = _par(ref - timedelta(days=29), ref)
    filas = Q(db, LINEAS + "SELECT COALESCE(pv.nombre,'Sin proveedor') proveedor, pr.nombre nombre, pr.stock_actual stock, "
                           "pr.stock_minimo minimo, ROUND(SUM(l.cantidad) / 30.0, 2) diaria, ROUND(pr.costo_promedio, 2) costo "
                           "FROM productos pr JOIN lineas l ON l.producto_id = pr.id LEFT JOIN proveedores pv ON pv.id = pr.proveedor_id "
                           "WHERE pr.activo = 1 GROUP BY pr.id HAVING SUM(l.cantidad) > 0", **p)
    out = []
    for f in filas:
        sug = max(0, int(-(-(f["diaria"] * dias_cobertura + f["minimo"] - f["stock"]) // 1)))
        if sug > 0:
            out.append({**f, "sugerido": sug, "valor": round(sug * f["costo"])})
    out.sort(key=lambda f: (f["proveedor"], -f["valor"]))
    return _tabla("Sugerido de compras", [_col("proveedor", "Proveedor"), _col("nombre", "Producto"), _col("stock", "Stock", "entero"),
                                          _col("minimo", "Mínimo", "entero"), _col("diaria", "Venta diaria", "decimal"),
                                          _col("sugerido", "Sugerido", "entero"), _col("costo", "Costo", "decimal"),
                                          _col("valor", "Valor estimado", "dinero")], out, _suma(out, "sugerido", "valor"),
                  f"Sugerido = venta diaria (30 días) × {dias_cobertura} días de cobertura + stock mínimo − stock actual.")


def r_valorizacion(db, d, h, **_):
    filas = Q(db, "SELECT COALESCE(c.nombre,'Sin categoría') nombre, COUNT(*) productos, SUM(MAX(pr.stock_actual,0)) unidades, "
                  "ROUND(SUM(MAX(pr.stock_actual,0) * pr.costo_promedio)) costo, SUM(MAX(pr.stock_actual,0) * pr.precio_venta) venta "
                  "FROM productos pr LEFT JOIN categorias c ON c.id = pr.categoria_id WHERE pr.activo = 1 GROUP BY c.id ORDER BY costo DESC")
    return _tabla("Valorización del inventario", [_col("nombre", "Categoría"), _col("productos", "Productos", "entero"),
                                                  _col("unidades", "Unidades", "entero"), _col("costo", "Valor a costo", "dinero"),
                                                  _col("venta", "Valor a precio de venta", "dinero")], filas,
                  _suma(filas, "productos", "unidades", "costo", "venta"), "Stock negativo no se valora.")


def r_mermas(db, d, h, agrupar="motivo", **_):
    p = _par(d, h)
    base = ("FROM movimientos_inventario mv JOIN productos pr ON pr.id = mv.producto_id WHERE mv.tipo = 'MERMA' "
            "AND mv.fecha >= :d AND mv.fecha < :h")
    if agrupar == "producto":
        filas = Q(db, f"SELECT pr.nombre nombre, -SUM(mv.cantidad) unidades, ROUND(-SUM(mv.cantidad * mv.costo_unitario)) valor {base} "
                      "GROUP BY pr.id ORDER BY valor DESC", **p)
    else:
        filas = Q(db, f"SELECT COALESCE(mv.motivo,'OTRO') nombre, -SUM(mv.cantidad) unidades, ROUND(-SUM(mv.cantidad * mv.costo_unitario)) valor {base} "
                      "GROUP BY 1 ORDER BY valor DESC", **p)
        for f in filas:
            f["nombre"] = inv.MOTIVOS_MERMA.get(f["nombre"], f["nombre"])
    ventas = Q(db, "SELECT COALESCE(SUM(total),0) t FROM ventas WHERE estado='completada' AND fecha >= :d AND fecha < :h", **p)[0]["t"]
    tot = _suma(filas, "unidades", "valor")
    return _tabla("Mermas por " + ("producto" if agrupar == "producto" else "motivo"),
                  [_col("nombre", "Producto" if agrupar == "producto" else "Motivo"), _col("unidades", "Unidades", "entero"),
                   _col("valor", "Valor a costo", "dinero")], filas, tot,
                  f"Merma = {_pct(tot['valor'], ventas) or 0} % de las ventas del periodo.")


def r_compras_proveedor(db, d, h, **_):
    filas = Q(db, "SELECT COALESCE(pv.nombre,'Sin proveedor') nombre, COUNT(*) compras, ROUND(SUM(c.total)) total FROM compras c "
                  "LEFT JOIN proveedores pv ON pv.id = c.proveedor_id WHERE c.fecha >= :d AND c.fecha < :h GROUP BY pv.id ORDER BY total DESC", **_par(d, h))
    return _tabla("Compras por proveedor", [_col("nombre", "Proveedor"), _col("compras", "Compras", "entero"), _col("total", "Total comprado", "dinero")],
                  filas, _suma(filas, "compras", "total"))


def r_cierres(db, d, h, **_):
    filas = Q(db, "SELECT t.id id, u.nombre cajero, t.abierto_en abierto, t.cerrado_en cerrado, t.base_efectivo base, "
                  "(SELECT COALESCE(SUM(total),0) FROM ventas WHERE turno_id = t.id AND estado='completada') ventas, "
                  "t.efectivo_esperado esperado, t.efectivo_contado contado, t.diferencia_efectivo dif_efectivo, t.diferencia_banco dif_banco "
                  "FROM turnos t JOIN usuarios u ON u.id = t.usuario_id WHERE t.estado='cerrado' AND t.cerrado_en >= :d AND t.cerrado_en < :h "
                  "ORDER BY t.cerrado_en DESC", **_par(d, h))
    return _tabla("Cierres de caja", [_col("id", "Turno", "entero"), _col("cajero", "Cajero"), _col("abierto", "Apertura", "fechahora"),
                                      _col("cerrado", "Cierre", "fechahora"), _col("base", "Base", "dinero"), _col("ventas", "Ventas", "dinero"),
                                      _col("esperado", "Efectivo esperado", "dinero"), _col("contado", "Efectivo contado", "dinero"),
                                      _col("dif_efectivo", "Dif. efectivo", "dinero"), _col("dif_banco", "Dif. banco", "dinero")],
                  filas, _suma(filas, "ventas", "dif_efectivo", "dif_banco"), "Diferencia positiva = sobrante; negativa = faltante.")


def r_dif_cajero(db, d, h, **_):
    filas = Q(db, "SELECT u.nombre nombre, COUNT(*) turnos, SUM(t.diferencia_efectivo) dif_total, "
                  "SUM(CASE WHEN t.diferencia_efectivo < 0 THEN 1 ELSE 0 END) con_faltante, "
                  "SUM(CASE WHEN t.diferencia_efectivo < 0 THEN t.diferencia_efectivo ELSE 0 END) faltantes, "
                  "SUM(CASE WHEN t.diferencia_efectivo > 0 THEN t.diferencia_efectivo ELSE 0 END) sobrantes FROM turnos t "
                  "JOIN usuarios u ON u.id = t.usuario_id WHERE t.estado='cerrado' AND t.cerrado_en >= :d AND t.cerrado_en < :h "
                  "GROUP BY u.id ORDER BY dif_total ASC", **_par(d, h))
    return _tabla("Diferencias de caja por cajero", [_col("nombre", "Cajero"), _col("turnos", "Turnos", "entero"),
                                                     _col("con_faltante", "Turnos con faltante", "entero"), _col("faltantes", "Faltantes", "dinero"),
                                                     _col("sobrantes", "Sobrantes", "dinero"), _col("dif_total", "Neto", "dinero")],
                  filas, _suma(filas, "turnos", "con_faltante", "faltantes", "sobrantes", "dif_total"))


def r_conteos_historico(db, d, h, **_):
    filas = Q(db, "SELECT c.id id, c.nombre nombre, c.tipo tipo, c.cerrado_en fecha, c.exactitud_pct exactitud, "
                  "SUM(CASE WHEN ci.diferencia IS NOT NULL THEN 1 ELSE 0 END) contados, "
                  "SUM(CASE WHEN ci.diferencia != 0 THEN 1 ELSE 0 END) con_dif, "
                  "ROUND(SUM(CASE WHEN ci.diferencia < 0 THEN ci.diferencia * ci.costo_unitario ELSE 0 END)) faltantes, "
                  "ROUND(SUM(CASE WHEN ci.diferencia > 0 THEN ci.diferencia * ci.costo_unitario ELSE 0 END)) sobrantes "
                  "FROM conteos c JOIN conteo_items ci ON ci.conteo_id = c.id WHERE c.estado='aplicado' AND c.cerrado_en >= :d AND c.cerrado_en < :h "
                  "GROUP BY c.id ORDER BY c.cerrado_en DESC", **_par(d, h))
    return _tabla("Inconsistencias de conteos (histórico)", [_col("nombre", "Conteo"), _col("tipo", "Tipo"), _col("fecha", "Fecha", "fechahora"),
                                                             _col("contados", "Productos contados", "entero"), _col("con_dif", "Con diferencia", "entero"),
                                                             _col("exactitud", "Exactitud %", "porcentaje"), _col("faltantes", "Faltantes $", "dinero"),
                                                             _col("sobrantes", "Sobrantes $", "dinero")], filas, _suma(filas, "faltantes", "sobrantes"))


def r_iva(db, d, h, **_):
    filas = Q(db, LINEAS + "SELECT CASE WHEN tarifa > 0 THEN 'Tarifa ' || tarifa || '%' ELSE 'Exento / excluido' END nombre, "
                           "SUM(total - impuesto) base, SUM(impuesto) impuesto, SUM(total) total FROM lineas GROUP BY tarifa ORDER BY tarifa DESC", **_par(d, h))
    return _tabla("Impuestos por tarifa", [_col("nombre", "Tarifa"), _col("base", "Base gravable", "dinero"), _col("impuesto", "Impuesto", "dinero"),
                                           _col("total", "Total", "dinero")], filas, _suma(filas, "base", "impuesto", "total"),
                  "Netos de devoluciones. Para entregar al contador.")


def r_kardex(db, d, h, producto_id=None, **_):
    if not producto_id:
        raise ErrorNegocio("Elija un producto para ver su kardex.")
    p = db.get(m.Producto, int(producto_id))
    if not p:
        raise ErrorNegocio("Producto no encontrado.", 404)
    filas = inv.kardex(db, p.id, d, h, limite=5000)
    return _tabla(f"Kardex: {p.nombre}", [_col("fecha", "Fecha", "fechahora"), _col("tipo_nombre", "Movimiento"), _col("cantidad", "Cantidad", "entero"),
                                          _col("costo_unitario", "Costo", "decimal"), _col("stock_resultante", "Saldo", "entero"),
                                          _col("usuario", "Usuario"), _col("nota", "Nota")], filas)


# slug → (función, grupo, descripción, parámetros)
P_AGRUPAR_PROD_CAT = {"name": "agrupar", "label": "Agrupar por", "tipo": "opcion", "default": "producto",
                      "opciones": [["producto", "Producto"], ["categoria", "Categoría"]]}
CATALOGO: dict[str, dict] = {}


def _reg(slug, fn, grupo, titulo, desc, fechas=True, params=None):
    CATALOGO[slug] = {"slug": slug, "fn": fn, "grupo": grupo, "titulo": titulo, "descripcion": desc,
                      "fechas": fechas, "params": params or []}


_reg("ventas_dia", r_ventas_dia, "Ventas", "Ventas por día", "Tiquetes, unidades, ventas, costo y margen de cada día.")
_reg("ventas_hora", r_ventas_hora, "Ventas", "Ventas por hora", "En qué horas se vende más: para programar turnos.")
_reg("ventas_producto", r_ventas_producto, "Ventas", "Ventas por producto", "Qué se vende, cuánto deja y qué peso tiene.")
_reg("ventas_categoria", r_ventas_categoria, "Ventas", "Ventas por categoría", "Ventas y margen por categoría.")
_reg("ventas_cajero", r_ventas_cajero, "Ventas", "Ventas por cajero", "Tiquetes, ventas y ticket promedio por cajero.")
_reg("ventas_medio_pago", r_ventas_medio_pago, "Ventas", "Ventas por medio de pago", "Efectivo, débito, crédito, transferencias.")
_reg("rentabilidad", r_rentabilidad, "Ventas", "Rentabilidad", "Margen por producto o categoría con el costo del momento de la venta.",
     params=[P_AGRUPAR_PROD_CAT])
_reg("iva", r_iva, "Ventas", "Impuestos por tarifa", "Base e impuesto por tarifa de IVA, para el contador.")
_reg("tiquetes", r_tiquetes, "Control", "Detalle de tiquetes", "Listado de todos los tiquetes con sus medios de pago.")
_reg("anulaciones", r_anulaciones, "Control", "Anulaciones", "Ventas anuladas, quién las anuló y por qué.")
_reg("devoluciones", r_devoluciones, "Control", "Devoluciones", "Devoluciones de clientes, quién las autorizó.")
_reg("descuentos", r_descuentos, "Control", "Descuentos", "Tiquetes con descuento y su porcentaje.")
_reg("rotacion", r_rotacion, "Inventario", "Rotación de inventario", "Veces que rota el inventario, días de inventario y GMROI.",
     params=[{"name": "agrupar", "label": "Agrupar por", "tipo": "opcion", "default": "categoria",
              "opciones": [["total", "Todo el inventario"], ["categoria", "Categoría"], ["producto", "Producto"]]}])
_reg("cobertura", r_cobertura, "Inventario", "Cobertura (días de stock)", "Cuántos días alcanza el stock al ritmo actual de venta.", fechas=False)
_reg("abc", r_abc, "Inventario", "Análisis ABC (Pareto)", "Qué pocos productos generan la mayor parte de las ventas o del margen.",
     params=[{"name": "base", "label": "Basado en", "tipo": "opcion", "default": "ventas",
              "opciones": [["ventas", "Ventas"], ["margen", "Margen"]]}])
_reg("sin_movimiento", r_sin_movimiento, "Inventario", "Productos sin movimiento", "Stock que no se vende: dinero inmovilizado.",
     fechas=False, params=[{"name": "dias", "label": "Sin vender hace (días)", "tipo": "numero", "default": 60}])
_reg("sugerido", r_sugerido, "Inventario", "Sugerido de compras", "Qué pedir a cada proveedor según la venta reciente.",
     fechas=False, params=[{"name": "dias_cobertura", "label": "Días de cobertura deseados", "tipo": "numero", "default": 7}])
_reg("valorizacion", r_valorizacion, "Inventario", "Valorización del inventario", "Valor del stock a costo y a precio de venta.", fechas=False)
_reg("mermas", r_mermas, "Inventario", "Mermas", "Pérdidas por vencimiento, daño, robo o consumo interno.",
     params=[{"name": "agrupar", "label": "Agrupar por", "tipo": "opcion", "default": "motivo",
              "opciones": [["motivo", "Motivo"], ["producto", "Producto"]]}])
_reg("compras_proveedor", r_compras_proveedor, "Inventario", "Compras por proveedor", "Cuánto se compra a cada proveedor.")
_reg("kardex", r_kardex, "Inventario", "Kardex de un producto", "Historia completa de entradas y salidas de un producto.",
     params=[{"name": "producto_id", "label": "Producto", "tipo": "producto", "default": None}])
_reg("cierres", r_cierres, "Caja", "Cierres de caja", "Cada turno cerrado con su esperado, contado y diferencia.")
_reg("dif_cajero", r_dif_cajero, "Caja", "Diferencias por cajero", "Faltantes y sobrantes acumulados por cajero.")
_reg("conteos_historico", r_conteos_historico, "Caja", "Conteos de inventario (histórico)", "Exactitud y diferencias de cada toma de inventario.")


def catalogo_publico() -> list[dict]:
    return [{k: v for k, v in c.items() if k != "fn"} for c in CATALOGO.values()]


def generar(db: Session, slug: str, desde: date | None, hasta: date | None, params: dict) -> dict:
    c = CATALOGO.get(slug)
    if not c:
        raise ErrorNegocio("Informe no encontrado.", 404)
    d, h = rango(desde, hasta)
    r = c["fn"](db, d, h, **{k: v for k, v in params.items() if v not in (None, "")})
    r["slug"], r["desde"], r["hasta"] = slug, d.isoformat(), h.isoformat()
    return r
