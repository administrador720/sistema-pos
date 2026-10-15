"""Inventario: alertas, kardex, mermas, ajustes y compras."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter

from ..core import ErrorNegocio
from ..deps import DB, DBW, Admin
from ..schemas import AjusteIn, CompraIn, MermaIn
from ..services import compras as compras_svc
from ..services import inventario as svc

router = APIRouter(prefix="/api")


@router.get("/inventario/alertas")
def alertas(_: Admin, db: DB):
    return svc.alertas(db)


@router.get("/inventario/kardex")
def kardex(_: Admin, db: DB, producto_id: int, desde: date | None = None, hasta: date | None = None):
    return svc.kardex(db, producto_id, desde, hasta)


@router.get("/inventario/motivos-merma")
def motivos(_: Admin):
    return [{"codigo": k, "nombre": v} for k, v in svc.MOTIVOS_MERMA.items()]


@router.post("/inventario/mermas")
def merma(body: MermaIn, adm: Admin, db: DBW):
    mov = svc.registrar_merma(db, adm, body.producto_id, body.cantidad, body.motivo, body.nota)
    db.commit()
    return {"id": mov.id, "stock_resultante": mov.stock_resultante}


@router.post("/inventario/ajustes")
def ajuste(body: AjusteIn, adm: Admin, db: DBW):
    mov = svc.ajustar_stock(db, adm, body.producto_id, nuevo_stock=body.nuevo_stock, delta=body.delta, nota=body.nota)
    db.commit()
    return {"id": mov.id if mov else None, "stock_resultante": mov.stock_resultante if mov else None}


@router.get("/compras")
def listar_compras(_: Admin, db: DB, desde: date | None = None, hasta: date | None = None,
                   proveedor_id: int | None = None):
    return compras_svc.listar(db, desde, hasta, proveedor_id)


@router.get("/compras/{cid}")
def obtener_compra(cid: int, _: Admin, db: DB):
    from .. import models as m
    c = db.get(m.Compra, cid)
    if not c:
        raise ErrorNegocio("Compra no encontrada.", 404)
    return compras_svc.serializar(c, detalle=True)


@router.post("/compras")
def crear_compra(body: CompraIn, adm: Admin, db: DBW):
    c = compras_svc.crear_compra(db, adm, body.model_dump())
    out = compras_svc.serializar(c, detalle=True)
    db.commit()
    return out
