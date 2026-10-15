"""Configuración inicial, inicio de sesión, autorización por PIN y usuarios."""
from __future__ import annotations

from fastapi import APIRouter, Header
from sqlalchemy import func, select

from .. import config
from .. import models as m
from ..core import (ErrorNegocio, ahora, auditar, autorizar, cerrar_sesion, crear_sesion, hashear, limitador,
                    verificar_hash)
from ..deps import DB, DBW, Admin, Pin, Usuario
from ..schemas import CredencialesIn, LoginIn, PinIn, SecretoIn, SetupIn, UsuarioIn
from ..services import setup as setup_svc

router = APIRouter(prefix="/api")


def usuario_dict(u: m.Usuario) -> dict:
    return {"id": u.id, "nombre": u.nombre, "usuario": u.usuario, "rol": u.rol, "activo": u.activo,
            "tiene_pin": bool(u.hash_pin)}


@router.get("/salud")
def salud():
    return {"ok": True, "version": config.VERSION}


@router.get("/setup/estado")
def setup_estado(db: DB):
    return {"configurado": setup_svc.configurado(db), "version": config.VERSION}


@router.post("/setup")
def setup(body: SetupIn, db: DBW):
    u = setup_svc.primera_configuracion(db, negocio=body.negocio.model_dump(), admin=body.admin.model_dump())
    token = crear_sesion(db, u)
    db.commit()
    return {"token": token, "usuario": usuario_dict(u)}


@router.post("/auth/login")
def login(body: LoginIn, db: DBW):
    clave = f"login:{body.usuario.strip().lower()}"
    limitador.revisar(clave)
    u = db.scalars(select(m.Usuario).where(m.Usuario.usuario == body.usuario.strip().lower())).first()
    if not u or not u.activo or not verificar_hash(u.hash_password, body.password):
        limitador.fallo(clave)
        raise ErrorNegocio("Usuario o contraseña incorrectos.", 401, "CREDENCIALES")
    limitador.exito(clave)
    token = crear_sesion(db, u)
    db.commit()
    return {"token": token, "usuario": usuario_dict(u)}


@router.post("/auth/logout")
def logout(db: DBW, authorization: str | None = Header(None)):
    if authorization and authorization.lower().startswith("bearer "):
        cerrar_sesion(db, authorization[7:].strip())
        db.commit()
    return {"ok": True}


@router.get("/auth/yo")
def yo(u: Usuario):
    return usuario_dict(u)


@router.post("/auth/verificar")
def verificar(body: SecretoIn, u: Usuario, db: DB):
    """Desbloqueo de pantalla: acepta la contraseña o el PIN del usuario que tiene la sesión abierta."""
    clave = f"verificar:{u.id}"
    limitador.revisar(clave)
    if verificar_hash(u.hash_pin, body.secreto) or verificar_hash(u.hash_password, body.secreto):
        limitador.exito(clave)
        return {"ok": True}
    limitador.fallo(clave)
    raise ErrorNegocio("PIN o contraseña incorrectos.", 403, "VERIFICACION_FALLIDA")


@router.post("/auth/autorizar")
def autorizar_accion(body: PinIn, u: Usuario, db: DBW):
    """Valida el PIN de un administrador para una acción sensible que el cliente va a reintentar."""
    adm = autorizar(db, u, body.pin, "Se requiere el PIN del administrador.")
    auditar(db, u.id, "AUTORIZACION", "usuario", adm.id, autorizado_por=adm.id)
    db.commit()
    return {"ok": True, "autorizado_por": adm.nombre}


@router.put("/auth/credenciales")
def cambiar_credenciales(body: CredencialesIn, u: Usuario, db: DBW):
    usuario = db.get(m.Usuario, u.id)
    if not verificar_hash(usuario.hash_password, body.password_actual):
        raise ErrorNegocio("La contraseña actual no es correcta.", 403)
    if body.password_nueva:
        setup_svc.validar_password(body.password_nueva)
        usuario.hash_password = hashear(body.password_nueva)
    if body.pin_nuevo:
        setup_svc.validar_pin(body.pin_nuevo)
        usuario.hash_pin = hashear(body.pin_nuevo)
    auditar(db, u.id, "CAMBIO_CREDENCIALES", "usuario", u.id)
    db.commit()
    return {"ok": True}


# ───────────────────────────── Usuarios (administrador) ─────────────────────────────
@router.get("/usuarios")
def listar_usuarios(_: Admin, db: DB):
    return [usuario_dict(u) for u in db.scalars(select(m.Usuario).order_by(m.Usuario.nombre))]


def _admins_activos(db, excluir_id: int | None = None) -> int:
    q = select(func.count()).select_from(m.Usuario).where(m.Usuario.rol == "admin", m.Usuario.activo.is_(True))
    if excluir_id:
        q = q.where(m.Usuario.id != excluir_id)
    return db.scalar(q) or 0


@router.post("/usuarios")
def crear_usuario(body: UsuarioIn, adm: Admin, db: DBW):
    if not (body.nombre and body.usuario and body.password):
        raise ErrorNegocio("Complete nombre, usuario y contraseña.")
    login_ = body.usuario.strip().lower()
    if db.scalar(select(m.Usuario.id).where(m.Usuario.usuario == login_)):
        raise ErrorNegocio("Ya existe un usuario con ese nombre de usuario.", 409)
    if (body.rol or "cajero") not in ("admin", "cajero"):
        raise ErrorNegocio("Rol no válido.")
    setup_svc.validar_password(body.password)
    if body.pin:
        setup_svc.validar_pin(body.pin)
    elif (body.rol or "cajero") == "admin":
        raise ErrorNegocio("Un administrador necesita un PIN de 4 a 6 números.")
    u = m.Usuario(nombre=body.nombre.strip(), usuario=login_, hash_password=hashear(body.password),
                  hash_pin=hashear(body.pin) if body.pin else None, rol=body.rol or "cajero", activo=True, creado_en=ahora())
    db.add(u)
    db.flush()
    auditar(db, adm.id, "USUARIO_CREADO", "usuario", u.id, despues={"usuario": u.usuario, "rol": u.rol})
    db.commit()
    return usuario_dict(u)


@router.put("/usuarios/{uid}")
def editar_usuario(uid: int, body: UsuarioIn, adm: Admin, db: DBW):
    u = db.get(m.Usuario, uid)
    if not u:
        raise ErrorNegocio("Usuario no encontrado.", 404)
    if body.nombre:
        u.nombre = body.nombre.strip()
    if body.password:
        setup_svc.validar_password(body.password)
        u.hash_password = hashear(body.password)
    if body.pin:
        setup_svc.validar_pin(body.pin)
        u.hash_pin = hashear(body.pin)
    nuevo_rol = body.rol or u.rol
    if nuevo_rol not in ("admin", "cajero"):
        raise ErrorNegocio("Rol no válido.")
    activo = u.activo if body.activo is None else body.activo
    if u.rol == "admin" and (nuevo_rol != "admin" or not activo) and _admins_activos(db, excluir_id=u.id) == 0:
        raise ErrorNegocio("Debe quedar al menos un administrador activo.", 409)
    if nuevo_rol == "admin" and not u.hash_pin:
        raise ErrorNegocio("Un administrador necesita un PIN de 4 a 6 números.")
    u.rol, u.activo = nuevo_rol, activo
    if not activo:  # cierra sus sesiones abiertas
        for s in db.scalars(select(m.Sesion).where(m.Sesion.usuario_id == u.id)):
            db.delete(s)
    auditar(db, adm.id, "USUARIO_EDITADO", "usuario", u.id, despues={"rol": u.rol, "activo": u.activo})
    db.commit()
    return usuario_dict(u)
