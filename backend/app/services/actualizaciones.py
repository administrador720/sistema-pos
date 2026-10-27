"""Actualizaciones del programa desde las versiones (Releases) de GitHub.

Flujo: buscar → descargar (verifica la suma SHA-256 publicada) → instalar (respaldo previo, abre el instalador con
permiso de administrador y cierra el programa). El instalador reemplaza los archivos en el mismo lugar y vuelve a abrir
el programa; la base de datos vive en ProgramData y no se toca (las migraciones corren al arrancar).

Solo funciona en la versión instalada en Windows. Todo lo demás (buscar, descargar, verificar) se puede probar en
cualquier sistema: la red se aísla en `_abrir`.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

from .. import config, db as db_mod
from ..core import ErrorNegocio, auditar
from . import respaldos

log = logging.getLogger("pos.actualizaciones")

_abrir = urllib.request.urlopen  # las pruebas lo reemplazan
MAX_BYTES = 600 * 1024 * 1024
PATRON_INSTALADOR = re.compile(r"Instalador-POS-Supermercado-(\d+(?:\.\d+)*)\.exe")
_lock = threading.Lock()
_ultima: dict | None = None
_estado: dict = {"fase": "ninguna"}


def _agente() -> str:
    return f"POS-Supermercado/{config.VERSION}"


def version_tupla(texto: str) -> tuple[int, ...]:
    """«v1.2.0», «1.2» o «1.2.0-rc1» → (1, 2, 0). Lo que no es número se ignora."""
    limpio = re.match(r"v?(\d+(?:\.\d+)*)", (texto or "").strip())
    if not limpio:
        return (0,)
    partes = tuple(int(x) for x in limpio.group(1).split("."))
    while len(partes) > 1 and partes[-1] == 0:  # 1.2.0 == 1.2
        partes = partes[:-1]
    return partes


def soportado() -> tuple[bool, str | None]:
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        return True, None
    return False, ("Las actualizaciones automáticas funcionan en la versión instalada en Windows. "
                   "En este equipo (modo de desarrollo) actualice con git.")


def _pedir_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": _agente(), "Accept": "application/vnd.github+json"})
    try:
        with _abrir(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ErrorNegocio("Todavía no hay versiones publicadas para descargar.", 404, "SIN_VERSIONES")
        if e.code in (403, 429):
            raise ErrorNegocio("GitHub limitó las consultas por un rato. Intente de nuevo en unos minutos.", 503, "LIMITE_GITHUB")
        raise ErrorNegocio(f"GitHub respondió con un error ({e.code}). Intente más tarde.", 502, "ERROR_GITHUB")
    except (urllib.error.URLError, OSError, TimeoutError, ValueError):
        raise ErrorNegocio("No se pudo consultar si hay una versión nueva. Revise la conexión a internet.", 502, "SIN_CONEXION")


def _pedir_texto(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _agente()})
    with _abrir(req, timeout=20) as r:
        return r.read(4096).decode("utf-8", "replace")


def buscar() -> dict:
    """Consulta la última versión publicada y la compara con la instalada."""
    global _ultima
    repo = config.REPO_ACTUALIZACIONES
    rel = _pedir_json(f"https://api.github.com/repos/{repo}/releases/latest")
    nueva = str(rel.get("tag_name") or "").lstrip("vV")
    base = f"https://github.com/{repo}/releases/download/"
    instalador = sha = None
    for a in rel.get("assets") or []:
        nombre, url = str(a.get("name") or ""), str(a.get("browser_download_url") or "")
        if not url.startswith(base):  # solo archivos publicados en este repositorio
            continue
        if PATRON_INSTALADOR.fullmatch(nombre):
            instalador = {"nombre": nombre, "url": url, "tamano": int(a.get("size") or 0)}
        elif nombre.endswith(".exe.sha256"):
            sha = {"nombre": nombre, "url": url}
    if instalador and not (sha and sha["nombre"] == instalador["nombre"] + ".sha256"):
        sha = None
    ok, motivo = soportado()
    r = {"version_actual": config.VERSION, "version_nueva": nueva,
         "hay_nueva": version_tupla(nueva) > version_tupla(config.VERSION),
         "notas": str(rel.get("body") or "").strip(), "publicada": rel.get("published_at"),
         "instalador": instalador, "sha256_url": sha["url"] if sha else None,
         "descargable": bool(instalador and sha), "soportado": ok, "motivo": motivo}
    if r["hay_nueva"] and not r["descargable"]:
        r["motivo"] = r["motivo"] or "Esa versión no trae un instalador verificable; descárguelo desde la página de versiones."
    _ultima = r
    _limpiar_descargas()
    return r


# ───────────────────────────── Descarga ─────────────────────────────
def estado() -> dict:
    with _lock:
        return dict(_estado)


def _fijar(**campos):
    with _lock:
        _estado.update(campos)


def _sha256_archivo(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def _limpiar_descargas():
    """Borra restos de descargas incompletas y de instaladores de versiones que ya están instaladas."""
    try:
        for f in config.dir_actualizaciones().iterdir():
            m = PATRON_INSTALADOR.fullmatch(f.name)
            if f.suffix == ".part" or (m and version_tupla(m.group(1)) <= version_tupla(config.VERSION)):
                f.unlink(missing_ok=True)
    except OSError:
        pass


def _descargar(info: dict):
    nombre, version = info["instalador"]["nombre"], info["version_nueva"]
    destino = config.dir_actualizaciones() / nombre
    parte = destino.with_name(nombre + ".part")
    try:
        esperado = re.match(r"\s*([0-9a-fA-F]{64})", _pedir_texto(info["sha256_url"]))
        if not esperado:
            raise ErrorNegocio("La suma de verificación publicada no es válida.", 502)
        esperado = esperado.group(1).lower()
        req = urllib.request.Request(info["instalador"]["url"], headers={"User-Agent": _agente()})
        h, recibidos = hashlib.sha256(), 0
        with _abrir(req, timeout=30) as r:
            total = int(r.headers.get("Content-Length") or info["instalador"]["tamano"] or 0)
            if total > MAX_BYTES:
                raise ErrorNegocio("El instalador es más grande de lo esperado; no se descarga.", 502)
            _fijar(fase="descargando", total=total, bytes=0, progreso=0.0)
            with open(parte, "wb") as f:
                while True:
                    bloque = r.read(256 * 1024)
                    if not bloque:
                        break
                    recibidos += len(bloque)
                    if recibidos > MAX_BYTES:
                        raise ErrorNegocio("El instalador es más grande de lo esperado; se canceló la descarga.", 502)
                    f.write(bloque)
                    h.update(bloque)
                    _fijar(bytes=recibidos, progreso=(recibidos / total) if total else 0.0)
        if total and recibidos != total:
            raise ErrorNegocio("La descarga quedó incompleta. Intente de nuevo.", 502)
        _fijar(fase="verificando", progreso=1.0)
        if h.hexdigest() != esperado:
            raise ErrorNegocio("El archivo descargado no coincide con su suma de verificación; se descartó.", 502)
        parte.replace(destino)
        _fijar(fase="listo", archivo=str(destino), sha256=esperado, version=version, error=None)
        log.info("Actualización %s descargada y verificada (%s)", version, destino)
    except ErrorNegocio as e:
        parte.unlink(missing_ok=True)
        _fijar(fase="error", error=e.detalle)
    except (urllib.error.URLError, OSError, TimeoutError):
        parte.unlink(missing_ok=True)
        _fijar(fase="error", error="Se interrumpió la descarga. Revise la conexión a internet e intente de nuevo.")
    except Exception:  # noqa: BLE001
        log.exception("Error inesperado descargando la actualización")
        parte.unlink(missing_ok=True)
        _fijar(fase="error", error="No se pudo descargar la actualización.")


def iniciar_descarga() -> dict:
    ok, motivo = soportado()
    if not ok:
        raise ErrorNegocio(motivo, 409, "NO_SOPORTADO")
    info = buscar()
    if not info["hay_nueva"]:
        raise ErrorNegocio("Ya tiene la versión más reciente.", 409, "AL_DIA")
    if not info["descargable"]:
        raise ErrorNegocio(info["motivo"] or "Esa versión no se puede descargar automáticamente.", 409)
    with _lock:
        if _estado.get("fase") in ("descargando", "verificando"):
            return dict(_estado)
        _estado.clear()
        _estado.update(fase="descargando", version=info["version_nueva"], progreso=0.0, bytes=0, total=info["instalador"]["tamano"], error=None)
    threading.Thread(target=_descargar, args=(info,), daemon=True, name="pos-descarga").start()
    return estado()


# ───────────────────────────── Instalación ─────────────────────────────
def _lanzar_instalador(ruta: Path):
    """Abre el instalador pidiendo permiso de administrador (UAC). Falla si la persona lo cancela."""
    import ctypes
    registro = config.dir_actualizaciones() / "instalacion.log"
    args = f'/SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /RELANZAR=1 /LOG="{registro}"'
    r = ctypes.windll.shell32.ShellExecuteW(None, "runas", str(ruta), args, str(ruta.parent), 1)  # type: ignore[attr-defined]
    if r <= 32:
        raise ErrorNegocio("Windows no abrió el instalador (¿se canceló el permiso de administrador?). El sistema "
                           "sigue funcionando; intente de nuevo.", 409, "INSTALADOR_NO_ABRIO")


def _salir():
    log.info("Cerrando el programa para que el instalador reemplace los archivos.")
    logging.shutdown()
    os._exit(0)


def instalar(usuario) -> dict:
    ok, motivo = soportado()
    if not ok:
        raise ErrorNegocio(motivo, 409, "NO_SOPORTADO")
    est = estado()
    ruta = Path(est.get("archivo") or "")
    if est.get("fase") != "listo" or not ruta.is_file():
        raise ErrorNegocio("Primero descargue la actualización.", 409, "SIN_DESCARGA")
    if _sha256_archivo(ruta) != est.get("sha256"):
        raise ErrorNegocio("El instalador descargado cambió o se dañó. Descárguelo de nuevo.", 409, "DESCARGA_CORRUPTA")
    respaldos.crear_respaldo_seguro("actualizacion", usuario.id)  # si falla, no se actualiza
    s = db_mod.nueva_sesion(escritura=True)
    try:
        auditar(s, usuario.id, "ACTUALIZACION_INICIADA", despues={"desde": config.VERSION, "hasta": est.get("version")})
        s.commit()
    finally:
        s.close()
    _lanzar_instalador(ruta)
    threading.Timer(2.0, _salir).start()
    return {"ok": True, "mensaje": "Instalando la versión %s. El programa se cerrará y volverá a abrir solo en un momento." % est.get("version")}
