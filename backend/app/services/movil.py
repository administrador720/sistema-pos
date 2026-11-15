"""Celulares en la red local: servidor aparte, vinculación con código/QR y control de acceso.

Diseño (la ventana del programa NUNCA se abre a la red):
  · El servidor normal escucha solo en 127.0.0.1.
  · Cuando el administrador activa «Celulares», se levanta un SEGUNDO servidor (mismo programa) en el puerto 8766 de
    todas las interfaces. Las peticiones que llegan por él pasan por `controlar_acceso`: solo red local, solo IP como
    nombre de servidor, y cada petición de la API necesita la llave de un celular vinculado (`X-Dispositivo`).
  · Los celulares solo ven una API reducida (`PERMITIDAS`) y solo entra el administrador.
  · Vincular un celular: el administrador, en el computador, genera un código de 6 dígitos (vale 5 minutos, un solo uso,
    5 intentos) que viaja en un QR junto con la dirección; el celular lo canjea por su llave.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import os
import re
import secrets
import socket
import threading
import time
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import config, db as db_mod
from .. import models as m
from ..core import ErrorNegocio, ahora, auditar, cfg, limitador

log = logging.getLogger("pos.movil")

CODIGO_VIGENCIA_S = 300
MAX_INTENTOS_CODIGO = 5
MAX_DISPOSITIVOS = 10

# Lo único que un celular puede pedir (método, ruta). Anular, devoluciones, respaldos, usuarios, ajustes, actualizar el
# programa, etc. se hacen en el computador.
PERMITIDAS = [(met, re.compile(rx)) for met, rx in [
    ("POST", r"/api/auth/login"), ("POST", r"/api/auth/logout"), ("GET", r"/api/auth/yo"),
    ("GET", r"/api/catalogos"), ("GET", r"/api/config"), ("GET", r"/api/turnos/actual"),
    ("GET", r"/api/productos"), ("GET", r"/api/productos/(codigo/[^/]+|rapidos|\d+)"),
    ("GET", r"/api/compras"), ("POST", r"/api/compras"), ("GET", r"/api/compras/\d+"),
    ("GET", r"/api/conteos"), ("GET", r"/api/conteos/\d+"), ("GET", r"/api/conteos/\d+/capturas"),
    ("POST", r"/api/conteos/\d+/capturas"), ("DELETE", r"/api/conteos/\d+/capturas/\d+"),
    ("GET", r"/api/dashboard"), ("GET", r"/api/inventario/(alertas|kardex)"),
    ("GET", r"/api/ventas"), ("POST", r"/api/ventas"), ("GET", r"/api/ventas/\d+"), ("GET", r"/api/ventas/\d+/recibo"),
]]
PUBLICAS = {"/api/salud", "/api/movil/info", "/api/movil/vincular"}

_reloj = time.time  # las pruebas lo reemplazan
_lock = threading.Lock()
_codigo: dict = {}          # {"codigo", "expira", "intentos"}
_ultimo_registro: dict[int, float] = {}


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ───────────────────────────── Direcciones del computador ─────────────────────────────
def _es_red_local(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return False
    return a.is_private or a.is_loopback or a.is_link_local


def direcciones_locales() -> list[str]:
    """Direcciones IPv4 de red local de este computador (192.168.x.x primero). Con varias tarjetas de red se puede
    fijar la correcta con la variable POS_DIRECCIONES_MOVIL (por ejemplo 192.168.1.20)."""
    forzadas = [x.strip() for x in os.environ.get("POS_DIRECCIONES_MOVIL", "").split(",") if x.strip()]
    if forzadas:
        return forzadas
    ips: set[str] = set()
    try:  # la ruta hacia la red local; UDP no envía nada al «conectar»
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    utiles = [i for i in ips if _es_red_local(i) and not i.startswith(("127.", "169.254."))]
    return sorted(utiles, key=lambda i: (not i.startswith("192.168."), not i.startswith("10."), i))


# ───────────────────────────── Servidor para la red local ─────────────────────────────
class ServidorMovil:
    def __init__(self):
        self._servidor = None
        self._hilo: threading.Thread | None = None
        self.error: str | None = None

    @property
    def activo(self) -> bool:
        return bool(self._servidor and self._servidor.started and self._hilo and self._hilo.is_alive())

    def iniciar(self, app, host: str | None = None, puerto: int | None = None):
        if self.activo:
            return
        import uvicorn
        host, puerto = host or config.HOST_MOVIL, puerto or config.PUERTO_MOVIL
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:  # ¿el puerto está libre?
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((host, puerto))
            except OSError:
                self.error = f"El puerto {puerto} está ocupado por otro programa."
                raise ErrorNegocio(self.error + " Cierre ese programa o cambie POS_PUERTO_MOVIL.", 409, "PUERTO_OCUPADO")
        # lifespan="off": el ciclo de vida (base de datos, tareas) ya lo maneja el servidor principal
        srv = uvicorn.Server(uvicorn.Config(app, host=host, port=puerto, log_level="warning", log_config=None, lifespan="off"))
        hilo = threading.Thread(target=srv.run, daemon=True, name="pos-movil")
        hilo.start()
        for _ in range(100):
            if srv.started:
                self._servidor, self._hilo, self.error = srv, hilo, None
                log.info("Servidor de celulares escuchando en %s:%s", host, puerto)
                return
            if not hilo.is_alive():
                break
            time.sleep(0.05)
        self.error = "El servidor para celulares no pudo arrancar."
        raise ErrorNegocio(self.error, 500, "MOVIL_NO_ARRANCO")

    def detener(self):
        if self._servidor:
            self._servidor.should_exit = True
            if self._hilo:
                self._hilo.join(timeout=8)
            log.info("Servidor de celulares detenido.")
        self._servidor = self._hilo = None


servidor = ServidorMovil()


def habilitado(db: Session) -> bool:
    return cfg(db, "acceso_movil") == "1"


# ───────────────────────────── Control de acceso (cada petición por el servidor de celulares) ─────────────────────────────
def _rechazo(status: int, detalle: str, codigo: str | None = None) -> tuple[int, str, str | None]:
    return status, detalle, codigo


def controlar_acceso(request) -> tuple[int, str, str | None] | None:
    """Devuelve (status, detalle, código) si hay que rechazar la petición, o None si pasa. Marca `request.state`."""
    ip = request.client.host if request.client else ""
    if not _es_red_local(ip):
        return _rechazo(403, "Solo se atiende a dispositivos de la red local.")
    host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]")
    if not _es_red_local(host):  # solo por IP: así no sirven los nombres falsos (DNS rebinding)
        return _rechazo(403, "Acceso no permitido.")
    s = db_mod.nueva_sesion()
    try:
        if not habilitado(s):
            return _rechazo(403, "El acceso desde celulares está apagado en el computador.", "MOVIL_APAGADO")
        ruta, metodo = request.url.path, request.method
        request.state.movil = True
        if ruta == "/" or ruta == "/m" or ruta.startswith("/m/"):
            return None                      # las pantallas de la app no tienen datos
        if not ruta.startswith("/api/"):
            return _rechazo(404, "No encontrado.")
        if ruta in PUBLICAS:
            return None
        if not any(met == metodo and rx.fullmatch(ruta) for met, rx in PERMITIDAS):
            return _rechazo(403, "Esta función solo está disponible en el computador.", "SOLO_EN_EL_COMPUTADOR")
        token = request.headers.get("x-dispositivo") or ""
        d = s.scalars(select(m.Dispositivo).where(m.Dispositivo.token_hash == _hash(token),
                                                  m.Dispositivo.revocado_en.is_(None))).first() if token else None
        if not d:
            return _rechazo(401, "Este celular no está vinculado (o fue desvinculado). Vincúlelo de nuevo.", "DISPOSITIVO_NO_VINCULADO")
        request.state.dispositivo_id = d.id
        dispositivo_id = d.id
    finally:
        s.close()
    _registrar_uso(dispositivo_id, ip)
    return None


def _registrar_uso(dispositivo_id: int, ip: str):
    """Anota cuándo y desde dónde se usó el celular (como mucho una vez por minuto)."""
    ahora_ts = _reloj()
    if ahora_ts - _ultimo_registro.get(dispositivo_id, 0) < 60:
        return
    _ultimo_registro[dispositivo_id] = ahora_ts
    w = db_mod.nueva_sesion(escritura=True)
    try:
        d = w.get(m.Dispositivo, dispositivo_id)
        if d:
            d.ultimo_uso, d.ultima_ip = ahora(), ip[:45]
            w.commit()
    except Exception:  # noqa: BLE001 - un registro de uso nunca debe tumbar una venta
        w.rollback()
    finally:
        w.close()


# ───────────────────────────── Vinculación ─────────────────────────────
def nuevo_codigo() -> dict:
    """Genera el código de vinculación (reemplaza al anterior)."""
    with _lock:
        _codigo.clear()
        _codigo.update(codigo=f"{secrets.randbelow(10 ** 6):06d}", expira=_reloj() + CODIGO_VIGENCIA_S, intentos=0)
        return {"codigo": _codigo["codigo"], "vigencia_s": CODIGO_VIGENCIA_S}


def qr_svg(contenido: str) -> str:
    import segno
    return segno.make(contenido, error="m").svg_inline(scale=6, border=2, dark="#0b3b37", light="#ffffff")


def contenido_qr(direccion: str, codigo: str, negocio: str) -> str:
    return json.dumps({"pos": config.API_MOVIL, "url": f"http://{direccion}:{config.PUERTO_MOVIL}", "codigo": codigo, "negocio": negocio},
                      ensure_ascii=False, separators=(",", ":"))


def vincular(db: Session, codigo: str, nombre: str, ip: str) -> tuple[str, m.Dispositivo]:
    """Canjea el código por la llave del celular. Se guarda solo el hash; la llave viaja una única vez."""
    limitador.revisar(f"vincular:{ip}")
    with _lock:
        vigente = _codigo.get("codigo")
        if not vigente or _reloj() > _codigo["expira"]:
            _codigo.clear()
            raise ErrorNegocio("El código venció o no existe. Genere uno nuevo en el computador.", 410, "CODIGO_VENCIDO")
        if not secrets.compare_digest(str(codigo or "").strip(), vigente):
            _codigo["intentos"] += 1
            limitador.fallo(f"vincular:{ip}")
            if _codigo["intentos"] >= MAX_INTENTOS_CODIGO:
                _codigo.clear()
                raise ErrorNegocio("Demasiados intentos con el código. Genere uno nuevo en el computador.", 403, "CODIGO_ANULADO")
            raise ErrorNegocio("El código no es correcto.", 403, "CODIGO_INCORRECTO")
        _codigo.clear()  # un solo uso
    limitador.exito(f"vincular:{ip}")
    activos = db.scalar(select(func.count()).select_from(m.Dispositivo).where(m.Dispositivo.revocado_en.is_(None))) or 0
    if activos >= MAX_DISPOSITIVOS:
        raise ErrorNegocio(f"Ya hay {MAX_DISPOSITIVOS} celulares vinculados. Desvincule alguno en el computador.", 409, "MUCHOS_DISPOSITIVOS")
    token = secrets.token_urlsafe(32)
    d = m.Dispositivo(nombre=(nombre or "").strip()[:80] or "Celular", token_hash=_hash(token), creado_en=ahora(), ultima_ip=ip[:45])
    db.add(d)
    db.flush()
    auditar(db, None, "MOVIL_VINCULADO", "dispositivo", d.id, despues={"nombre": d.nombre, "ip": ip})
    return token, d


def listar(db: Session) -> list[dict]:
    return [{"id": d.id, "nombre": d.nombre, "creado_en": d.creado_en.isoformat(), "ultimo_uso": d.ultimo_uso.isoformat() if d.ultimo_uso else None,
             "ultima_ip": d.ultima_ip} for d in db.scalars(select(m.Dispositivo).where(m.Dispositivo.revocado_en.is_(None)).order_by(m.Dispositivo.id))]


def revocar(db: Session, usuario: m.Usuario, dispositivo_id: int):
    d = db.get(m.Dispositivo, dispositivo_id)
    if not d or d.revocado_en:
        raise ErrorNegocio("Ese celular ya no está vinculado.", 404)
    d.revocado_en = ahora()
    auditar(db, usuario.id, "MOVIL_REVOCADO", "dispositivo", d.id, antes={"nombre": d.nombre})
