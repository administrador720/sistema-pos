"""Servidor real (uvicorn) con datos de demostración + navegador Playwright para las pruebas de interfaz."""
import glob
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]


def _chromium():
    explicito = os.environ.get("POS_CHROMIUM")
    if explicito and Path(explicito).exists():
        return explicito
    for patron in ("/opt/pw-browsers/chromium-*/chrome-linux/chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"):
        hallados = sorted(glob.glob(patron))
        if hallados:
            return hallados[-1]
    return None


@pytest.fixture(scope="session")
def servidor(tmp_path_factory):
    pytest.importorskip("playwright")
    datos = tmp_path_factory.mktemp("pos-e2e")
    env = {**os.environ, "POS_DATA_DIR": str(datos), "POS_EXPORT_DIR": str(datos / "exportes"), "POS_SIN_JOBS": "1", "PYTHONPATH": str(BACKEND)}
    subprocess.run([sys.executable, "-m", "app.seed_demo", "--dias", "4", "--ventas-dia", "14"], cwd=BACKEND, env=env, check=True, capture_output=True)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        puerto = s.getsockname()[1]
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(puerto), "--log-level", "warning"],
                            cwd=BACKEND, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{puerto}/"
    for _ in range(80):
        try:
            urllib.request.urlopen(url + "api/salud", timeout=1)
            break
        except Exception:  # noqa: BLE001
            time.sleep(0.25)
    else:
        proc.kill()
        pytest.fail("El servidor no arrancó: " + proc.stdout.read().decode(errors="replace"))
    yield url
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture(scope="session")
def navegador():
    sync = pytest.importorskip("playwright.sync_api")
    ejecutable = _chromium()
    if not ejecutable:
        pytest.skip("No hay Chromium disponible (defina POS_CHROMIUM)")
    with sync.sync_playwright() as p:
        b = p.chromium.launch(executable_path=ejecutable, args=["--no-sandbox"])
        yield b
        b.close()


@pytest.fixture()
def pagina(navegador, servidor):
    ctx = navegador.new_context(viewport={"width": 1440, "height": 900}, locale="es-CO")
    pg = ctx.new_page()
    pg.errores = []
    pg.on("pageerror", lambda e: pg.errores.append(f"pageerror: {e}"))
    pg.on("console", lambda m: pg.errores.append(f"{m.type}: {m.text}") if m.type == "error" and "404" not in m.text else None)
    pg.goto(servidor)
    pg.url_base = servidor
    yield pg
    ctx.close()


def entrar(pg, usuario, password):
    pg.wait_for_selector(".auth")
    pg.fill("input[autocomplete=username]", usuario)
    pg.fill("input[type=password]", password)
    pg.keyboard.press("Enter")
    pg.wait_for_selector(".sidebar", timeout=10000)
