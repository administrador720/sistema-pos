from __future__ import annotations

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import select

from .. import models as m
from ..core import ErrorNegocio
from ..deps import DB, DBW, Admin, Usuario
from ..schemas import PreciosMasivoIn, ProductoIn
from ..services import productos as svc

router = APIRouter(prefix="/api/productos")


CAMPOS_DE_COSTO = ("costo_promedio", "margen_pct", "proveedor_id", "proveedor")


def sin_costos(d: dict, usuario) -> dict:
    """El costo, el margen y el proveedor son información del administrador: el cajero no los recibe."""
    if usuario.rol != "admin":
        for k in CAMPOS_DE_COSTO:
            d.pop(k, None)
    return d


@router.get("")
def listar(u: Usuario, db: DB, q: str = "", categoria_id: int | None = None, proveedor_id: int | None = None,
           estado: str = "activos", bajo_minimo: bool = False, limite: int = Query(100, le=500), offset: int = 0):
    r = svc.buscar(db, q, categoria_id=categoria_id, proveedor_id=proveedor_id, estado=estado,
                   bajo_minimo=bajo_minimo, limite=limite, offset=offset)
    r["productos"] = [sin_costos(p, u) for p in r["productos"]]
    return r


@router.get("/codigo/{codigo}")
def por_codigo(codigo: str, _: Usuario, db: DB):
    """Búsqueda por lector de barras: devuelve el producto y cuántas unidades representa el código."""
    r = svc.por_codigo(db, codigo)
    if not r:
        raise ErrorNegocio(f"El código {codigo} no existe.", 404, "CODIGO_NO_EXISTE")
    p, unidades = r
    if not p.activo:
        raise ErrorNegocio(f"«{p.nombre}» está inactivo.", 409, "PRODUCTO_INACTIVO")
    return {**svc.serializar(p, completo=False), "unidades_por_codigo": unidades}


@router.get("/rapidos")
def rapidos(u: Usuario, db: DB):
    """Botones de acceso rápido de la caja (verduras y frutas de todos los días)."""
    return [sin_costos(p, u) for p in svc.rapidos(db)]


@router.get("/plantilla")
def plantilla(_: Admin):
    return Response(svc.plantilla_xlsx(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="plantilla-productos.xlsx"'})


@router.post("/importar")
def importar(adm: Admin, db: DBW, archivo: UploadFile = File(...), simular: bool = True):
    contenido = archivo.file.read()
    if len(contenido) > 15_000_000:
        raise ErrorNegocio("El archivo es demasiado grande (máximo 15 MB).")
    r = svc.importar(db, adm, archivo.filename or "", contenido, simular=simular)
    if simular:
        db.rollback()
    else:
        db.commit()
    return r


@router.post("/precios-masivo")
def precios_masivo(body: PreciosMasivoIn, adm: Admin, db: DBW):
    r = svc.cambio_masivo_precios(db, adm, porcentaje=body.porcentaje, categoria_id=body.categoria_id,
                                  proveedor_id=body.proveedor_id, redondeo=body.redondeo, simular=body.simular)
    if body.simular:
        db.rollback()
    else:
        db.commit()
    return r


@router.get("/{pid}")
def obtener(pid: int, u: Usuario, db: DB):
    p = db.scalars(select(m.Producto).where(m.Producto.id == pid).options(*svc._opciones())).first()
    if not p:
        raise ErrorNegocio("Producto no encontrado.", 404)
    return sin_costos(svc.serializar(p), u)


@router.post("")
def crear(body: ProductoIn, adm: Admin, db: DBW):
    datos = body.model_dump(exclude_unset=True)
    if "codigos" in datos:
        datos["codigos"] = [c.model_dump() if hasattr(c, "model_dump") else c for c in datos["codigos"] or []]
    p = svc.crear(db, adm, datos)
    db.commit()
    return svc.serializar(db.scalars(select(m.Producto).where(m.Producto.id == p.id).options(*svc._opciones())).one())


@router.put("/{pid}")
def actualizar(pid: int, body: ProductoIn, adm: Admin, db: DBW):
    datos = body.model_dump(exclude_unset=True)
    datos.pop("stock_inicial", None)  # el stock solo cambia con movimientos
    p = svc.actualizar(db, adm, pid, datos)
    db.commit()
    return svc.serializar(p)


@router.get("/{pid}/historial-precios")
def historial(pid: int, _: Admin, db: DB):
    return svc.historial_precios(db, pid)
