"""Actualizaciones desde GitHub: comparar versiones, descargar con verificación, instalar (sin tocar la red ni Windows)."""
import hashlib
import io
import json
import time
import urllib.error
from pathlib import Path

import pytest

from app import config
from app.services import actualizaciones as act

REPO = config.REPO_ACTUALIZACIONES
BASE = f"https://github.com/{REPO}/releases/download/v9.9.9/"
NOMBRE = "Instalador-POS-Supermercado-9.9.9.exe"
CONTENIDO = b"MZ" + bytes(range(256)) * 300      # un «instalador» de mentira


class Respuesta(io.BytesIO):
    def __init__(self, datos: bytes, largo=None):
        super().__init__(datos)
        self.headers = {"Content-Length": str(len(datos) if largo is None else largo)}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def release(**cambios):
    r = {"tag_name": "v9.9.9", "published_at": "2026-11-01T10:00:00Z", "body": "Qué hay de nuevo:\n- Cosas buenas",
         "assets": [{"name": NOMBRE, "browser_download_url": BASE + NOMBRE, "size": len(CONTENIDO)},
                    {"name": NOMBRE + ".sha256", "browser_download_url": BASE + NOMBRE + ".sha256", "size": 100}]}
    r.update(cambios)
    return r


@pytest.fixture()
def github(monkeypatch):
    """Falso GitHub: el estado se cambia con g.release, g.contenido, g.sha, g.fallo."""
    class G:
        pass
    g = G()
    g.release, g.contenido, g.fallo, g.pedidos = release(), CONTENIDO, None, []
    g.sha = lambda: hashlib.sha256(g.contenido).hexdigest() + f"  {NOMBRE}\n"

    def abrir(req, timeout=None):
        url = req.full_url
        g.pedidos.append(url)
        if g.fallo:
            raise g.fallo
        if url == f"https://api.github.com/repos/{REPO}/releases/latest":
            return Respuesta(json.dumps(g.release).encode())
        if url == BASE + NOMBRE:
            return Respuesta(g.contenido)
        if url == BASE + NOMBRE + ".sha256":
            return Respuesta(g.sha().encode())
        raise urllib.error.HTTPError(url, 404, "no", {}, None)

    monkeypatch.setattr(act, "_abrir", abrir)
    act._estado.clear()
    act._estado["fase"] = "ninguna"
    return g


@pytest.fixture()
def windows(monkeypatch):
    """Simula el programa instalado en Windows y registra lo que haría el instalador."""
    hechos = {"lanzado": [], "salidas": 0}
    monkeypatch.setattr(act, "soportado", lambda: (True, None))
    monkeypatch.setattr(act, "_lanzar_instalador", lambda ruta: hechos["lanzado"].append(ruta))
    monkeypatch.setattr(act, "_salir", lambda: hechos.__setitem__("salidas", hechos["salidas"] + 1))
    return hechos


def esperar_fase(api, fase, segundos=10):
    fin = time.time() + segundos
    while time.time() < fin:
        e = api.ok(api.get("/api/sistema/actualizaciones/estado"))
        if e["fase"] == fase or e["fase"] == "error":
            return e
        time.sleep(0.05)
    raise AssertionError(f"No llegó a «{fase}»: {e}")


def test_comparacion_de_versiones():
    v = act.version_tupla
    assert v("v1.2.0") == v("1.2") == (1, 2)
    assert v("1.10.0") > v("1.9.9") > v("1.9")
    assert v("1.2.0-rc1") == (1, 2) and v("basura") == (0,) and v("") == (0,)
    assert v("2.0") > v("1.99.99")


def test_la_version_sale_del_archivo_version():
    raiz = Path(config.__file__).resolve().parents[2]
    assert config.VERSION == (raiz / "VERSION").read_text().strip() != "0.0.0"


def test_buscar_encuentra_una_version_nueva(tienda, github):
    api = tienda.api
    r = api.ok(api.post("/api/sistema/actualizaciones/buscar"))
    assert r["hay_nueva"] and r["version_nueva"] == "9.9.9" and r["version_actual"] == config.VERSION
    assert r["descargable"] and r["instalador"]["nombre"] == NOMBRE and "Cosas buenas" in r["notas"]
    assert r["soportado"] is False and "Windows" in r["motivo"]          # en el entorno de pruebas (Linux)
    # misma versión o anterior: no hay nada nuevo
    github.release = release(tag_name="v" + config.VERSION)
    assert api.ok(api.post("/api/sistema/actualizaciones/buscar"))["hay_nueva"] is False


def test_un_archivo_ajeno_al_repositorio_no_se_acepta(tienda, github):
    github.release = release(assets=[{"name": NOMBRE, "browser_download_url": "https://malo.example.com/" + NOMBRE, "size": 5},
                                     {"name": NOMBRE + ".sha256", "browser_download_url": "https://malo.example.com/x.sha256", "size": 5}])
    r = tienda.api.ok(tienda.api.post("/api/sistema/actualizaciones/buscar"))
    assert r["hay_nueva"] and not r["descargable"] and r["instalador"] is None


def test_una_version_sin_suma_de_verificacion_no_se_descarga_sola(tienda, github, windows):
    github.release = release(assets=[github.release["assets"][0]])
    api = tienda.api
    r = api.ok(api.post("/api/sistema/actualizaciones/buscar"))
    assert r["hay_nueva"] and not r["descargable"]
    assert api.post("/api/sistema/actualizaciones/descargar").status_code == 409


def test_errores_de_red_se_explican(tienda, github):
    api = tienda.api
    github.fallo = urllib.error.URLError("sin red")
    r = api.post("/api/sistema/actualizaciones/buscar")
    assert r.status_code == 502 and r.json()["codigo"] == "SIN_CONEXION" and "internet" in r.json()["detalle"]
    github.fallo = urllib.error.HTTPError("u", 404, "x", {}, None)
    assert api.post("/api/sistema/actualizaciones/buscar").json()["codigo"] == "SIN_VERSIONES"
    github.fallo = urllib.error.HTTPError("u", 403, "x", {}, None)
    assert api.post("/api/sistema/actualizaciones/buscar").json()["codigo"] == "LIMITE_GITHUB"


def test_solo_el_administrador_actualiza(tienda, github):
    api = tienda.api
    api.login("carlos", "cajero1")
    for metodo, ruta in (("get", "/api/sistema/version"), ("post", "/api/sistema/actualizaciones/buscar"),
                         ("post", "/api/sistema/actualizaciones/descargar"), ("get", "/api/sistema/actualizaciones/estado"),
                         ("post", "/api/sistema/actualizaciones/instalar")):
        assert getattr(api, metodo)(ruta).status_code == 403, ruta
    assert github.pedidos == []


def test_fuera_de_windows_no_se_puede_instalar(tienda, github):
    api = tienda.api
    r = api.post("/api/sistema/actualizaciones/descargar")
    assert r.status_code == 409 and r.json()["codigo"] == "NO_SOPORTADO"
    assert api.post("/api/sistema/actualizaciones/instalar").json()["codigo"] == "NO_SOPORTADO"
    v = api.ok(api.get("/api/sistema/version"))
    assert v["version"] == config.VERSION and v["soportado"] is False


def test_descarga_verificada_e_instalacion(tienda, github, windows):
    api = tienda.api
    est = api.ok(api.post("/api/sistema/actualizaciones/descargar"))
    assert est["fase"] in ("descargando", "verificando", "listo")
    est = esperar_fase(api, "listo")
    assert est["fase"] == "listo" and est["version"] == "9.9.9"
    archivo = Path(est["archivo"])
    assert archivo.read_bytes() == CONTENIDO and archivo.parent == config.dir_actualizaciones()
    assert not list(config.dir_actualizaciones().glob("*.part"))

    r = api.ok(api.post("/api/sistema/actualizaciones/instalar"))
    assert r["ok"] and "9.9.9" in r["mensaje"]
    assert windows["lanzado"] == [archivo]
    # antes de instalar se hizo un respaldo y quedó en la auditoría
    resp = api.ok(api.get("/api/respaldos"))["respaldos"]
    assert any("actualizacion" in x["archivo"] for x in resp)
    acc = [a["accion"] for a in api.ok(api.get("/api/auditoria"))["filas"]]
    assert "ACTUALIZACION_INICIADA" in acc
    time.sleep(2.3)   # el programa se cierra 2 s después de abrir el instalador
    assert windows["salidas"] == 1


def test_una_descarga_alterada_se_descarta(tienda, github, windows):
    api = tienda.api
    github.contenido = CONTENIDO[:-1] + b"X"
    github.sha = lambda: hashlib.sha256(CONTENIDO).hexdigest() + "  x\n"        # la suma publicada es de otro archivo
    api.ok(api.post("/api/sistema/actualizaciones/descargar"))
    est = esperar_fase(api, "listo")
    assert est["fase"] == "error" and "suma de verificación" in est["error"]
    assert not list(config.dir_actualizaciones().glob("Instalador*"))
    assert api.post("/api/sistema/actualizaciones/instalar").json()["codigo"] == "SIN_DESCARGA"
    assert windows["lanzado"] == []


def test_descarga_incompleta_o_exagerada(tienda, github, windows, monkeypatch):
    api = tienda.api
    # el servidor promete más bytes de los que entrega
    abrir_original = act._abrir

    def corto(req, timeout=None):
        r = abrir_original(req, timeout)
        if req.full_url.endswith(".exe"):
            r.headers["Content-Length"] = str(len(CONTENIDO) + 10)
        return r
    monkeypatch.setattr(act, "_abrir", corto)
    api.ok(api.post("/api/sistema/actualizaciones/descargar"))
    assert "incompleta" in esperar_fase(api, "listo")["error"]
    # y uno que promete un tamaño absurdo
    monkeypatch.setattr(act, "MAX_BYTES", 100)
    api.ok(api.post("/api/sistema/actualizaciones/descargar"))
    assert "más grande" in esperar_fase(api, "listo")["error"]


def test_si_se_cancela_el_permiso_de_administrador_el_programa_sigue(tienda, github, windows, monkeypatch):
    from app.core import ErrorNegocio
    api = tienda.api
    api.ok(api.post("/api/sistema/actualizaciones/descargar"))
    esperar_fase(api, "listo")

    def cancelado(ruta):
        raise ErrorNegocio("Windows no abrió el instalador", 409, "INSTALADOR_NO_ABRIO")
    monkeypatch.setattr(act, "_lanzar_instalador", cancelado)
    r = api.post("/api/sistema/actualizaciones/instalar")
    assert r.status_code == 409 and r.json()["codigo"] == "INSTALADOR_NO_ABRIO"
    time.sleep(2.3)
    assert windows["salidas"] == 0          # no se cerró: el sistema sigue funcionando


def test_el_instalador_cambiado_despues_de_descargar_no_se_ejecuta(tienda, github, windows):
    api = tienda.api
    api.ok(api.post("/api/sistema/actualizaciones/descargar"))
    est = esperar_fase(api, "listo")
    Path(est["archivo"]).write_bytes(b"otra cosa")
    r = api.post("/api/sistema/actualizaciones/instalar")
    assert r.status_code == 409 and r.json()["codigo"] == "DESCARGA_CORRUPTA"
    assert windows["lanzado"] == []


def test_un_programa_viejo_no_abre_una_base_mas_nueva(tmp_path, monkeypatch):
    import sqlite3
    from app import db as db_mod
    monkeypatch.setenv("POS_DATA_DIR", str(tmp_path))
    eng = db_mod.configurar()
    db_mod.inicializar()
    with eng.begin() as c:
        c.exec_driver_sql("UPDATE _version SET version = 99 WHERE id = 1")
    with pytest.raises(RuntimeError, match="versión más nueva"):
        db_mod.inicializar()
    eng.dispose()
