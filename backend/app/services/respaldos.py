"""Respaldos de la base de datos: copia segura en caliente, copia externa, retención y restauración.

Usa la API de *backup* de SQLite, que produce una copia consistente aunque la base esté en uso.
La "carpeta externa" puede ser un USB, un disco externo o una carpeta sincronizada (Google Drive para
escritorio, OneDrive, Dropbox…): así se logra la copia fuera del computador sin configurar credenciales.
"""
from __future__ import annotations

import gzip
import shutil
import sqlite3
import tempfile
import zlib
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config, db as db_mod
from .. import models as m
from ..core import ErrorNegocio, ahora, auditar, cfg, cfg_int, verificar_hash

RETENCION_DIARIOS = 30
RETENCION_MENSUALES = 12


def _copiar_sqlite(origen: Path, destino: Path):
    src = sqlite3.connect(f"file:{origen}?mode=ro", uri=True, timeout=30)
    dst = sqlite3.connect(destino)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def crear_respaldo(db: Session, tipo: str = "manual", usuario_id: int | None = None) -> dict:
    """Crea `pos-AAAAMMDD-HHMMSS-<tipo>.db.gz` en la carpeta de respaldos y, si está configurada, en la externa."""
    ahora_ = ahora()
    nombre = f"pos-{ahora_:%Y%m%d-%H%M%S}-{tipo}.db.gz"
    destino = config.dir_respaldos() / nombre
    with tempfile.TemporaryDirectory() as tmp:
        plano = Path(tmp) / "copia.db"
        _copiar_sqlite(config.ruta_db(), plano)
        with open(plano, "rb") as f_in, gzip.open(destino, "wb", compresslevel=6) as f_out:
            shutil.copyfileobj(f_in, f_out)
    externa_ok, aviso = False, None
    carpeta = cfg(db, "respaldo_carpeta_externa").strip()
    if carpeta:
        try:
            ext = Path(carpeta)
            ext.mkdir(parents=True, exist_ok=True)
            shutil.copy2(destino, ext / nombre)
            externa_ok = True
        except OSError as e:
            aviso = f"No se pudo copiar a la carpeta externa «{carpeta}»: {e.strerror or e}"
    r = m.Respaldo(fecha=ahora_, archivo=nombre, tipo=tipo, tamano=destino.stat().st_size, copia_externa=externa_ok)
    db.add(r)
    db.flush()
    _aplicar_retencion()
    if usuario_id:
        auditar(db, usuario_id, "RESPALDO", "respaldo", r.id, despues={"archivo": nombre, "externa": externa_ok})
    return {"id": r.id, "archivo": nombre, "tamano": r.tamano, "copia_externa": externa_ok, "aviso": aviso}


def _aplicar_retencion():
    """Conserva los últimos 30 días de respaldos y el más reciente de cada uno de los últimos 12 meses."""
    archivos = sorted(config.dir_respaldos().glob("pos-*.db.gz"))
    corte = ahora() - timedelta(days=RETENCION_DIARIOS)
    por_mes: dict[str, Path] = {}
    for a in archivos:
        try:
            fecha = datetime.strptime(a.name[4:19], "%Y%m%d-%H%M%S")
        except ValueError:
            continue
        if "previo_restauracion" in a.name:
            continue
        if fecha < corte:
            por_mes[f"{fecha:%Y-%m}"] = a  # el último del mes (la lista está ordenada)
    meses_conservar = set(sorted(por_mes)[-RETENCION_MENSUALES:])
    conservar = {p for k, p in por_mes.items() if k in meses_conservar}
    for a in archivos:
        try:
            fecha = datetime.strptime(a.name[4:19], "%Y%m%d-%H%M%S")
        except ValueError:
            continue
        if fecha < corte and a not in conservar and "previo_restauracion" not in a.name:
            a.unlink(missing_ok=True)


def listar(db: Session) -> list[dict]:
    existentes = {p.name for p in config.dir_respaldos().glob("pos-*.db.gz")}
    return [{"id": r.id, "fecha": r.fecha.isoformat(), "archivo": r.archivo, "tipo": r.tipo, "tamano": r.tamano,
             "copia_externa": r.copia_externa, "disponible": r.archivo in existentes}
            for r in db.scalars(select(m.Respaldo).order_by(m.Respaldo.id.desc()).limit(100))]


def estado(db: Session) -> dict:
    ultimo = db.scalars(select(m.Respaldo).order_by(m.Respaldo.id.desc())).first()
    ultimo_ext = db.scalars(select(m.Respaldo).where(m.Respaldo.copia_externa.is_(True))
                            .order_by(m.Respaldo.id.desc())).first()
    limite = cfg_int(db, "respaldo_alerta_dias")
    hay_externa = bool(cfg(db, "respaldo_carpeta_externa").strip())
    ref = ultimo_ext if hay_externa else ultimo
    dias = (ahora() - ref.fecha).days if ref else None
    alerta = None
    if not ultimo:
        alerta = "Todavía no se ha hecho ningún respaldo."
    elif not hay_externa:
        alerta = "No hay carpeta externa configurada: si el computador se daña o lo roban, se pierde todo."
    elif dias is None or dias >= limite:
        alerta = f"El último respaldo externo tiene {dias if dias is not None else 'más de'} día(s). Conecte el USB/disco."
    return {"ultimo": ultimo.fecha.isoformat() if ultimo else None, "ultimo_externo": ultimo_ext.fecha.isoformat() if ultimo_ext else None,
            "externa_configurada": hay_externa, "dias_sin_externo": dias, "alerta": alerta}


def restaurar(db: Session, usuario: m.Usuario, archivo: str, password: str) -> str:
    """Reemplaza la base actual por un respaldo. Primero guarda una copia de la base actual."""
    if not verificar_hash(usuario.hash_password, password or ""):
        raise ErrorNegocio("Contraseña incorrecta.", 403)
    origen = (config.dir_respaldos() / Path(archivo).name)
    if not origen.exists() or not origen.name.startswith("pos-"):
        raise ErrorNegocio("El respaldo no existe en la carpeta de respaldos.", 404)
    with tempfile.TemporaryDirectory() as tmp:
        plano = Path(tmp) / "restaurar.db"
        try:
            with gzip.open(origen, "rb") as f_in, open(plano, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
            chequeo = sqlite3.connect(plano)
            try:
                ok = chequeo.execute("PRAGMA integrity_check").fetchone()[0]
                tablas = {r[0] for r in chequeo.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            finally:
                chequeo.close()
        except (OSError, EOFError, gzip.BadGzipFile, zlib.error, sqlite3.DatabaseError):
            raise ErrorNegocio("El archivo de respaldo está dañado o no es de este sistema.", 422)
        if ok != "ok" or "ventas" not in tablas or "usuarios" not in tablas:
            raise ErrorNegocio("El archivo de respaldo está dañado o no es de este sistema.", 422)
        previo = crear_respaldo(db, tipo="previo_restauracion", usuario_id=usuario.id)
        db.commit()
        db.close()
        with db_mod.bloqueo_motor:
            db_mod.engine.dispose()
            destino = config.ruta_db()
            for sufijo in ("-wal", "-shm"):
                Path(str(destino) + sufijo).unlink(missing_ok=True)
            shutil.copyfile(plano, destino)
            db_mod.configurar(destino)
    return previo["archivo"]
