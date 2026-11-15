"""Celulares en la red local: acceso apagado por defecto, vinculación con código/QR, API reducida y solo administrador."""
import json
import socket
import urllib.error
import urllib.request

import pytest
from fastapi.testclient import TestClient

from app import config, core
from app.services import movil as svc

IP_PC = "192.168.1.20"
IP_CEL = "192.168.1.50"


class Celular:
    """Cliente que llega por el puerto de celulares, desde otra máquina de la red local."""

    def __init__(self, app, ip=IP_CEL, host=IP_PC, puerto=None):
        self.c = TestClient(app, base_url=f"http://{host}:{puerto or config.PUERTO_MOVIL}", client=(ip, 51000))
        self.llave = None
        self.sesion = None

    def pedir(self, metodo, url, json_=None, llave=True, sesion=True, **kw):
        h = {}
        if llave and self.llave:
            h["X-Dispositivo"] = self.llave
        if sesion and self.sesion:
            h["Authorization"] = f"Bearer {self.sesion}"
        return self.c.request(metodo, url, json=json_, headers=h, follow_redirects=False, **kw)

    def get(self, url, **kw): return self.pedir("GET", url, **kw)
    def post(self, url, json_=None, **kw): return self.pedir("POST", url, json_, **kw)
    def put(self, url, json_=None, **kw): return self.pedir("PUT", url, json_, **kw)
    def delete(self, url, **kw): return self.pedir("DELETE", url, **kw)


@pytest.fixture()
def red(tienda, monkeypatch):
    """La tienda lista, sin abrir puertos de verdad, con una red local conocida."""
    from app.main import app
    monkeypatch.setattr(svc.servidor, "iniciar", lambda *a, **k: None)
    monkeypatch.setattr(svc.servidor, "detener", lambda: None)
    monkeypatch.setattr(svc, "direcciones_locales", lambda: [IP_PC])
    tienda.app = app
    tienda.celular = lambda **kw: Celular(app, **kw)
    return tienda


def activar(t):
    t.api.ok(t.api.post("/api/movil/habilitar", {"habilitado": True}))


def vincular(t, cel=None, nombre="Celular de Ana"):
    api = t.api
    cel = cel or t.celular()
    codigo = api.ok(api.post("/api/movil/codigo"))["codigo"]
    r = cel.post("/api/movil/vincular", {"codigo": codigo, "nombre": nombre})
    assert r.status_code == 200, r.text
    cel.llave = r.json()["token"]
    return cel


def entrar(cel, usuario="admin", clave="secreto1"):
    r = cel.post("/api/auth/login", {"usuario": usuario, "password": clave})
    if r.status_code == 200:
        cel.sesion = r.json()["token"]
    return r


def test_apagado_por_defecto(red):
    r = red.celular().get("/api/movil/info")
    assert r.status_code == 403 and r.json()["codigo"] == "MOVIL_APAGADO"
    # no se puede pedir un código con el acceso apagado
    assert red.api.post("/api/movil/codigo").json()["codigo"] == "MOVIL_APAGADO"


def test_solo_red_local_y_solo_por_direccion_ip(red):
    activar(red)
    assert red.celular().get("/api/movil/info").status_code == 200
    r = red.celular(ip="8.8.8.8").get("/api/movil/info")                 # desde internet
    assert r.status_code == 403 and "red local" in r.json()["detalle"]
    assert red.celular(host="pos.example.com").get("/api/movil/info").status_code == 403   # nombre de servidor: rebinding
    assert red.celular(host="8.8.8.8").get("/api/movil/info").status_code == 403
    assert red.celular(host="10.0.0.5", ip="10.0.0.9").get("/api/movil/info").json()["ok"] is True


def test_la_ventana_del_computador_sigue_igual(red):
    """El puerto normal no cambia: Host local, sin llaves de celular."""
    assert red.api.get("/api/salud").status_code == 200
    ajeno = TestClient(red.app, base_url="http://192.168.1.20:8765")
    assert ajeno.get("/api/salud").status_code == 403


def test_activar_pide_ser_administrador_y_queda_auditado(red):
    api = red.api
    api.login("carlos", "cajero1")
    assert api.post("/api/movil/habilitar", {"habilitado": True}).status_code == 403
    api.token = red.admin_token
    activar(red)
    est = api.ok(api.get("/api/movil/estado"))
    assert est["habilitado"] is True and est["direcciones"] == [IP_PC] and est["puerto"] == config.PUERTO_MOVIL
    api.ok(api.post("/api/movil/habilitar", {"habilitado": False}))
    assert api.ok(api.get("/api/movil/estado"))["habilitado"] is False
    acciones = [a["accion"] for a in api.ok(api.get("/api/auditoria"))["filas"]]
    assert "MOVIL_ACTIVADO" in acciones and "MOVIL_APAGADO" in acciones


def test_sin_llave_no_hay_api_pero_si_las_pantallas(red):
    activar(red)
    cel = red.celular()
    r = cel.get("/api/productos")
    assert r.status_code == 401 and r.json()["codigo"] == "DISPOSITIVO_NO_VINCULADO"
    assert cel.get("/", llave=False).status_code == 307 and cel.get("/", llave=False).headers["location"] == "/m/"
    assert cel.get("/css/app.css").status_code == 404       # la interfaz del computador no se sirve por aquí
    assert cel.get("/api/docs").status_code == 403


def test_vincular_con_codigo_de_un_solo_uso(red):
    activar(red)
    api = red.api
    c = api.ok(api.post("/api/movil/codigo"))
    assert len(c["codigo"]) == 6 and c["codigo"].isdigit() and c["vigencia_s"] == 300
    assert c["url"] == f"http://{IP_PC}:{config.PUERTO_MOVIL}" and c["qrs"][0]["svg"].startswith("<svg")
    cel = red.celular()
    r = cel.post("/api/movil/vincular", {"codigo": c["codigo"], "nombre": "Celular de Ana"})
    assert r.status_code == 200 and r.json()["dispositivo"]["nombre"] == "Celular de Ana" and r.json()["api"] == config.API_MOVIL
    llave = r.json()["token"]
    assert len(llave) >= 40
    # el mismo código no sirve dos veces
    assert red.celular().post("/api/movil/vincular", {"codigo": c["codigo"]}).json()["codigo"] == "CODIGO_VENCIDO"
    # la lista del computador no muestra la llave
    lista = api.ok(api.get("/api/movil/estado"))["dispositivos"]
    assert [d["nombre"] for d in lista] == ["Celular de Ana"] and llave not in json.dumps(lista)


def test_codigo_incorrecto_vencido_y_fuerza_bruta(red, monkeypatch):
    activar(red)
    api = red.api
    c = api.ok(api.post("/api/movil/codigo"))["codigo"]
    mal = "000000" if c != "000000" else "111111"
    cel = red.celular()
    for i in range(4):
        r = cel.post("/api/movil/vincular", {"codigo": mal})
        assert r.status_code == 403 and r.json()["codigo"] == "CODIGO_INCORRECTO"
    r = cel.post("/api/movil/vincular", {"codigo": mal})
    assert r.json()["codigo"] == "CODIGO_ANULADO"                         # 5 fallos: el código se invalida, aunque se acierte después
    assert red.celular(ip="192.168.1.60").post("/api/movil/vincular", {"codigo": c}).json()["codigo"] == "CODIGO_VENCIDO"   # otro celular: ya no sirve
    # la dirección que falló 5 veces queda bloqueada un rato, aunque ahora acierte con un código nuevo
    c2 = api.ok(api.post("/api/movil/codigo"))["codigo"]
    r = cel.post("/api/movil/vincular", {"codigo": c2})
    assert r.status_code == 429 and r.json()["codigo"] == "BLOQUEADO"
    # otro celular sí puede, y el código vence a los 5 minutos
    c3 = api.ok(api.post("/api/movil/codigo"))["codigo"]
    ahora = svc._reloj()
    monkeypatch.setattr(svc, "_reloj", lambda: ahora + 301)
    assert red.celular(ip="192.168.1.77").post("/api/movil/vincular", {"codigo": c3}).json()["codigo"] == "CODIGO_VENCIDO"


def test_celular_vinculado_entra_solo_como_administrador(red):
    activar(red)
    cel = vincular(red)
    assert entrar(cel, "carlos", "cajero1").json()["codigo"] == "SOLO_ADMIN_MOVIL"      # el cajero no obtiene sesión
    assert cel.sesion is None
    r = entrar(cel)
    assert r.status_code == 200 and r.json()["usuario"]["rol"] == "admin"
    p = cel.get("/api/productos/codigo/7701").json()
    assert p["nombre"] == "Leche 1 L" and p["unidad"] == "u"
    # sin la llave del celular la sesión no sirve en la red local, aunque sea válida
    assert cel.get("/api/auth/yo", llave=False).status_code == 401
    # una sesión de cajero (obtenida en el computador) tampoco sirve por el celular
    red.api.login("carlos", "cajero1")
    cel.sesion = red.api.token
    r = cel.get("/api/auth/yo")
    assert r.status_code == 403 and r.json()["codigo"] == "SOLO_ADMIN_MOVIL"


def test_el_celular_solo_ve_la_api_reducida(red):
    activar(red)
    cel = vincular(red)
    entrar(cel)
    permitidas = ["/api/catalogos", "/api/config", "/api/turnos/actual", "/api/productos", "/api/productos/rapidos", "/api/compras",
                  "/api/conteos", "/api/dashboard", "/api/inventario/alertas", "/api/ventas"]
    for ruta in permitidas:
        assert cel.get(ruta).status_code == 200, ruta
    bloqueadas = [("GET", "/api/respaldos"), ("GET", "/api/usuarios"), ("POST", "/api/usuarios"), ("PUT", "/api/config"),
                  ("GET", "/api/auditoria"), ("POST", "/api/ventas/1/anular"), ("POST", "/api/ventas/1/devolucion"),
                  ("POST", "/api/respaldos/restaurar"), ("POST", "/api/sistema/actualizaciones/instalar"),
                  ("POST", "/api/productos"), ("PUT", "/api/productos/1"), ("POST", "/api/inventario/ajustes"),
                  ("POST", "/api/conteos/1/aplicar"), ("POST", "/api/turnos/abrir"), ("POST", "/api/cajon/abrir"),
                  ("GET", "/api/movil/estado"), ("POST", "/api/movil/habilitar"), ("POST", "/api/movil/codigo")]
    for metodo, ruta in bloqueadas:
        r = cel.pedir(metodo, ruta, {} if metodo != "GET" else None)
        assert r.status_code == 403 and r.json()["codigo"] == "SOLO_EN_EL_COMPUTADOR", (metodo, ruta, r.text)


def test_desvincular_un_celular_lo_deja_sin_acceso(red):
    activar(red)
    cel = vincular(red)
    entrar(cel)
    assert cel.get("/api/productos").status_code == 200
    did = red.api.ok(red.api.get("/api/movil/estado"))["dispositivos"][0]["id"]
    assert cel.delete(f"/api/movil/dispositivos/{did}").status_code == 403          # solo desde el computador
    red.api.ok(red.api.delete(f"/api/movil/dispositivos/{did}"))
    r = cel.get("/api/productos")
    assert r.status_code == 401 and r.json()["codigo"] == "DISPOSITIVO_NO_VINCULADO"
    assert red.api.ok(red.api.get("/api/movil/estado"))["dispositivos"] == []
    assert red.api.delete(f"/api/movil/dispositivos/{did}").status_code == 404
    acciones = [a["accion"] for a in red.api.ok(red.api.get("/api/auditoria"))["filas"]]
    assert "MOVIL_VINCULADO" in acciones and "MOVIL_REVOCADO" in acciones


def test_registra_el_ultimo_uso_del_celular(red, monkeypatch):
    activar(red)
    cel = vincular(red, nombre="Bodega")
    monkeypatch.setattr(svc, "_ultimo_registro", {})
    cel.get("/api/productos")
    d = red.api.ok(red.api.get("/api/movil/estado"))["dispositivos"][0]
    assert d["ultima_ip"] == IP_CEL and d["ultimo_uso"]


def test_se_limita_la_cantidad_de_celulares(red, monkeypatch):
    activar(red)
    monkeypatch.setattr(svc, "MAX_DISPOSITIVOS", 2)
    vincular(red, nombre="Uno"); vincular(red, nombre="Dos")
    codigo = red.api.ok(red.api.post("/api/movil/codigo"))["codigo"]
    r = red.celular().post("/api/movil/vincular", {"codigo": codigo})
    assert r.status_code == 409 and r.json()["codigo"] == "MUCHOS_DISPOSITIVOS"


def test_cors_solo_para_la_app_del_celular(red):
    activar(red)
    cel = red.celular()
    pre = cel.c.options("/api/productos", headers={"Origin": "http://localhost", "Access-Control-Request-Method": "GET",
                                                    "Access-Control-Request-Headers": "x-dispositivo,authorization"})
    assert pre.status_code == 200 and pre.headers["access-control-allow-origin"] == "http://localhost"
    ajeno = cel.c.options("/api/productos", headers={"Origin": "https://sitio-malo.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in ajeno.headers


def test_el_contenido_del_qr(red):
    j = json.loads(svc.contenido_qr(IP_PC, "123456", "Súper Ñandú"))
    assert j == {"pos": config.API_MOVIL, "url": f"http://{IP_PC}:{config.PUERTO_MOVIL}", "codigo": "123456", "negocio": "Súper Ñandú"}


def test_direcciones_locales_solo_red_privada():
    for ip in svc.direcciones_locales():
        assert svc._es_red_local(ip) and not ip.startswith(("127.", "169.254."))
    assert svc._es_red_local("192.168.0.5") and svc._es_red_local("10.1.2.3") and svc._es_red_local("172.20.1.1")
    assert not svc._es_red_local("8.8.8.8") and not svc._es_red_local("172.32.0.1") and not svc._es_red_local("basura")


def test_servidor_real_para_celulares(red, monkeypatch):
    """El segundo servidor de verdad: arranca en su puerto, aplica las reglas y se detiene."""
    from app import db as db_mod
    monkeypatch.undo()                        # esta prueba usa el servidor real (sin los falsos de la fixture)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        puerto = s.getsockname()[1]
    monkeypatch.setattr(config, "PUERTO_MOVIL", puerto)
    monkeypatch.setattr(config, "HOST_MOVIL", "127.0.0.1")
    s = db_mod.nueva_sesion(escritura=True)
    core.cfg_set(s, "acceso_movil", "1")
    s.commit(); s.close()
    srv = svc.ServidorMovil()
    srv.iniciar(red.app)
    try:
        assert srv.activo
        base = f"http://127.0.0.1:{puerto}"
        info = json.loads(urllib.request.urlopen(base + "/api/movil/info", timeout=5).read())
        assert info["ok"] and info["api"] == config.API_MOVIL
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(base + "/api/productos", timeout=5)
        assert e.value.code == 401
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(urllib.request.Request(base + "/api/respaldos", headers={"X-Dispositivo": "x"}), timeout=5)
        assert e.value.code == 403
        # un puerto ocupado se explica
        otro = svc.ServidorMovil()
        with pytest.raises(core.ErrorNegocio) as err:
            otro.iniciar(red.app)
        assert err.value.codigo == "PUERTO_OCUPADO"
    finally:
        srv.detener()
    assert not srv.activo
    with pytest.raises(OSError):
        urllib.request.urlopen(f"http://127.0.0.1:{puerto}/api/movil/info", timeout=2)
