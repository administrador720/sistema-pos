"""Aplicación FastAPI: API local + interfaz web estática."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, db, jobs
from .core import ErrorNegocio
from .routers import auth, caja, catalogos, conteos, inventario, productos, reportes, sistema, ventas

log = logging.getLogger("pos")


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    if db.engine is None:
        db.configurar()
    db.inicializar()
    jobs.iniciar()
    yield
    jobs.detener()


app = FastAPI(title=config.NOMBRE_APP, version=config.VERSION, lifespan=ciclo_de_vida,
              docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")

for r in (auth, catalogos, productos, caja, ventas, inventario, conteos, reportes, sistema):
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
async def _solo_local(request: Request, call_next):
    """Defensa contra DNS-rebinding: solo se atiende si el Host es la propia máquina."""
    host = (request.headers.get("host") or "").split(":")[0].lower()
    if host not in ("127.0.0.1", "localhost", "[::1]", "testserver"):
        return JSONResponse({"detalle": "Acceso no permitido."}, status_code=403)
    resp = await call_next(request)
    if request.url.path.startswith("/api"):
        resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


# ───────────────────────────── Interfaz ─────────────────────────────
_front = config.dir_frontend()


@app.get("/", include_in_schema=False)
def inicio():
    return FileResponse(_front / "index.html", headers={"Cache-Control": "no-cache"})


if _front.exists():
    app.mount("/", StaticFiles(directory=_front), name="frontend")
