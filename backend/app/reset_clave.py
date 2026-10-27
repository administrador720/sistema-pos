"""Restablece la contraseña (y, si se quiere, el PIN) de un usuario, desde este mismo computador.

    restablecer_clave.bat          (Windows: doble clic)
    python -m app.reset_clave      lista los usuarios y pregunta cuál restablecer
    python -m app.reset_clave admin

Pensado para cuando el administrador olvida su clave y no hay otro administrador que pueda cambiársela
(Configuración → Usuarios). Hay que tener acceso a este computador. Queda registrado en la auditoría,
reactiva la cuenta si estaba inactiva y cierra las sesiones abiertas de ese usuario.
"""
from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config, core, db as db_mod
from . import models as m
from .core import ErrorNegocio
from .services import setup as setup_svc


def restablecer(db: Session, usuario: str, password: str, pin: str | None = None) -> m.Usuario:
    """Cambia la contraseña de `usuario` (y el PIN si se indica). No confirma: lo hace quien llama."""
    u = db.scalars(select(m.Usuario).where(m.Usuario.usuario == (usuario or "").strip().lower())).first()
    if not u:
        raise ErrorNegocio(f"No existe el usuario «{usuario}».", 404)
    setup_svc.validar_password(password)
    if pin:
        setup_svc.validar_pin(pin)
    elif u.rol == "admin" and not u.hash_pin:
        raise ErrorNegocio("Un administrador necesita un PIN de 4 a 6 números.")
    u.hash_password = core.hashear(password)
    if pin:
        u.hash_pin = core.hashear(pin)
    reactivado = not u.activo
    u.activo = True
    for s in db.scalars(select(m.Sesion).where(m.Sesion.usuario_id == u.id)):
        db.delete(s)
    core.auditar(db, u.id, "CLAVE_RESTABLECIDA", "usuario", u.id,
                 despues={"origen": "herramienta local", "reactivado": reactivado, "pin_cambiado": bool(pin)})
    db.flush()
    return u


def _pedir_clave(etiqueta: str, repetir: bool = True) -> str:
    while True:
        a = getpass.getpass(f"{etiqueta}: ")
        if not repetir or a == getpass.getpass("Repítala para confirmar: "):
            return a
        print("No coinciden. Intente de nuevo.\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Restablecer la contraseña de un usuario del POS")
    ap.add_argument("usuario", nargs="?", help="usuario para ingresar (no el nombre); si se omite, se pregunta")
    a = ap.parse_args(argv)

    ruta = config.ruta_db()
    if not ruta.exists():
        print(f"No se encontró la base de datos en {ruta}.\nSi todavía no ha configurado el sistema, no hay nada que restablecer.")
        return 1
    db_mod.configurar()
    db_mod.inicializar()

    s = db_mod.nueva_sesion()
    try:
        usuarios = list(s.scalars(select(m.Usuario).order_by(m.Usuario.id)))
    finally:
        s.close()
    print(f"\nBase de datos: {ruta}\n")
    print(f"  {'USUARIO':<18}{'NOMBRE':<28}{'ROL':<15}ESTADO")
    for u in usuarios:
        print(f"  {u.usuario:<18}{u.nombre:<28}{('Administrador' if u.rol == 'admin' else 'Cajero'):<15}{'activo' if u.activo else 'INACTIVO'}")
    print("\n  (Para ingresar se usa la columna USUARIO, no el nombre.)\n")

    usuario = a.usuario or input("Usuario a restablecer: ").strip()
    if not usuario:
        return 1
    try:
        password = _pedir_clave("Nueva contraseña (mínimo 6 caracteres)")
        pin = getpass.getpass("Nuevo PIN de 4 a 6 números (Enter para no cambiarlo): ").strip() or None
        w = db_mod.nueva_sesion(escritura=True)
        try:
            u = restablecer(w, usuario, password, pin)
            w.commit()
        finally:
            w.close()
    except ErrorNegocio as e:
        print(f"\nNo se pudo: {e.detalle}")
        return 1
    print(f"\nListo. Ya puede ingresar con el usuario «{u.usuario}» y la nueva contraseña.")
    print("Si el programa estaba abierto y se bloqueó por intentos fallidos, espere 5 minutos o ciérrelo y ábralo de nuevo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
