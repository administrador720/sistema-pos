"""Rutas y ajustes de arranque. Los ajustes del negocio viven en la tabla `configuracion`."""
import os
import sys
from pathlib import Path

VERSION = "1.0.0"
NOMBRE_APP = "POS Supermercado"


def directorio_datos() -> Path:
    """Carpeta donde viven la base de datos y los respaldos."""
    env = os.environ.get("POS_DATA_DIR")
    if env:
        base = Path(env)
    elif sys.platform == "win32":
        base = Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "POSSupermercado"
    else:
        base = Path.home() / ".local" / "share" / "pos-supermercado"
    base.mkdir(parents=True, exist_ok=True)
    return base


def ruta_db() -> Path:
    d = directorio_datos() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d / "pos.db"


def dir_respaldos() -> Path:
    d = directorio_datos() / "respaldos"
    d.mkdir(parents=True, exist_ok=True)
    return d


def dir_exportes() -> Path:
    """Donde se guardan los Excel/PDF generados desde la ventana de escritorio."""
    env = os.environ.get("POS_EXPORT_DIR")
    base = Path(env) if env else Path.home() / "Documents" / "POS Supermercado" / "Exportes"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError:
        base = directorio_datos() / "exportes"
        base.mkdir(parents=True, exist_ok=True)
    return base


def dir_frontend() -> Path:
    """Frontend estático; funciona tanto en desarrollo como empaquetado con PyInstaller."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", ".")) / "frontend"
    return Path(__file__).resolve().parents[2] / "frontend"


PUERTO = int(os.environ.get("POS_PUERTO", "8765"))
HOST = "127.0.0.1"  # solo local: nunca exponer a la red
