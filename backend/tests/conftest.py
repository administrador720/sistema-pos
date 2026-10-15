import os
import sys
from pathlib import Path

import pytest

os.environ["POS_SIN_JOBS"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402


class Api:
    """Cliente de pruebas con sesión: api.get/post/put/delete devuelven la respuesta cruda."""

    def __init__(self, client: TestClient):
        self.c = client
        self.token: str | None = None

    def _h(self, pin=None, extra=None):
        h = {}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        if pin:
            h["X-Autorizacion-Pin"] = pin
        return {**h, **(extra or {})}

    def get(self, url, pin=None, **kw): return self.c.get(url, headers=self._h(pin), **kw)
    def post(self, url, json=None, pin=None, **kw): return self.c.post(url, json=json, headers=self._h(pin), **kw)
    def put(self, url, json=None, pin=None, **kw): return self.c.put(url, json=json, headers=self._h(pin), **kw)
    def delete(self, url, pin=None, **kw): return self.c.delete(url, headers=self._h(pin), **kw)

    def ok(self, r, status=200):
        assert r.status_code == status, f"{r.request.method} {r.request.url.path} → {r.status_code}: {r.text}"
        return r.json() if r.headers.get("content-type", "").startswith("application/json") else r

    def login(self, usuario, password):
        r = self.c.post("/api/auth/login", json={"usuario": usuario, "password": password})
        self.token = r.json().get("token") if r.status_code == 200 else None
        return r


@pytest.fixture()
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("POS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("POS_EXPORT_DIR", str(tmp_path / "exportes"))
    from app import core, db
    core.limitador.reiniciar()
    core.reloj = __import__("datetime").datetime.now
    db.configurar()
    from app.main import app
    with TestClient(app, base_url="http://localhost") as client:
        yield Api(client)
    db.engine.dispose()


@pytest.fixture()
def tienda(api):
    """Negocio configurado, con un administrador, un cajero y algunos productos."""
    r = api.post("/api/setup", {"negocio": {"nombre": "Super Prueba", "nit": "900123"},
                                "admin": {"nombre": "Ana Admin", "usuario": "admin", "password": "secreto1", "pin": "1234"}})
    api.token = api.ok(r)["token"]
    api.ok(api.post("/api/usuarios", {"nombre": "Carlos Cajero", "usuario": "carlos", "password": "cajero1", "pin": "4321", "rol": "cajero"}))
    cat = api.ok(api.get("/api/catalogos"))
    impuestos = {i["nombre"]: i["id"] for i in cat["impuestos"]}
    medios = {x["nombre"]: x["id"] for x in cat["medios_pago"]}

    def producto(nombre, precio, costo, stock, codigo, impuesto="IVA 19%", **extra):
        return api.ok(api.post("/api/productos", {
            "nombre": nombre, "precio_venta": precio, "costo_promedio": costo, "stock_inicial": stock,
            "impuesto_id": impuestos[impuesto], "codigos": [{"codigo": codigo, "unidades": 1}], **extra}))

    class T:
        pass
    t = T()
    t.api, t.impuestos, t.medios, t.producto = api, impuestos, medios, producto
    t.leche = producto("Leche 1 L", 4200, 3000, 50, "7701", impuesto="Excluido")
    t.arroz = producto("Arroz 500 g", 2900, 2000, 40, "7702", impuesto="Exento (0%)")
    t.aceite = producto("Aceite 1 L", 11500, 8000, 20, "7703")
    t.admin_token = api.token
    t.categorias = cat["categorias"]
    return t


def abrir_turno_cajero(t, base=100000):
    """Inicia sesión como el cajero y abre turno con la base indicada. Devuelve el turno."""
    api = t.api
    api.login("carlos", "cajero1")
    return api.ok(api.post("/api/turnos/abrir", {"base": base}))["turno"]


def volver_admin(t):
    t.api.token = t.admin_token
