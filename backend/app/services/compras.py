"""Compras / entrada de mercancía: actualiza stock, costo promedio ponderado y, opcionalmente, el precio."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..core import ErrorNegocio, ahora, auditar
from . import inventario as inv
from .productos import cambiar_precio


def crear_compra(db: Session, usuario: m.Usuario, datos: dict) -> m.Compra:
    items = datos.get("items") or []
    if not items:
        raise ErrorNegocio("La compra no tiene productos.")
    prov_id = datos.get("proveedor_id")
    if prov_id and not db.get(m.Proveedor, prov_id):
        raise ErrorNegocio("Proveedor no encontrado.", 404)
    compra = m.Compra(proveedor_id=prov_id, numero_factura=(datos.get("numero_factura") or "").strip() or None,
                      fecha=ahora(), usuario_id=usuario.id, nota=(datos.get("nota") or "").strip() or None, total=0)
    db.add(compra)
    db.flush()
    total = 0.0
    for e in items:
        p = db.get(m.Producto, int(e["producto_id"]))
        cant, costo = int(e["cantidad"]), float(e["costo_unitario"])
        if not p:
            raise ErrorNegocio("Producto no encontrado en la compra.", 404)
        if cant <= 0:
            raise ErrorNegocio(f"Cantidad no válida para «{p.nombre}».")
        if costo < 0:
            raise ErrorNegocio(f"Costo no válido para «{p.nombre}».")
        inv.aplicar_compra_a_costo(p, cant, costo)
        inv.registrar_movimiento(db, p, "COMPRA", cant, costo_unitario=costo, referencia_tipo="compra",
                                 referencia_id=compra.id, usuario_id=usuario.id)
        db.add(m.CompraItem(compra_id=compra.id, producto_id=p.id, cantidad=cant, costo_unitario=costo))
        total += cant * costo
        nuevo = e.get("nuevo_precio")
        if nuevo not in (None, "", 0) and int(nuevo) != p.precio_venta:
            cambiar_precio(db, p, int(nuevo), usuario.id)
    compra.total = round(total, 2)
    auditar(db, usuario.id, "COMPRA", "compra", compra.id, despues={"total": compra.total, "items": len(items)})
    db.flush()
    return compra


def serializar(c: m.Compra, detalle: bool = False) -> dict:
    d = {"id": c.id, "fecha": c.fecha.isoformat(), "proveedor": c.proveedor.nombre if c.proveedor else None,
         "proveedor_id": c.proveedor_id, "numero_factura": c.numero_factura, "total": round(c.total),
         "nota": c.nota, "n_items": len(c.items)}
    if detalle:
        d["items"] = [{"producto_id": i.producto_id, "nombre": i.producto.nombre, "cantidad": i.cantidad,
                       "costo_unitario": round(i.costo_unitario, 2), "subtotal": round(i.cantidad * i.costo_unitario)}
                      for i in c.items]
    return d


def listar(db: Session, desde: date | None = None, hasta: date | None = None, proveedor_id: int | None = None,
           limite: int = 200) -> list[dict]:
    q = select(m.Compra).order_by(m.Compra.id.desc()).limit(limite)
    if desde:
        q = q.where(m.Compra.fecha >= datetime.combine(desde, time.min))
    if hasta:
        q = q.where(m.Compra.fecha < datetime.combine(hasta + timedelta(days=1), time.min))
    if proveedor_id:
        q = q.where(m.Compra.proveedor_id == proveedor_id)
    return [serializar(c) for c in db.scalars(q)]
