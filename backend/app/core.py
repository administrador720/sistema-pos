"""Utilidades compartidas: errores, reloj, dinero/impuestos, contraseñas, sesiones, configuración, auditoría."""
from __future__ import annotations

import hashlib
import json
import math
import secrets
import threading
import time
from datetime import date, datetime

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m


# ───────────────────────────── Errores ─────────────────────────────
class ErrorNegocio(Exception):
    """Error de regla de negocio; el handler de FastAPI lo traduce a JSON {detalle, codigo}."""

    def __init__(self, detalle: str, status: int = 400, codigo: str | None = None):
        super().__init__(detalle)
        self.detalle = detalle
        self.status = status
        self.codigo = codigo


class RequiereAutorizacion(ErrorNegocio):
    def __init__(self, detalle: str):
        super().__init__(detalle, status=403, codigo="REQUIERE_AUTORIZACION")


# ───────────────────────────── Reloj ─────────────────────────────
reloj = datetime.now  # los tests y la carga demo lo reemplazan


def ahora() -> datetime:
    return reloj()


def hoy() -> date:
    return ahora().date()


# ───────────────────────────── Dinero e impuestos ─────────────────────────────
def redondear(x: float) -> int:
    """Redondeo comercial (mitad hacia arriba, simétrico para negativos)."""
    return int(math.floor(abs(x) + 0.5)) * (1 if x >= 0 else -1)


def desglosar_impuesto(total: int, cantidad: int, tarifa_pct: float, valor_fijo: int) -> int:
    """Impuesto contenido en `total` (el precio ya incluye el impuesto). Devuelve el valor del impuesto."""
    if total <= 0:
        return 0
    if valor_fijo and valor_fijo > 0:
        return min(total, valor_fijo * cantidad)
    if tarifa_pct and tarifa_pct > 0:
        base = redondear(total / (1 + tarifa_pct / 100.0))
        return total - base
    return 0


def prorratear(monto: int, pesos: list[int]) -> list[int]:
    """Reparte `monto` en proporción a `pesos` (método del mayor resto); la suma es exacta
    y ninguna parte supera su peso."""
    total = sum(pesos)
    if monto <= 0 or total <= 0:
        return [0] * len(pesos)
    monto = min(monto, total)
    brutos = [monto * p / total for p in pesos]
    base = [int(math.floor(b)) for b in brutos]
    resto = monto - sum(base)
    orden = sorted(range(len(pesos)), key=lambda i: brutos[i] - base[i], reverse=True)
    for i in orden:
        if resto <= 0:
            break
        if base[i] < pesos[i]:
            base[i] += 1
            resto -= 1
    return base


# ───────────────────────────── Contraseñas y PIN ─────────────────────────────
_ph = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)


def hashear(secreto: str) -> str:
    return _ph.hash(secreto)


def verificar_hash(hash_: str | None, secreto: str) -> bool:
    if not hash_:
        return False
    try:
        return _ph.verify(hash_, secreto)
    except (VerificationError, InvalidHashError):
        return False


class _Limitador:
    """Bloquea temporalmente tras varios intentos fallidos (contraseña o PIN)."""

    def __init__(self, maximo: int = 5, ventana: int = 300):
        self.maximo, self.ventana = maximo, ventana
        self.fallos: dict[str, list[float]] = {}
        self.lock = threading.Lock()

    def _limpiar(self, clave: str) -> list[float]:
        t = time.monotonic()
        lista = [x for x in self.fallos.get(clave, []) if t - x < self.ventana]
        self.fallos[clave] = lista
        return lista

    def revisar(self, clave: str):
        with self.lock:
            if len(self._limpiar(clave)) >= self.maximo:
                raise ErrorNegocio("Demasiados intentos fallidos. Espere unos minutos e intente de nuevo.",
                                   429, "BLOQUEADO")

    def fallo(self, clave: str):
        with self.lock:
            self._limpiar(clave).append(time.monotonic())

    def exito(self, clave: str):
        with self.lock:
            self.fallos.pop(clave, None)

    def reiniciar(self):
        with self.lock:
            self.fallos.clear()


limitador = _Limitador()


# ───────────────────────────── Sesiones ─────────────────────────────
def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def crear_sesion(db: Session, usuario: m.Usuario) -> str:
    token = secrets.token_urlsafe(32)
    db.add(m.Sesion(token_hash=_hash_token(token), usuario_id=usuario.id, creado_en=ahora()))
    return token


def usuario_por_token(db: Session, token: str) -> m.Usuario | None:
    s = db.get(m.Sesion, _hash_token(token))
    if not s:
        return None
    if (ahora() - s.creado_en).days >= 7:
        return None
    u = db.get(m.Usuario, s.usuario_id)
    return u if u and u.activo else None


def cerrar_sesion(db: Session, token: str):
    s = db.get(m.Sesion, _hash_token(token))
    if s:
        db.delete(s)


# ───────────────────────────── Autorización de acciones sensibles ─────────────────────────────
def autorizar(db: Session, usuario: m.Usuario, pin: str | None, detalle: str) -> m.Usuario:
    """Un administrador se autoriza a sí mismo; un cajero necesita el PIN de un administrador.
    Devuelve el usuario que autoriza."""
    if usuario.rol == "admin":
        return usuario
    if not pin:
        raise RequiereAutorizacion(detalle)
    limitador.revisar("pin-admin")
    for adm in db.scalars(select(m.Usuario).where(m.Usuario.rol == "admin", m.Usuario.activo.is_(True))):
        if verificar_hash(adm.hash_pin, pin):
            limitador.exito("pin-admin")
            return adm
    limitador.fallo("pin-admin")
    raise ErrorNegocio("PIN de administrador incorrecto.", 403, "PIN_INCORRECTO")


# ───────────────────────────── Configuración ─────────────────────────────
DEFECTOS: dict[str, str] = {
    "negocio_nombre": "Mi Supermercado",
    "negocio_nit": "",
    "negocio_direccion": "",
    "negocio_telefono": "",
    "negocio_logo": "",
    "prefijo_venta": "POS",
    "consecutivo_venta": "1",
    "permitir_stock_negativo": "1",
    "descuento_max_pct_cajero": "10",
    "exigir_pin_quitar_linea": "0",
    "retiro_requiere_autorizacion": "1",
    "denominaciones": "100000,50000,20000,10000,5000,2000,1000,500,200,100,50",
    "cajon_modo": "ninguno",  # ninguno | serial | escpos_archivo | escpos_windows
    "cajon_puerto": "",
    "respaldo_hora": "23:30",
    "respaldo_carpeta_externa": "",
    "respaldo_alerta_dias": "7",
    "bloqueo_minutos": "10",
    "dias_cobertura_sugerido": "7",
    "conteo_recordatorio_dias": "3",
    "tema": "claro",
}
# Claves que cualquier usuario autenticado puede leer (el resto solo el administrador)
CLAVES_PUBLICAS = {"negocio_nombre", "negocio_nit", "negocio_direccion", "negocio_telefono", "negocio_logo",
                   "descuento_max_pct_cajero", "exigir_pin_quitar_linea", "retiro_requiere_autorizacion",
                   "denominaciones", "bloqueo_minutos", "tema", "prefijo_venta", "permitir_stock_negativo"}


def cfg(db: Session, clave: str) -> str:
    fila = db.get(m.Configuracion, clave)
    return fila.valor if fila is not None else DEFECTOS.get(clave, "")


def cfg_int(db: Session, clave: str) -> int:
    try:
        return int(float(cfg(db, clave) or 0))
    except ValueError:
        return int(float(DEFECTOS.get(clave, "0") or 0))


def cfg_bool(db: Session, clave: str) -> bool:
    return cfg(db, clave).strip().lower() in ("1", "true", "si", "sí", "yes")


def cfg_set(db: Session, clave: str, valor: str):
    fila = db.get(m.Configuracion, clave)
    if fila is None:
        db.add(m.Configuracion(clave=clave, valor=str(valor)))
    else:
        fila.valor = str(valor)


def denominaciones(db: Session) -> list[int]:
    try:
        d = sorted({int(x) for x in cfg(db, "denominaciones").split(",") if x.strip()}, reverse=True)
    except ValueError:
        d = [int(x) for x in DEFECTOS["denominaciones"].split(",")]
    return d


# ───────────────────────────── Auditoría ─────────────────────────────
def auditar(db: Session, usuario_id: int | None, accion: str, entidad: str | None = None,
            entidad_id: int | None = None, antes=None, despues=None, autorizado_por: int | None = None):
    def _j(x):
        return None if x is None else json.dumps(x, ensure_ascii=False, default=str)

    db.add(m.Auditoria(fecha=ahora(), usuario_id=usuario_id, accion=accion, entidad=entidad,
                       entidad_id=entidad_id, datos_antes=_j(antes), datos_despues=_j(despues),
                       autorizado_por=autorizado_por if autorizado_por != usuario_id else None))
