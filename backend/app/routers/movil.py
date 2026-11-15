"""Celulares: activar el acceso desde la red local, vincular (código/QR) y desvincular."""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from .. import config
from ..core import ErrorNegocio, auditar, cfg, cfg_set
from ..deps import DB, DBW, Admin
from ..services import movil as svc

router = APIRouter(prefix="/api/movil")
URL_APK = f"https://github.com/{config.REPO_ACTUALIZACIONES}/releases/latest"


def _solo_computador(request: Request):
    """Activar, vincular y desvincular celulares solo se hace sentado frente al computador."""
    if getattr(request.state, "movil", False):
        raise ErrorNegocio("Esto solo se puede hacer desde el computador.", 403, "SOLO_EN_EL_COMPUTADOR")


class VincularIn(BaseModel):
    codigo: str
    nombre: str = ""


class HabilitarIn(BaseModel):
    habilitado: bool


@router.get("/info")
def info(db: DB):
    """Público (sin llave): sirve para comprobar la conexión y que la app sepa si es compatible."""
    return {"ok": True, "negocio": cfg(db, "negocio_nombre"), "version": config.VERSION, "api": config.API_MOVIL}


@router.post("/vincular")
def vincular(body: VincularIn, request: Request, db: DBW):
    ip = request.client.host if request.client else "?"
    token, d = svc.vincular(db, body.codigo, body.nombre, ip)
    out = {"token": token, "dispositivo": {"id": d.id, "nombre": d.nombre}, "negocio": cfg(db, "negocio_nombre"),
           "version": config.VERSION, "api": config.API_MOVIL}
    db.commit()
    return out


@router.get("/estado")
def estado(request: Request, _: Admin, db: DB):
    _solo_computador(request)
    return {"habilitado": svc.habilitado(db), "activo": svc.servidor.activo, "puerto": config.PUERTO_MOVIL,
            "direcciones": svc.direcciones_locales(), "error": svc.servidor.error, "url_apk": URL_APK, "version": config.VERSION,
            "dispositivos": svc.listar(db)}


@router.post("/habilitar")
def habilitar(body: HabilitarIn, request: Request, adm: Admin, db: DBW):
    _solo_computador(request)
    if body.habilitado:
        svc.servidor.iniciar(request.app)        # si el puerto está ocupado, falla antes de guardar nada
    else:
        svc.servidor.detener()
    cfg_set(db, "acceso_movil", "1" if body.habilitado else "0")
    auditar(db, adm.id, "MOVIL_ACTIVADO" if body.habilitado else "MOVIL_APAGADO", "configuracion")
    db.commit()
    return {"habilitado": body.habilitado, "activo": svc.servidor.activo}


@router.post("/codigo")
def codigo(request: Request, adm: Admin, db: DB):
    _solo_computador(request)
    if not svc.habilitado(db):
        raise ErrorNegocio("Primero active el acceso desde celulares.", 409, "MOVIL_APAGADO")
    dirs = svc.direcciones_locales()
    if not dirs:
        raise ErrorNegocio("Este computador no está conectado a una red local (Wi-Fi o cable).", 409, "SIN_RED")
    c = svc.nuevo_codigo()
    negocio = cfg(db, "negocio_nombre")
    return {**c, "direcciones": dirs, "puerto": config.PUERTO_MOVIL, "url": f"http://{dirs[0]}:{config.PUERTO_MOVIL}",
            "qrs": [{"direccion": d, "svg": svc.qr_svg(svc.contenido_qr(d, c["codigo"], negocio))} for d in dirs[:3]]}


@router.delete("/dispositivos/{did}")
def desvincular(did: int, request: Request, adm: Admin, db: DBW):
    _solo_computador(request)
    svc.revocar(db, adm, did)
    db.commit()
    return {"ok": True}
