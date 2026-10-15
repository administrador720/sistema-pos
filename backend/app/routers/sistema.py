"""Respaldos y auditoría."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select

from .. import config
from .. import db as db_mod
from .. import models as m
from ..core import ErrorNegocio
from ..deps import DB, DBW, Admin
from ..schemas import RestaurarIn
from ..services import respaldos as svc

router = APIRouter(prefix="/api")


@router.get("/respaldos")
def listar(_: Admin, db: DB):
    return {"estado": svc.estado(db), "respaldos": svc.listar(db)}


@router.post("/respaldos")
def crear(adm: Admin, db: DBW):
    r = svc.crear_respaldo(db, "manual", adm.id)
    db.commit()
    return r


@router.get("/respaldos/{archivo}/descargar")
def descargar(archivo: str, _: Admin):
    ruta = config.dir_respaldos() / archivo
    if not ruta.exists() or ruta.parent != config.dir_respaldos() or not archivo.startswith("pos-"):
        raise ErrorNegocio("El respaldo no existe.", 404)
    return FileResponse(ruta, filename=archivo, media_type="application/gzip")


@router.post("/respaldos/restaurar")
def restaurar(body: RestaurarIn, adm: Admin):
    s = db_mod.nueva_sesion(escritura=True)
    try:
        previo = svc.restaurar(s, adm, body.archivo, body.password)
    finally:
        s.close()
    return {"ok": True, "respaldo_previo": previo,
            "mensaje": "Respaldo restaurado. Se guardó una copia de lo anterior; vuelva a iniciar sesión."}


@router.get("/auditoria")
def auditoria(_: Admin, db: DB, desde: date | None = None, hasta: date | None = None, accion: str | None = None,
              limite: int = 300):
    q = select(m.Auditoria).order_by(m.Auditoria.id.desc()).limit(min(limite, 2000))
    if desde:
        q = q.where(m.Auditoria.fecha >= datetime.combine(desde, time.min))
    if hasta:
        q = q.where(m.Auditoria.fecha < datetime.combine(hasta + timedelta(days=1), time.min))
    if accion:
        q = q.where(m.Auditoria.accion == accion)
    nombres = {u.id: u.nombre for u in db.scalars(select(m.Usuario))}
    acciones = [a for (a,) in db.execute(select(m.Auditoria.accion).distinct().order_by(m.Auditoria.accion))]
    return {"acciones": acciones, "filas": [{
        "id": a.id, "fecha": a.fecha.isoformat(), "usuario": nombres.get(a.usuario_id), "accion": a.accion,
        "entidad": a.entidad, "entidad_id": a.entidad_id, "autorizado_por": nombres.get(a.autorizado_por),
        "antes": json.loads(a.datos_antes) if a.datos_antes else None,
        "despues": json.loads(a.datos_despues) if a.datos_despues else None} for a in db.scalars(q)]}


class AbrirIn(BaseModel):
    ruta: str


@router.post("/sistema/abrir")
def abrir_exportado(body: AbrirIn, _: Admin):
    """Abre un archivo exportado con el programa predeterminado (Excel, visor de PDF).
    Solo permite archivos dentro de la carpeta de exportes."""
    base = config.dir_exportes().resolve()
    ruta = Path(body.ruta).resolve()
    if base not in ruta.parents or not ruta.is_file():
        raise ErrorNegocio("Archivo no permitido.", 403)
    try:
        if sys.platform == "win32":
            os.startfile(str(ruta))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(ruta)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return {"ok": False}
    return {"ok": True}
