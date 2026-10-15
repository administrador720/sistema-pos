"""Dashboard e informes (con exportación a Excel y PDF)."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import Response

from .. import db as db_mod
from ..core import cfg, hoy
from ..deps import DB, Admin
from ..services import exportacion, reportes as svc
from ..services import inventario as inv
from ..services import respaldos as respaldos_svc

router = APIRouter(prefix="/api")

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _preparar_fotos(desde: date, hasta: date):
    """Completa las fotos diarias que falten en una transacción de escritura corta e independiente."""
    desde = max(desde, hasta - timedelta(days=120))
    s = db_mod.nueva_sesion(escritura=True)
    try:
        inv.asegurar_fotos(s, desde, hasta)
        s.commit()
    finally:
        s.close()


@router.get("/dashboard")
def dashboard(_: Admin, db: DB, desde: date | None = None, hasta: date | None = None):
    r = svc.dashboard(db, desde, hasta)
    r["respaldo"] = respaldos_svc.estado(db)
    return r


@router.get("/informes")
def catalogo(_: Admin):
    return svc.catalogo_publico()


@router.get("/informes/{slug}")
def informe(slug: str, request: Request, _: Admin, db: DB, desde: date | None = None, hasta: date | None = None,
            formato: str = "json", guardar: bool = False):
    params = {k: v for k, v in request.query_params.items() if k not in ("desde", "hasta", "formato", "guardar")}
    if slug == "rotacion":
        d, h = svc.rango(desde, hasta)
        _preparar_fotos(d, h)
    r = svc.generar(db, slug, desde, hasta, params)
    if formato == "json":
        return r
    negocio = cfg(db, "negocio_nombre")
    if formato == "xlsx":
        contenido, tipo, ext = exportacion.a_xlsx(r, negocio), XLSX, "xlsx"
    elif formato == "pdf":
        contenido, tipo, ext = exportacion.a_pdf(r, negocio), "application/pdf", "pdf"
    else:
        return Response("Formato no válido", status_code=400)
    nombre = f"{slug}-{hoy():%Y%m%d}.{ext}"
    if guardar:  # desde la ventana de escritorio: se guarda en Documentos/POS Supermercado/Exportes
        return {"ruta": exportacion.guardar_en_exportes(nombre, contenido), "nombre": nombre}
    return Response(contenido, media_type=tipo, headers={"Content-Disposition": f'attachment; filename="{nombre}"'})
