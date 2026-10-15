"""Tomas de inventario físico: programación, captura ciega, revisión de inconsistencias y ajustes.

El stock teórico de cada producto se calcula con el kardex *en el momento en que se contó*
(stock actual − movimientos posteriores a la captura), así se puede contar con la tienda abierta
sin que las ventas generen diferencias falsas.
"""
from __future__ import annotations

import calendar
import json
from datetime import date, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, selectinload

from .. import models as m
from ..core import ErrorNegocio, ahora, auditar, cfg_int, hoy
from . import inventario as inv

TIPOS = ("total", "parcial", "ciclico")
FRECUENCIAS = ("una_vez", "dias", "semanal", "quincenal", "mensual")
ESTADOS = {"borrador": "Borrador", "en_conteo": "En conteo", "en_revision": "En revisión",
           "aplicado": "Aplicado", "cancelado": "Cancelado"}


# ───────────────────────────── Programación ─────────────────────────────
def _sumar_meses(d: date, meses: int) -> date:
    mes = d.month - 1 + meses
    anio, mes = d.year + mes // 12, mes % 12 + 1
    return date(anio, mes, min(d.day, calendar.monthrange(anio, mes)[1]))


def siguiente_fecha(frecuencia: str, intervalo: int, desde: date) -> date | None:
    intervalo = max(1, intervalo)
    if frecuencia == "dias":
        return desde + timedelta(days=intervalo)
    if frecuencia == "semanal":
        return desde + timedelta(weeks=intervalo)
    if frecuencia == "quincenal":
        return desde + timedelta(days=15 * intervalo)
    if frecuencia == "mensual":
        return _sumar_meses(desde, intervalo)
    return None  # una_vez


def _validar_alcance(tipo: str, alcance: dict):
    if tipo not in TIPOS:
        raise ErrorNegocio("Tipo de conteo no válido.")
    if tipo == "parcial" and not any(alcance.get(k) for k in ("categoria_ids", "proveedor_ids", "ubicaciones")):
        raise ErrorNegocio("Un conteo parcial necesita al menos una categoría, proveedor o ubicación.")
    if tipo == "ciclico" and int(alcance.get("n") or 0) < 1:
        raise ErrorNegocio("Indique cuántos productos incluir en el conteo cíclico.")


def guardar_programacion(db: Session, datos: dict, prog: m.ProgramacionConteo | None = None) -> m.ProgramacionConteo:
    tipo, alcance = datos.get("tipo", "total"), datos.get("alcance") or {}
    _validar_alcance(tipo, alcance)
    frecuencia = datos.get("frecuencia", "una_vez")
    if frecuencia not in FRECUENCIAS:
        raise ErrorNegocio("Frecuencia no válida.")
    if not (datos.get("nombre") or "").strip():
        raise ErrorNegocio("Escriba un nombre para la programación.")
    prox = date.fromisoformat(datos["proxima_fecha"]) if datos.get("proxima_fecha") else None
    if not prox:
        raise ErrorNegocio("Indique la fecha del conteo.")
    prog = prog or m.ProgramacionConteo()
    prog.nombre, prog.tipo, prog.alcance = datos["nombre"].strip(), tipo, json.dumps(alcance)
    prog.frecuencia, prog.intervalo = frecuencia, max(1, int(datos.get("intervalo") or 1))
    prog.proxima_fecha, prog.activo = prox, bool(datos.get("activo", True))
    db.add(prog)
    db.flush()
    return prog


def serializar_programacion(p: m.ProgramacionConteo) -> dict:
    return {"id": p.id, "nombre": p.nombre, "tipo": p.tipo, "alcance": json.loads(p.alcance or "{}"),
            "frecuencia": p.frecuencia, "intervalo": p.intervalo,
            "proxima_fecha": p.proxima_fecha.isoformat() if p.proxima_fecha else None, "activo": p.activo}


def recordatorios(db: Session) -> list[dict]:
    """Programaciones vencidas o por vencer (para el dashboard)."""
    limite = hoy() + timedelta(days=cfg_int(db, "conteo_recordatorio_dias"))
    filas = db.scalars(select(m.ProgramacionConteo).where(
        m.ProgramacionConteo.activo.is_(True), m.ProgramacionConteo.proxima_fecha <= limite)
        .order_by(m.ProgramacionConteo.proxima_fecha)).all()
    return [{**serializar_programacion(p), "dias_restantes": (p.proxima_fecha - hoy()).days,
             "vencida": p.proxima_fecha < hoy()} for p in filas]


# ───────────────────────────── Ciclo de vida ─────────────────────────────
def _conteo(db: Session, conteo_id: int) -> m.Conteo:
    c = db.get(m.Conteo, conteo_id)
    if not c:
        raise ErrorNegocio("Conteo no encontrado.", 404)
    return c


def crear(db: Session, usuario: m.Usuario, *, nombre: str, tipo: str, alcance: dict,
          programacion_id: int | None = None) -> m.Conteo:
    _validar_alcance(tipo, alcance or {})
    if not (nombre or "").strip():
        raise ErrorNegocio("Escriba un nombre para el conteo.")
    c = m.Conteo(nombre=nombre.strip(), tipo=tipo, alcance=json.dumps(alcance or {}), estado="borrador",
                 programacion_id=programacion_id, creado_por=usuario.id, creado_en=ahora())
    db.add(c)
    db.flush()
    return c


def _ultimos_conteos(db: Session) -> dict[int, tuple[date, int]]:
    """producto_id → (fecha del último conteo aplicado donde se contó, diferencia obtenida)."""
    ultimo: dict[int, tuple[date, int]] = {}
    for pid, cerrado, dif in db.execute(
            select(m.ConteoItem.producto_id, m.Conteo.cerrado_en, m.ConteoItem.diferencia)
            .join(m.Conteo, m.Conteo.id == m.ConteoItem.conteo_id)
            .where(m.Conteo.estado == "aplicado", m.ConteoItem.diferencia.is_not(None))
            .order_by(m.Conteo.cerrado_en)):
        ultimo[pid] = (cerrado.date(), dif)
    return ultimo


def productos_en_alcance(db: Session, tipo: str, alcance: dict) -> list[m.Producto]:
    q = select(m.Producto).where(m.Producto.activo.is_(True))
    if tipo in ("parcial", "ciclico"):
        if alcance.get("categoria_ids"):
            q = q.where(m.Producto.categoria_id.in_([int(x) for x in alcance["categoria_ids"]]))
        if alcance.get("proveedor_ids"):
            q = q.where(m.Producto.proveedor_id.in_([int(x) for x in alcance["proveedor_ids"]]))
        if alcance.get("ubicaciones"):
            q = q.where(m.Producto.ubicacion.in_(alcance["ubicaciones"]))
    productos = db.scalars(q).all()
    if tipo != "ciclico":
        return productos
    # cíclico: primero los que tuvieron diferencia la última vez, luego los nunca contados / más antiguos,
    # y entre iguales los de mayor valor en inventario
    ultimo = _ultimos_conteos(db)

    def prioridad(p: m.Producto):
        previo = ultimo.get(p.id)
        con_dif = 0 if previo and previo[1] != 0 else 1
        antiguedad = previo[0] if previo else date.min
        return (con_dif, antiguedad, -abs(p.stock_actual * p.costo_promedio))

    return sorted(productos, key=prioridad)[: max(1, int(alcance.get("n") or 50))]


def iniciar(db: Session, usuario: m.Usuario, conteo_id: int) -> m.Conteo:
    c = _conteo(db, conteo_id)
    if c.estado != "borrador":
        raise ErrorNegocio("Solo se puede iniciar un conteo en borrador.", 409)
    if db.scalar(select(func.count()).select_from(m.Conteo).where(m.Conteo.estado.in_(("en_conteo", "en_revision")))):
        raise ErrorNegocio("Ya hay un conteo en curso. Termínelo o cancélelo antes de iniciar otro.", 409)
    if c.tipo == "total":  # lo más común y lo más grande: se copia directo, sin cargar 30.000 objetos
        db.execute(text("INSERT INTO conteo_items (conteo_id, producto_id, costo_unitario, no_contado, reconteo) "
                        "SELECT :c, id, costo_promedio, 0, 0 FROM productos WHERE activo = 1"), {"c": c.id})
        cantidad = db.scalar(select(func.count()).select_from(m.ConteoItem).where(m.ConteoItem.conteo_id == c.id)) or 0
    else:
        productos = productos_en_alcance(db, c.tipo, json.loads(c.alcance or "{}"))
        cantidad = len(productos)
        if productos:
            db.execute(m.ConteoItem.__table__.insert(), [{"conteo_id": c.id, "producto_id": p.id, "costo_unitario": p.costo_promedio,
                                                          "no_contado": False, "reconteo": False} for p in productos])
    if not cantidad:
        raise ErrorNegocio("El alcance elegido no tiene productos.")
    c.estado, c.iniciado_en = "en_conteo", ahora()
    if c.programacion_id:
        prog = db.get(m.ProgramacionConteo, c.programacion_id)
        if prog:
            sig = siguiente_fecha(prog.frecuencia, prog.intervalo, hoy())
            prog.proxima_fecha, prog.activo = (sig, prog.activo) if sig else (prog.proxima_fecha, False)
    auditar(db, usuario.id, "CONTEO_INICIADO", "conteo", c.id, despues={"productos": cantidad})
    db.flush()
    return c


def capturar(db: Session, usuario: m.Usuario, conteo_id: int, *, codigo: str | None = None,
             producto_id: int | None = None, cantidad: int, ubicacion: str | None = None) -> dict:
    c = _conteo(db, conteo_id)
    if c.estado != "en_conteo":
        raise ErrorNegocio("El conteo no está recibiendo capturas.", 409)
    unidades = 1
    if codigo:
        cb = db.get(m.CodigoBarra, codigo.strip())
        if cb:
            producto_id, unidades = cb.producto_id, cb.unidades_por_codigo
        else:
            p = db.scalars(select(m.Producto).where(m.Producto.codigo_interno == codigo.strip())).first()
            producto_id = p.id if p else None
        if not producto_id:
            raise ErrorNegocio(f"El código {codigo} no existe en el catálogo.", 404, "CODIGO_NO_EXISTE")
    if not producto_id:
        raise ErrorNegocio("Indique el producto.")
    if int(cantidad) < 0:
        raise ErrorNegocio("La cantidad no puede ser negativa.")
    item = db.get(m.ConteoItem, (c.id, producto_id))
    p = db.get(m.Producto, producto_id)
    if not item:
        raise ErrorNegocio(f"«{p.nombre}» no hace parte del alcance de este conteo.", 409, "FUERA_DE_ALCANCE")
    cap = m.ConteoCaptura(conteo_id=c.id, producto_id=producto_id, cantidad=int(cantidad) * unidades,
                          ubicacion=(ubicacion or "").strip() or p.ubicacion, usuario_id=usuario.id, capturado_en=ahora())
    db.add(cap)
    db.flush()
    # respuesta ciega: nada del stock del sistema
    total = db.scalar(select(func.coalesce(func.sum(m.ConteoCaptura.cantidad), 0)).where(
        m.ConteoCaptura.conteo_id == c.id, m.ConteoCaptura.producto_id == producto_id,
        m.ConteoCaptura.reemplazada.is_(False))) or 0
    return {"captura_id": cap.id, "producto_id": p.id, "nombre": p.nombre, "cantidad": cap.cantidad,
            "total_contado": total}


def listar_capturas(db: Session, conteo_id: int, limite: int = 100) -> list[dict]:
    return [{"id": cap.id, "producto_id": cap.producto_id, "nombre": nombre, "cantidad": cap.cantidad,
             "ubicacion": cap.ubicacion, "usuario": usuario, "capturado_en": cap.capturado_en.isoformat()}
            for cap, nombre, usuario in db.execute(
                select(m.ConteoCaptura, m.Producto.nombre, m.Usuario.nombre)
                .join(m.Producto, m.Producto.id == m.ConteoCaptura.producto_id)
                .join(m.Usuario, m.Usuario.id == m.ConteoCaptura.usuario_id)
                .where(m.ConteoCaptura.conteo_id == conteo_id, m.ConteoCaptura.reemplazada.is_(False))
                .order_by(m.ConteoCaptura.id.desc()).limit(limite))]


def eliminar_captura(db: Session, conteo_id: int, captura_id: int):
    c = _conteo(db, conteo_id)
    if c.estado != "en_conteo":
        raise ErrorNegocio("El conteo no está recibiendo capturas.", 409)
    cap = db.get(m.ConteoCaptura, captura_id)
    if not cap or cap.conteo_id != c.id:
        raise ErrorNegocio("Captura no encontrada.", 404)
    db.delete(cap)


def progreso(db: Session, conteo_id: int) -> dict:
    total = db.scalar(select(func.count()).select_from(m.ConteoItem).where(m.ConteoItem.conteo_id == conteo_id)) or 0
    contados = db.scalar(select(func.count(func.distinct(m.ConteoCaptura.producto_id))).where(
        m.ConteoCaptura.conteo_id == conteo_id, m.ConteoCaptura.reemplazada.is_(False))) or 0
    return {"productos": total, "contados": contados, "pendientes": total - contados}


def _calcular_items(db: Session, c: m.Conteo):
    """Calcula stock teórico (al momento de la captura), contado y diferencia de cada ítem."""
    filas = db.execute(text("""
        SELECT ci.producto_id, p.stock_actual, agg.suma, agg.ult,
               CASE WHEN agg.ult IS NULL THEN 0 ELSE
                 (SELECT COALESCE(SUM(mv.cantidad), 0) FROM movimientos_inventario mv
                   WHERE mv.producto_id = ci.producto_id AND mv.fecha > agg.ult) END AS despues
        FROM conteo_items ci
        JOIN productos p ON p.id = ci.producto_id
        LEFT JOIN (SELECT producto_id, SUM(cantidad) suma, MAX(capturado_en) ult FROM conteo_capturas
                    WHERE conteo_id = :c AND reemplazada = 0 GROUP BY producto_id) agg
               ON agg.producto_id = ci.producto_id
        WHERE ci.conteo_id = :c"""), {"c": c.id}).all()
    por_id = {i.producto_id: i for i in c.items}
    for pid, stock, suma, ult, despues in filas:
        it = por_id[pid]
        if ult is None:
            it.no_contado, it.cantidad_contada, it.stock_teorico, it.diferencia = True, None, stock, None
        else:
            it.no_contado, it.cantidad_contada = False, int(suma)
            it.stock_teorico = stock - int(despues)
            it.diferencia = it.cantidad_contada - it.stock_teorico
    db.flush()


def cerrar_captura(db: Session, usuario: m.Usuario, conteo_id: int) -> m.Conteo:
    c = _conteo(db, conteo_id)
    if c.estado != "en_conteo":
        raise ErrorNegocio("El conteo no está en captura.", 409)
    _calcular_items(db, c)
    c.estado = "en_revision"
    auditar(db, usuario.id, "CONTEO_CAPTURA_CERRADA", "conteo", c.id)
    db.flush()
    return c


def reconteo(db: Session, usuario: m.Usuario, conteo_id: int, producto_ids: list[int]) -> m.Conteo:
    c = _conteo(db, conteo_id)
    if c.estado != "en_revision":
        raise ErrorNegocio("Solo se puede pedir reconteo en la revisión.", 409)
    if not producto_ids:
        raise ErrorNegocio("Seleccione los productos a recontar.")
    for it in c.items:
        if it.producto_id in producto_ids:
            it.reconteo = True
            it.no_contado, it.cantidad_contada, it.diferencia = True, None, None
    db.execute(text("UPDATE conteo_capturas SET reemplazada = 1 WHERE conteo_id = :c AND producto_id IN (%s)"
                    % ",".join(str(int(x)) for x in producto_ids)), {"c": c.id})
    c.estado = "en_conteo"
    auditar(db, usuario.id, "CONTEO_RECONTEO", "conteo", c.id, despues={"productos": producto_ids})
    db.flush()
    return c


def cancelar(db: Session, usuario: m.Usuario, conteo_id: int) -> m.Conteo:
    c = _conteo(db, conteo_id)
    if c.estado in ("aplicado", "cancelado"):
        raise ErrorNegocio("El conteo ya está cerrado.", 409)
    c.estado, c.cerrado_en = "cancelado", ahora()
    auditar(db, usuario.id, "CONTEO_CANCELADO", "conteo", c.id)
    return c


# ───────────────────────────── Revisión ─────────────────────────────
def _recurrentes(db: Session, c: m.Conteo, faltantes: list[int]) -> dict[int, int]:
    """Producto → número de conteos seguidos con faltante (incluido este), solo si es >= 2."""
    if not faltantes:
        return {}
    previos = db.scalars(select(m.Conteo.id).where(m.Conteo.estado == "aplicado", m.Conteo.id != c.id)
                         .order_by(m.Conteo.cerrado_en.desc()).limit(4)).all()
    racha = {pid: 1 for pid in faltantes}
    vivos = set(faltantes)
    for cid in previos:
        difs = dict(db.execute(select(m.ConteoItem.producto_id, m.ConteoItem.diferencia).where(
            m.ConteoItem.conteo_id == cid, m.ConteoItem.producto_id.in_(vivos),
            m.ConteoItem.diferencia.is_not(None))).all())
        for pid in list(vivos):
            if pid not in difs:
                continue  # no se contó en ese conteo: no corta la racha
            if difs[pid] < 0:
                racha[pid] += 1
            else:
                vivos.discard(pid)
        if not vivos:
            break
    return {pid: n for pid, n in racha.items() if n >= 2}


def revision(db: Session, conteo_id: int) -> dict:
    c = _conteo(db, conteo_id)
    filas = []
    primer_codigo = select(m.CodigoBarra.codigo).where(m.CodigoBarra.producto_id == m.Producto.id).limit(1).scalar_subquery()
    consulta = (select(m.ConteoItem.producto_id, m.ConteoItem.stock_teorico, m.ConteoItem.cantidad_contada, m.ConteoItem.diferencia,
                       m.ConteoItem.costo_unitario, m.ConteoItem.no_contado, m.ConteoItem.reconteo, m.Producto.nombre, m.Producto.ubicacion,
                       m.Producto.codigo_interno, primer_codigo.label("codigo"))
                .join(m.Producto, m.Producto.id == m.ConteoItem.producto_id).where(m.ConteoItem.conteo_id == c.id))
    for pid, teorico, contado, dif, costo, no_contado, reconteo_, nombre, ubicacion, cod_interno, codigo in db.execute(consulta):
        filas.append({
            "producto_id": pid, "nombre": nombre, "ubicacion": ubicacion, "codigo": codigo or cod_interno,
            "stock_teorico": teorico, "contado": contado, "diferencia": dif,
            "costo_unitario": round(costo, 2),
            "valor_diferencia": round(dif * costo) if dif is not None else None,
            "pct": round(dif * 100 / teorico, 1) if dif is not None and teorico else None,
            "no_contado": no_contado, "reconteo": reconteo_})
    contados = [f for f in filas if not f["no_contado"]]
    con_dif = [f for f in contados if f["diferencia"] != 0]
    faltantes = [f for f in con_dif if f["diferencia"] < 0]
    sobrantes = [f for f in con_dif if f["diferencia"] > 0]
    recurr = _recurrentes(db, c, [f["producto_id"] for f in faltantes])
    for f in filas:
        f["racha_faltantes"] = recurr.get(f["producto_id"], 0)
    return {
        "conteo": serializar(c),
        "resumen": {
            "productos": len(filas), "contados": len(contados), "no_contados": len(filas) - len(contados),
            "con_diferencia": len(con_dif), "faltantes": len(faltantes), "sobrantes": len(sobrantes),
            "valor_faltantes": sum(f["valor_diferencia"] for f in faltantes),
            "valor_sobrantes": sum(f["valor_diferencia"] for f in sobrantes),
            "valor_neto": sum(f["valor_diferencia"] for f in con_dif),
            "exactitud_pct": round((len(contados) - len(con_dif)) * 100 / len(contados), 1) if contados else None,
            "recurrentes": len(recurr)},
        "items": sorted(filas, key=lambda f: (f["no_contado"], -abs(f["valor_diferencia"] or 0))),
    }


def aplicar(db: Session, usuario: m.Usuario, conteo_id: int, asumir_cero: bool = False) -> m.Conteo:
    c = _conteo(db, conteo_id)
    if c.estado != "en_revision":
        raise ErrorNegocio("El conteo debe estar en revisión para aplicarlo.", 409)
    _calcular_items(db, c)  # por si llegaron ventas durante la revisión
    pendientes_reconteo = [it for it in c.items if it.reconteo and it.no_contado]
    if pendientes_reconteo:
        raise ErrorNegocio(f"Hay {len(pendientes_reconteo)} producto(s) pendientes de reconteo.", 409)
    contados = ajustados = 0
    for it in c.items:
        p = db.get(m.Producto, it.producto_id)
        if it.no_contado:
            if not asumir_cero:
                continue
            it.stock_teorico, it.cantidad_contada, it.diferencia = p.stock_actual, 0, -p.stock_actual
        contados += 1
        it.costo_unitario = p.costo_promedio
        if it.diferencia:
            inv.registrar_movimiento(db, p, "AJUSTE_CONTEO", it.diferencia, costo_unitario=p.costo_promedio,
                                     referencia_tipo="conteo", referencia_id=c.id, usuario_id=usuario.id,
                                     nota=f"Conteo «{c.nombre}»")
            ajustados += 1
    c.exactitud_pct = round((contados - ajustados) * 100 / contados, 1) if contados else None
    c.estado, c.cerrado_en, c.aprobado_por, c.asumio_cero = "aplicado", ahora(), usuario.id, asumir_cero
    auditar(db, usuario.id, "CONTEO_APLICADO", "conteo", c.id,
            despues={"ajustados": ajustados, "exactitud": c.exactitud_pct, "asumir_cero": asumir_cero})
    db.flush()
    return c


def serializar(c: m.Conteo) -> dict:
    return {"id": c.id, "nombre": c.nombre, "tipo": c.tipo, "alcance": json.loads(c.alcance or "{}"),
            "estado": c.estado, "estado_nombre": ESTADOS.get(c.estado, c.estado),
            "creado_en": c.creado_en.isoformat(), "iniciado_en": c.iniciado_en.isoformat() if c.iniciado_en else None,
            "cerrado_en": c.cerrado_en.isoformat() if c.cerrado_en else None,
            "exactitud_pct": c.exactitud_pct, "asumio_cero": c.asumio_cero, "programacion_id": c.programacion_id}


def listar(db: Session, limite: int = 100) -> list[dict]:
    return [serializar(c) for c in db.scalars(select(m.Conteo).order_by(m.Conteo.id.desc()).limit(limite))]


def informe_tabla(db: Session, conteo_id: int) -> dict:
    r = revision(db, conteo_id)
    cols = [("nombre", "Producto", "texto"), ("ubicacion", "Ubicación", "texto"), ("stock_teorico", "Stock sistema", "entero"),
            ("contado", "Contado", "entero"), ("diferencia", "Diferencia", "entero"),
            ("valor_diferencia", "Valor dif. (costo)", "dinero"), ("pct", "% dif.", "porcentaje"),
            ("racha_faltantes", "Faltante seguido (conteos)", "entero")]
    return {"titulo": f"Conteo: {r['conteo']['nombre']}", "columnas": [{"key": k, "titulo": t, "tipo": tp} for k, t, tp in cols],
            "filas": r["items"], "totales": {"valor_diferencia": r["resumen"]["valor_neto"]},
            "resumen": r["resumen"]}
