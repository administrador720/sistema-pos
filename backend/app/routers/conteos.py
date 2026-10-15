"""Tomas de inventario físico. La captura la puede hacer cualquier usuario (siempre a ciegas);
la revisión, los ajustes y la programación son del administrador."""
from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import Response
from sqlalchemy import select

from .. import models as m
from ..core import ErrorNegocio, cfg, hoy
from ..deps import DB, DBW, Admin, Usuario
from ..schemas import AplicarConteoIn, CapturaIn, ConteoIn, ProgramacionIn, RecontarIn
from ..services import conteos as svc
from ..services import exportacion

router = APIRouter(prefix="/api/conteos")


@router.get("")
def listar(u: Usuario, db: DB):
    lista = svc.listar(db)
    if u.rol != "admin":  # el cajero solo ve el conteo que está en captura
        lista = [c for c in lista if c["estado"] == "en_conteo"]
    return lista


@router.get("/programaciones")
def programaciones(_: Admin, db: DB):
    return [svc.serializar_programacion(p) for p in db.scalars(select(m.ProgramacionConteo).order_by(m.ProgramacionConteo.proxima_fecha))]


@router.post("/programaciones")
def crear_programacion(body: ProgramacionIn, _: Admin, db: DBW):
    p = svc.guardar_programacion(db, body.model_dump())
    db.commit()
    return svc.serializar_programacion(p)


@router.put("/programaciones/{pid}")
def editar_programacion(pid: int, body: ProgramacionIn, _: Admin, db: DBW):
    p = db.get(m.ProgramacionConteo, pid)
    if not p:
        raise ErrorNegocio("Programación no encontrada.", 404)
    svc.guardar_programacion(db, body.model_dump(), p)
    db.commit()
    return svc.serializar_programacion(p)


@router.delete("/programaciones/{pid}")
def borrar_programacion(pid: int, _: Admin, db: DBW):
    p = db.get(m.ProgramacionConteo, pid)
    if p:
        for c in db.scalars(select(m.Conteo).where(m.Conteo.programacion_id == pid)):
            c.programacion_id = None
        db.delete(p)
        db.commit()
    return {"ok": True}


@router.post("/programaciones/{pid}/iniciar")
def iniciar_programado(pid: int, adm: Admin, db: DBW):
    """El administrador decide cuándo hacer el conteo programado: crea e inicia el conteo."""
    p = db.get(m.ProgramacionConteo, pid)
    if not p:
        raise ErrorNegocio("Programación no encontrada.", 404)
    c = svc.crear(db, adm, nombre=f"{p.nombre} — {hoy():%d/%m/%Y}", tipo=p.tipo,
                  alcance=json.loads(p.alcance or "{}"), programacion_id=p.id)
    svc.iniciar(db, adm, c.id)
    db.commit()
    return svc.serializar(c)


@router.post("")
def crear(body: ConteoIn, adm: Admin, db: DBW):
    c = svc.crear(db, adm, nombre=body.nombre, tipo=body.tipo, alcance=body.alcance, programacion_id=body.programacion_id)
    db.commit()
    return svc.serializar(c)


@router.get("/{cid}")
def obtener(cid: int, u: Usuario, db: DB):
    c = db.get(m.Conteo, cid)
    if not c:
        raise ErrorNegocio("Conteo no encontrado.", 404)
    out = svc.serializar(c)
    out["progreso"] = svc.progreso(db, cid)
    return out


@router.post("/{cid}/iniciar")
def iniciar(cid: int, adm: Admin, db: DBW):
    c = svc.iniciar(db, adm, cid)
    db.commit()
    return svc.serializar(c)


@router.post("/{cid}/capturas")
def capturar(cid: int, body: CapturaIn, u: Usuario, db: DBW):
    r = svc.capturar(db, u, cid, codigo=body.codigo, producto_id=body.producto_id, cantidad=body.cantidad,
                     ubicacion=body.ubicacion)
    db.commit()
    return r


@router.get("/{cid}/capturas")
def capturas(cid: int, u: Usuario, db: DB):
    return svc.listar_capturas(db, cid)


@router.delete("/{cid}/capturas/{capid}")
def borrar_captura(cid: int, capid: int, u: Usuario, db: DBW):
    svc.eliminar_captura(db, cid, capid)
    db.commit()
    return {"ok": True}


@router.post("/{cid}/cerrar-captura")
def cerrar_captura(cid: int, adm: Admin, db: DBW):
    c = svc.cerrar_captura(db, adm, cid)
    db.commit()
    return svc.serializar(c)


@router.get("/{cid}/revision")
def revision(cid: int, _: Admin, db: DB):
    return svc.revision(db, cid)


@router.post("/{cid}/reconteo")
def reconteo(cid: int, body: RecontarIn, adm: Admin, db: DBW):
    c = svc.reconteo(db, adm, cid, body.producto_ids)
    db.commit()
    return svc.serializar(c)


@router.post("/{cid}/aplicar")
def aplicar(cid: int, body: AplicarConteoIn, adm: Admin, db: DBW):
    c = svc.aplicar(db, adm, cid, body.asumir_cero_no_contados)
    out = svc.serializar(c)
    db.commit()
    return out


@router.post("/{cid}/cancelar")
def cancelar(cid: int, adm: Admin, db: DBW):
    c = svc.cancelar(db, adm, cid)
    db.commit()
    return svc.serializar(c)


@router.get("/{cid}/informe")
def informe(cid: int, _: Admin, db: DB, formato: str = "pdf"):
    t = svc.informe_tabla(db, cid)
    negocio = cfg(db, "negocio_nombre")
    if formato == "xlsx":
        return Response(exportacion.a_xlsx(t, negocio), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="conteo-{cid}.xlsx"'})
    return Response(exportacion.a_pdf(t, negocio), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="conteo-{cid}.pdf"'})
