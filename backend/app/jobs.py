"""Tareas en segundo plano: foto diaria del inventario y respaldos automáticos.

Un hilo revisa cada minuto qué falta. Está pensado para un computador que se apaga por las noches:
si el respaldo diario no se alcanzó a hacer, se hace al encender (o al cerrar el turno).
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import timedelta

from sqlalchemy import func, select

from . import db as db_mod
from . import models as m
from .core import ahora, cfg, hoy
from .services import inventario as inv
from .services import respaldos

log = logging.getLogger("pos.jobs")
_hilo: threading.Thread | None = None
_parar = threading.Event()
_lock = threading.Lock()


def _en_sesion(fn):
    s = db_mod.nueva_sesion(escritura=True)
    try:
        r = fn(s)
        s.commit()
        return r
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def foto_de_hoy():
    _en_sesion(lambda s: inv.foto_inventario(s, hoy()))


def tras_cierre_turno():
    """Al cerrar un turno: foto del inventario del día y respaldo (en un hilo, sin demorar al cajero)."""
    def trabajo():
        with _lock:
            try:
                _en_sesion(lambda s: inv.foto_inventario(s, hoy()))
                respaldos.crear_respaldo_seguro("turno")
            except Exception:  # noqa: BLE001
                log.exception("Falló el trabajo posterior al cierre de turno")
    if os.environ.get("POS_SIN_JOBS") == "1":
        return
    threading.Thread(target=trabajo, daemon=True, name="pos-cierre-turno").start()


def _hora_respaldo(s) -> tuple[int, int]:
    try:
        h, mi = cfg(s, "respaldo_hora").split(":")
        return int(h), int(mi)
    except ValueError:
        return 23, 30


def tick():
    """Una pasada del planificador."""
    with _lock:
        # 1. fotos de inventario de días pasados que falten (la de hoy se toma al cerrar turno / respaldo)
        _en_sesion(lambda s: inv.asegurar_fotos(s, hoy() - timedelta(days=7), hoy(), refrescar_hoy=False))
        # 2. respaldo diario: se decide con una lectura y se hace SIN transacción de escritura abierta
        s = db_mod.nueva_sesion()
        try:
            ahora_ = ahora()
            h, mi = _hora_respaldo(s)
            hecho_hoy = s.scalar(select(func.count()).select_from(m.Respaldo).where(
                m.Respaldo.tipo == "diario", func.date(m.Respaldo.fecha) == hoy().isoformat()))
            ultimo = s.scalar(select(func.max(m.Respaldo.fecha)))
        finally:
            s.close()
        hora_cumplida = (ahora_.hour, ahora_.minute) >= (h, mi)
        atrasado = ultimo is None or (ahora_ - ultimo) > timedelta(hours=24)
        if not hecho_hoy and (hora_cumplida or atrasado):
            _en_sesion(lambda s: inv.foto_inventario(s, hoy()))
            respaldos.crear_respaldo_seguro("diario")


def _bucle():
    time.sleep(5)  # deja arrancar la interfaz primero
    while not _parar.is_set():
        try:
            tick()
        except Exception:  # noqa: BLE001 - el planificador nunca debe tumbar la aplicación
            log.exception("Error en el planificador")
        _parar.wait(60)


def iniciar():
    global _hilo
    if os.environ.get("POS_SIN_JOBS") == "1" or (_hilo and _hilo.is_alive()):
        return
    _parar.clear()
    _hilo = threading.Thread(target=_bucle, daemon=True, name="pos-planificador")
    _hilo.start()


def detener():
    _parar.set()
