"""Rutas y ajustes de arranque. Los ajustes del negocio viven en la tabla `configuracion`."""
import os
import sys
from pathlib import Path

NOMBRE_APP = "POS Supermercado"
# Repositorio de GitHub donde se publican las versiones nuevas (Releases). Se puede cambiar con POS_REPO_ACTUALIZACIONES.
REPO_ACTUALIZACIONES = os.environ.get("POS_REPO_ACTUALIZACIONES", "administrador720/sistema-pos")


def _leer_version() -> str:
    """La versión vive en el archivo VERSION de la raíz (y se empaqueta junto al programa)."""
    for base in (Path(getattr(sys, "_MEIPASS", "")), Path(__file__).resolve().parents[2]):
        archivo = base / "VERSION"
        if archivo.is_file():
            return archivo.read_text(encoding="utf-8").strip() or "0.0.0"
    return "0.0.0"


VERSION = _leer_version()


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


def dir_actualizaciones() -> Path:
    """Instaladores descargados de las versiones nuevas."""
    d = directorio_datos() / "actualizaciones"
    d.mkdir(parents=True, exist_ok=True)
    return d


def directorio_usuario() -> Path:
    """Datos que son de cada usuario de Windows (por ejemplo, el perfil del motor de la ventana)."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "POSSupermercado"
    else:
        base = Path.home() / ".local" / "share" / "pos-supermercado-usuario"
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
