"""Aplicación FastAPI: API local + interfaz web estática."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware

from . import config, db, jobs
from .core import ErrorNegocio
from .routers import auth, caja, catalogos, conteos, inventario, movil, productos, reportes, sistema, ventas
from .services import movil as movil_svc

log = logging.getLogger("pos")


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    if db.engine is None:
        db.configurar()
    db.inicializar()
    jobs.iniciar()
    if not os.environ.get("POS_SIN_RED_MOVIL"):
        s = db.nueva_sesion()
        try:
            quiere_movil = movil_svc.habilitado(s)
        finally:
            s.close()
        if quiere_movil:  # el administrador lo había activado: se reanuda al abrir el programa
            try:
                movil_svc.servidor.iniciar(app)
            except Exception as e:  # noqa: BLE001 - un puerto ocupado no debe impedir abrir el programa
                log.warning("No se pudo reanudar el servidor de celulares: %s", e)
    yield
    movil_svc.servidor.detener()
    jobs.detener()


app = FastAPI(title=config.NOMBRE_APP, version=config.VERSION, lifespan=ciclo_de_vida,
              docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")

for r in (auth, catalogos, productos, caja, ventas, inventario, conteos, reportes, sistema, movil):
    app.include_router(r.router)


# ───────────────────────────── Errores ─────────────────────────────
@app.exception_handler(ErrorNegocio)
async def _error_negocio(_: Request, e: ErrorNegocio):
    return JSONResponse({"detalle": e.detalle, "codigo": e.codigo}, status_code=e.status)


@app.exception_handler(RequestValidationError)
async def _error_validacion(_: Request, e: RequestValidationError):
    campos = ", ".join(".".join(str(x) for x in err["loc"][1:]) or "?" for err in e.errors()[:4])
    return JSONResponse({"detalle": f"Datos no válidos ({campos}). Revise lo digitado.", "codigo": "VALIDACION"}, status_code=422)


@app.exception_handler(Exception)
async def _error_inesperado(_: Request, e: Exception):
    log.exception("Error no controlado")
    return JSONResponse({"detalle": "Ocurrió un error inesperado. La operación no se guardó.", "codigo": "ERROR"},
                        status_code=500)


# ───────────────────────────── Seguridad básica ─────────────────────────────
@app.middleware("http")
async def _control_de_acceso(request: Request, call_next):
    """Dos puertas: la de este computador (solo Host local, contra DNS-rebinding) y la de los celulares (red local,
    celulares vinculados y API reducida; ver services/movil.py)."""
    puerto = (request.scope.get("server") or (None, None))[1]
    if puerto == config.PUERTO_MOVIL and puerto != config.PUERTO:
        rechazo = await run_in_threadpool(movil_svc.controlar_acceso, request)
        if rechazo:
            status, detalle, codigo = rechazo
            return JSONResponse({"detalle": detalle, "codigo": codigo}, status_code=status)
        if request.url.path == "/":
            return RedirectResponse("/m/")
    else:
        host = (request.headers.get("host") or "").split(":")[0].lower()
        if host not in ("127.0.0.1", "localhost", "[::1]", "testserver"):
            return JSONResponse({"detalle": "Acceso no permitido."}, status_code=403)
    resp = await call_next(request)
    if request.url.path.startswith("/api"):
        resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


# La app del celular dentro de un WebView (Capacitor) llama a la API desde otro origen; solo esos orígenes, y la API
# exige llaves en cabeceras (no cookies), así que no se abre nada a páginas web ajenas.
app.add_middleware(CORSMiddleware, allow_origin_regex=r"^(https?|capacitor|ionic)://localhost(:\d+)?$",
                   allow_methods=["*"], allow_headers=["*"], max_age=600)


# ───────────────────────────── Interfaz ─────────────────────────────
_front = config.dir_frontend()
_movil_web = config.dir_movil()
if _movil_web.exists():
    app.mount("/m", StaticFiles(directory=_movil_web, html=True), name="movil")


@app.get("/", include_in_schema=False)
def inicio():
    return FileResponse(_front / "index.html", headers={"Cache-Control": "no-cache"})


if _front.exists():
    app.mount("/", StaticFiles(directory=_front), name="frontend")
