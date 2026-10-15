from __future__ import annotations

from datetime import date

from fastapi import APIRouter
from fastapi.responses import Response

from .. import models as m
from ..core import ErrorNegocio, cfg
from ..deps import DB, DBW, Pin, Usuario
from ..schemas import AnularIn, DevolucionIn, SuspenderIn, VentaIn
from ..services import exportacion
from ..services import ventas as svc
from .caja import abrir_cajon

router = APIRouter(prefix="/api")


@router.post("/ventas")
def crear_venta(body: VentaIn, u: Usuario, db: DBW, pin: Pin = None):
    v = svc.crear_venta(db, u, body.model_dump(), pin)
    efectivo = svc.tiene_efectivo(v)
    out = svc.serializar(db, v)
    db.commit()
    cajon = None
    if efectivo:  # mejor esfuerzo: un fallo del cajón nunca deshace ni bloquea la venta
        ok, msg = abrir_cajon(db)
        cajon = {"ok": ok, "mensaje": msg}
    out["cajon"] = cajon
    return out


@router.get("/ventas")
def listar(u: Usuario, db: DB, desde: date | None = None, hasta: date | None = None, turno_id: int | None = None,
           estado: str | None = None, q: str | None = None, limite: int = 200):
    # el cajero solo ve las ventas de su turno abierto
    uid = None
    if u.rol != "admin":
        uid = u.id
        if not (desde or hasta or turno_id or q):
            from ..services import caja as caja_svc
            t = caja_svc.turno_abierto(db)
            turno_id = t.id if t else -1
    return svc.listar(db, desde=desde, hasta=hasta, turno_id=turno_id, estado=estado, q=q, usuario_id=uid, limite=min(limite, 1000))


def _venta_visible(db, u, vid) -> m.Venta:
    v = svc.obtener(db, vid)
    if u.rol != "admin" and v.usuario_id != u.id:
        raise ErrorNegocio("No puede ver ventas de otro cajero.", 403)
    return v


@router.get("/ventas/{vid}")
def obtener(vid: int, u: Usuario, db: DB):
    return svc.serializar(db, _venta_visible(db, u, vid))


@router.get("/ventas/{vid}/recibo")
def recibo(vid: int, u: Usuario, db: DB):
    v = _venta_visible(db, u, vid)
    negocio = {k: cfg(db, k) for k in ("negocio_nombre", "negocio_nit", "negocio_direccion", "negocio_telefono")}
    return Response(exportacion.recibo_pdf(svc.serializar(db, v), negocio), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{v.numero}.pdf"'})


@router.post("/ventas/{vid}/anular")
def anular(vid: int, body: AnularIn, u: Usuario, db: DBW, pin: Pin = None):
    v = svc.anular_venta(db, u, vid, body.motivo, pin)
    out = svc.serializar(db, v)
    db.commit()
    return out


@router.post("/ventas/{vid}/devolucion")
def devolver(vid: int, body: DevolucionIn, u: Usuario, db: DBW, pin: Pin = None):
    d = svc.devolver(db, u, vid, [i.model_dump() for i in body.items], body.medio_reintegro, body.motivo, pin)
    out = {"devolucion_id": d.id, "total": d.total, "medio_reintegro": d.medio_reintegro}
    db.commit()
    if d.medio_reintegro == "efectivo":
        out["cajon"] = abrir_cajon(db)[0]
    return out


# ───────────────────────────── Ventas suspendidas ─────────────────────────────
@router.get("/ventas-suspendidas")
def suspendidas(_: Usuario, db: DB):
    return svc.listar_suspendidas(db)


@router.post("/ventas-suspendidas")
def suspender(body: SuspenderIn, u: Usuario, db: DBW):
    s = svc.suspender(db, u, body.carrito, body.etiqueta)
    db.commit()
    return {"id": s.id}


@router.post("/ventas-suspendidas/{sid}/retomar")
def retomar(sid: int, u: Usuario, db: DBW):
    datos = svc.retomar(db, sid)
    db.commit()
    return datos


@router.delete("/ventas-suspendidas/{sid}")
def descartar(sid: int, u: Usuario, db: DBW):
    svc.retomar(db, sid)
    db.commit()
    return {"ok": True}
