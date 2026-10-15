"""Inventario: todo cambio de stock pasa por `registrar_movimiento` (kardex)."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .. import models as m
from ..core import ErrorNegocio, ahora, auditar, cfg_bool, hoy, redondear

TIPOS_MOVIMIENTO = {
    "VENTA": "Venta", "ANULACION_VENTA": "Anulación de venta", "DEVOLUCION_VENTA": "Devolución de venta",
    "COMPRA": "Compra", "MERMA": "Merma / baja", "AJUSTE": "Ajuste manual",
    "AJUSTE_CONTEO": "Ajuste por conteo", "SALDO_INICIAL": "Saldo inicial",
}
MOTIVOS_MERMA = {"VENCIDO": "Vencido", "DANADO": "Dañado", "ROBO": "Robo / pérdida",
                 "CONSUMO_INTERNO": "Consumo interno", "OTRO": "Otro"}


def registrar_movimiento(db: Session, producto: m.Producto, tipo: str, cantidad: int, *,
                         costo_unitario: float | None = None, referencia_tipo: str | None = None,
                         referencia_id: int | None = None, usuario_id: int | None = None,
                         motivo: str | None = None, nota: str | None = None,
                         fecha: datetime | None = None) -> m.MovimientoInventario:
    """Aplica `cantidad` (con signo) al stock y deja el rastro en el kardex, en la misma transacción."""
    producto.stock_actual += cantidad
    producto.actualizado_en = ahora()
    mov = m.MovimientoInventario(
        producto_id=producto.id, fecha=fecha or ahora(), tipo=tipo, cantidad=cantidad,
        costo_unitario=producto.costo_promedio if costo_unitario is None else costo_unitario,
        stock_resultante=producto.stock_actual, referencia_tipo=referencia_tipo,
        referencia_id=referencia_id, usuario_id=usuario_id, motivo=motivo, nota=nota)
    db.add(mov)
    return mov


def verificar_stock(db: Session, producto: m.Producto, cantidad_a_sacar: int):
    if cantidad_a_sacar > 0 and not cfg_bool(db, "permitir_stock_negativo") \
            and producto.stock_actual < cantidad_a_sacar:
        raise ErrorNegocio(f"Stock insuficiente de «{producto.nombre}»: hay {producto.stock_actual}, "
                           f"se piden {cantidad_a_sacar}.", 409, "STOCK_INSUFICIENTE")


def aplicar_compra_a_costo(producto: m.Producto, cantidad: int, costo_compra: float):
    """Costo promedio ponderado. Si el stock era <= 0, el costo pasa a ser el de la compra."""
    if producto.stock_actual <= 0:
        producto.costo_promedio = costo_compra
    else:
        total = producto.stock_actual + cantidad
        producto.costo_promedio = (producto.stock_actual * producto.costo_promedio
                                   + cantidad * costo_compra) / total


def registrar_merma(db: Session, usuario: m.Usuario, producto_id: int, cantidad: int, motivo: str,
                    nota: str | None = None) -> m.MovimientoInventario:
    if cantidad <= 0:
        raise ErrorNegocio("La cantidad de la merma debe ser mayor a cero.")
    if motivo not in MOTIVOS_MERMA:
        raise ErrorNegocio("Motivo de merma no válido.")
    p = db.get(m.Producto, producto_id)
    if not p:
        raise ErrorNegocio("Producto no encontrado.", 404)
    mov = registrar_movimiento(db, p, "MERMA", -cantidad, usuario_id=usuario.id, motivo=motivo, nota=nota)
    auditar(db, usuario.id, "MERMA", "producto", p.id, despues={"cantidad": cantidad, "motivo": motivo})
    return mov


def ajustar_stock(db: Session, usuario: m.Usuario, producto_id: int, *, nuevo_stock: int | None = None,
                  delta: int | None = None, nota: str | None = None) -> m.MovimientoInventario | None:
    p = db.get(m.Producto, producto_id)
    if not p:
        raise ErrorNegocio("Producto no encontrado.", 404)
    if (nuevo_stock is None) == (delta is None):
        raise ErrorNegocio("Indique el nuevo stock o la diferencia, pero no ambos.")
    d = (nuevo_stock - p.stock_actual) if nuevo_stock is not None else delta
    if d == 0:
        return None
    if not nota or not nota.strip():
        raise ErrorNegocio("Escriba el motivo del ajuste.")
    antes = p.stock_actual
    mov = registrar_movimiento(db, p, "AJUSTE", d, usuario_id=usuario.id, nota=nota.strip())
    auditar(db, usuario.id, "AJUSTE_INVENTARIO", "producto", p.id,
            antes={"stock": antes}, despues={"stock": p.stock_actual, "nota": nota})
    return mov


def saldo_inicial(db: Session, usuario_id: int | None, producto: m.Producto, cantidad: int, costo: float):
    if cantidad:
        registrar_movimiento(db, producto, "SALDO_INICIAL", cantidad, costo_unitario=costo,
                             usuario_id=usuario_id, nota="Saldo inicial")


# ───────────────────────────── Consultas ─────────────────────────────
def stock_en(db: Session, producto_id: int, momento: datetime) -> int:
    """Stock que tenía el producto en `momento` (stock actual menos lo movido después)."""
    actual = db.scalar(select(m.Producto.stock_actual).where(m.Producto.id == producto_id)) or 0
    despues = db.scalar(select(func.coalesce(func.sum(m.MovimientoInventario.cantidad), 0)).where(
        m.MovimientoInventario.producto_id == producto_id, m.MovimientoInventario.fecha > momento)) or 0
    return actual - despues


def kardex(db: Session, producto_id: int, desde: date | None = None, hasta: date | None = None,
           limite: int = 500) -> list[dict]:
    q = select(m.MovimientoInventario, m.Usuario.nombre).outerjoin(
        m.Usuario, m.Usuario.id == m.MovimientoInventario.usuario_id).where(
        m.MovimientoInventario.producto_id == producto_id)
    if desde:
        q = q.where(m.MovimientoInventario.fecha >= datetime.combine(desde, time.min))
    if hasta:
        q = q.where(m.MovimientoInventario.fecha < datetime.combine(hasta + timedelta(days=1), time.min))
    q = q.order_by(m.MovimientoInventario.fecha.desc(), m.MovimientoInventario.id.desc()).limit(limite)
    return [{
        "id": mv.id, "fecha": mv.fecha.isoformat(), "tipo": mv.tipo, "tipo_nombre": TIPOS_MOVIMIENTO.get(mv.tipo, mv.tipo),
        "cantidad": mv.cantidad, "costo_unitario": round(mv.costo_unitario, 2), "stock_resultante": mv.stock_resultante,
        "referencia_tipo": mv.referencia_tipo, "referencia_id": mv.referencia_id, "usuario": nombre,
        "motivo": mv.motivo, "nota": mv.nota,
    } for mv, nombre in db.execute(q)]


def alertas(db: Session) -> dict:
    base = select(m.Producto.id, m.Producto.nombre, m.Producto.stock_actual, m.Producto.stock_minimo,
                  m.Producto.costo_promedio).where(m.Producto.activo.is_(True))

    def lista(cond, orden):
        return [{"id": i, "nombre": n, "stock": s, "minimo": mn} for i, n, s, mn, _ in
                db.execute(base.where(cond).order_by(orden).limit(200))]

    agotados = lista((m.Producto.stock_actual == 0) & (m.Producto.stock_minimo > 0), m.Producto.nombre)
    bajo = lista((m.Producto.stock_actual > 0) & (m.Producto.stock_actual <= m.Producto.stock_minimo),
                 m.Producto.nombre)
    negativos = lista(m.Producto.stock_actual < 0, m.Producto.stock_actual)
    return {"agotados": agotados, "bajo_minimo": bajo, "negativos": negativos,
            "total": len(agotados) + len(bajo) + len(negativos)}


# ───────────────────────────── Foto diaria (para rotación) ─────────────────────────────
def foto_inventario(db: Session, fecha: date):
    """Guarda (stock, costo) de cada producto con stock distinto de cero al cierre del día `fecha`.
    Para el día de hoy usa el stock actual; para días pasados lo reconstruye con el kardex."""
    db.execute(text("DELETE FROM inventario_diario WHERE fecha = :f"), {"f": fecha.isoformat()})
    if fecha >= hoy():
        db.execute(text(
            "INSERT INTO inventario_diario (fecha, producto_id, stock, costo_promedio) "
            "SELECT :f, id, stock_actual, costo_promedio FROM productos WHERE stock_actual != 0"),
            {"f": fecha.isoformat()})
    else:
        limite = datetime.combine(fecha + timedelta(days=1), time.min).isoformat(sep=" ")
        db.execute(text(
            "INSERT INTO inventario_diario (fecha, producto_id, stock, costo_promedio) "
            "SELECT :f, p.id, p.stock_actual - COALESCE((SELECT SUM(cantidad) FROM movimientos_inventario mv "
            "  WHERE mv.producto_id = p.id AND mv.fecha >= :lim), 0), p.costo_promedio FROM productos p "
            "WHERE p.stock_actual - COALESCE((SELECT SUM(cantidad) FROM movimientos_inventario mv "
            "  WHERE mv.producto_id = p.id AND mv.fecha >= :lim), 0) != 0"),
            {"f": fecha.isoformat(), "lim": limite})


def asegurar_fotos(db: Session, desde: date, hasta: date, refrescar_hoy: bool = True):
    """Completa los días sin foto entre `desde` y `hasta` (y, si se pide, refresca la de hoy)."""
    hasta = min(hasta, hoy())
    existentes = {d for (d,) in db.execute(text(
        "SELECT DISTINCT fecha FROM inventario_diario WHERE fecha BETWEEN :a AND :b"),
        {"a": desde.isoformat(), "b": hasta.isoformat()})}
    # un día sin productos con stock no deja filas; se reintenta, es barato
    d = desde
    while d <= hasta:
        if (d == hoy() and refrescar_hoy) or (d != hoy() and d.isoformat() not in existentes):
            foto_inventario(db, d)
        d += timedelta(days=1)
