"""Dependencias de FastAPI: sesiones de base de datos, usuario actual, administrador y PIN de autorización."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from . import db as db_mod
from . import models as m
from .core import ErrorNegocio, usuario_por_token

DB = Annotated[Session, Depends(db_mod.get_db)]
DBW = Annotated[Session, Depends(db_mod.get_db_w)]
Pin = Annotated[str | None, Header(alias="X-Autorizacion-Pin")]


def _token(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def usuario_actual(authorization: Annotated[str | None, Header()] = None) -> m.Usuario:
    token = _token(authorization)
    if not token:
        raise ErrorNegocio("Inicie sesión para continuar.", 401, "NO_AUTENTICADO")
    s = db_mod.nueva_sesion()  # sesión corta: no deja una lectura abierta durante toda la petición
    try:
        u = usuario_por_token(s, token)
    finally:
        s.close()
    if not u:
        raise ErrorNegocio("La sesión expiró. Inicie sesión de nuevo.", 401, "NO_AUTENTICADO")
    return u


def admin_requerido(u: Annotated[m.Usuario, Depends(usuario_actual)]) -> m.Usuario:
    if u.rol != "admin":
        raise ErrorNegocio("Esta acción es solo para el administrador.", 403, "SOLO_ADMIN")
    return u


Usuario = Annotated[m.Usuario, Depends(usuario_actual)]
Admin = Annotated[m.Usuario, Depends(admin_requerido)]
