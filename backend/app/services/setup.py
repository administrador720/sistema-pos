"""Configuración inicial: crea el primer administrador y los catálogos base."""
from __future__ import annotations

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m
from ..core import ErrorNegocio, ahora, auditar, cfg_set, hashear


def configurado(db: Session) -> bool:
    return (db.scalar(select(func.count()).select_from(m.Usuario)) or 0) > 0


def validar_pin(pin: str):
    if not re.fullmatch(r"\d{4,6}", pin or ""):
        raise ErrorNegocio("El PIN debe tener entre 4 y 6 números.")


def validar_password(pw: str):
    if len(pw or "") < 6:
        raise ErrorNegocio("La contraseña debe tener al menos 6 caracteres.")


def crear_catalogos_base(db: Session):
    if not db.scalar(select(func.count()).select_from(m.Impuesto)):
        db.add_all([
            m.Impuesto(nombre="IVA 19%", tipo="IVA", tarifa_pct=19),
            m.Impuesto(nombre="IVA 5%", tipo="IVA", tarifa_pct=5),
            m.Impuesto(nombre="Exento (0%)", tipo="IVA", tarifa_pct=0),
            m.Impuesto(nombre="Excluido", tipo="IVA", tarifa_pct=0),
        ])
    if not db.scalar(select(func.count()).select_from(m.MedioPago)):
        db.add_all([
            m.MedioPago(nombre="Efectivo", tipo="efectivo", orden=1),
            m.MedioPago(nombre="Tarjeta débito", tipo="banco", orden=2),
            m.MedioPago(nombre="Tarjeta crédito", tipo="banco", orden=3),
            m.MedioPago(nombre="Transferencia / QR", tipo="banco", requiere_referencia=False, orden=4),
        ])
    if not db.scalar(select(func.count()).select_from(m.Categoria)):
        db.add(m.Categoria(nombre="General"))
    if not db.scalar(select(func.count()).select_from(m.Caja)):
        db.add(m.Caja(nombre="Caja 1"))


def primera_configuracion(db: Session, *, negocio: dict, admin: dict) -> m.Usuario:
    if configurado(db):
        raise ErrorNegocio("El sistema ya está configurado.", 409)
    validar_password(admin.get("password", ""))
    validar_pin(admin.get("pin", ""))
    usuario = (admin.get("usuario") or "").strip().lower()
    if not usuario or not (admin.get("nombre") or "").strip():
        raise ErrorNegocio("Indique el nombre y el usuario del administrador.")
    u = m.Usuario(nombre=admin["nombre"].strip(), usuario=usuario, hash_password=hashear(admin["password"]),
                  hash_pin=hashear(admin["pin"]), rol="admin", activo=True, creado_en=ahora())
    db.add(u)
    for campo in ("nombre", "nit", "direccion", "telefono"):
        if negocio.get(campo):
            cfg_set(db, f"negocio_{campo}", negocio[campo].strip())
    crear_catalogos_base(db)
    db.flush()
    auditar(db, u.id, "CONFIGURACION_INICIAL", "usuario", u.id)
    return u
