"""Restablecer la contraseña desde el computador (herramienta local)."""
import getpass

from sqlalchemy import select

from app import core, db as db_mod, models as m, reset_clave
from app.core import ErrorNegocio

import pytest


def _restablecer(usuario, password, pin=None):
    s = db_mod.nueva_sesion(escritura=True)
    try:
        u = reset_clave.restablecer(s, usuario, password, pin)
        s.commit()
        return u
    finally:
        s.close()


def test_restablecer_clave_permite_entrar_y_cierra_sesiones(tienda):
    api = tienda.api
    token_viejo = api.token
    assert api.get("/api/auth/yo").status_code == 200
    _restablecer("admin", "clave-nueva-9")
    assert api.get("/api/auth/yo").status_code == 401                      # la sesión anterior ya no sirve
    api.token = None
    assert api.login("admin", "secreto1").status_code == 401               # la clave vieja no
    core.limitador.reiniciar()
    assert api.login("ADMIN", "clave-nueva-9").status_code == 200          # la nueva sí (el usuario no distingue mayúsculas)
    assert api.ok(api.get("/api/auth/yo"))["rol"] == "admin"
    # quedó en la auditoría
    aud = api.ok(api.get("/api/auditoria?accion=CLAVE_RESTABLECIDA"))["filas"]
    assert aud and aud[0]["despues"]["origen"] == "herramienta local"


def test_restablecer_reactiva_cuentas_inactivas_y_valida_datos(tienda):
    api = tienda.api
    cajero = next(u for u in api.ok(api.get("/api/usuarios")) if u["usuario"] == "carlos")
    api.ok(api.put(f"/api/usuarios/{cajero['id']}", {"activo": False}))
    assert api.login("carlos", "cajero1").status_code == 401
    core.limitador.reiniciar()
    with pytest.raises(ErrorNegocio, match="al menos 6"):
        _restablecer("carlos", "corta")
    with pytest.raises(ErrorNegocio, match="PIN"):
        _restablecer("carlos", "otra-clave-1", pin="12")
    with pytest.raises(ErrorNegocio, match="No existe"):
        _restablecer("fantasma", "otra-clave-1")
    _restablecer("carlos", "otra-clave-1", pin="5555")
    assert api.login("carlos", "otra-clave-1").status_code == 200           # reactivado
    assert api.post("/api/auth/verificar", {"secreto": "5555"}).status_code == 200   # y con PIN nuevo


def test_herramienta_interactiva(tienda, monkeypatch, capsys):
    respuestas = iter(["clave-por-consola", "clave-por-consola", ""])      # clave, repetir, PIN vacío
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": next(respuestas))
    assert reset_clave.main(["admin"]) == 0
    salida = capsys.readouterr().out
    assert "admin" in salida and "Ana Admin" in salida and "Listo" in salida     # lista los usuarios y confirma
    api = tienda.api
    api.token = None
    core.limitador.reiniciar()
    assert api.login("admin", "clave-por-consola").status_code == 200
    assert api.post("/api/auth/verificar", {"secreto": "1234"}).status_code == 200   # el PIN no se tocó


def test_herramienta_sin_base_de_datos(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("POS_DATA_DIR", str(tmp_path / "vacia"))
    assert reset_clave.main(["admin"]) == 1
    assert "No se encontró la base de datos" in capsys.readouterr().out
