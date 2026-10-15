"""Configuración del negocio y catálogos: categorías, proveedores, impuestos, medios de pago, clientes."""
from __future__ import annotations

import re

from fastapi import APIRouter
from sqlalchemy import func, or_, select

from .. import models as m
from ..core import CLAVES_PUBLICAS, DEFECTOS, ErrorNegocio, auditar, cfg, cfg_set, denominaciones
from ..deps import DB, DBW, Admin, Usuario
from ..schemas import (CategoriaIn, ClienteIn, ConfigIn, ImpuestoIn, MedioPagoIn, ProveedorIn)
from ..services import caja as caja_svc

router = APIRouter(prefix="/api")

# claves editables desde la pantalla de configuración (el consecutivo de ventas no se edita a mano)
EDITABLES = set(DEFECTOS) - {"consecutivo_venta"}
MODOS_CAJON = {"ninguno", "serial", "escpos_archivo", "escpos_windows"}


def _config_dict(db, admin: bool) -> dict:
    claves = EDITABLES | {"consecutivo_venta"} if admin else CLAVES_PUBLICAS
    d = {k: cfg(db, k) for k in sorted(claves)}
    d["denominaciones_lista"] = denominaciones(db)
    return d


@router.get("/config")
def leer_config(u: Usuario, db: DB):
    return _config_dict(db, u.rol == "admin")


@router.put("/config")
def guardar_config(body: ConfigIn, adm: Admin, db: DBW):
    antes = {}
    for k, v in body.valores.items():
        if k not in EDITABLES:
            raise ErrorNegocio(f"Ajuste desconocido: {k}")
        v = ("1" if v else "0") if isinstance(v, bool) else str(v).strip()
        if k == "cajon_modo" and v not in MODOS_CAJON:
            raise ErrorNegocio("Modo de cajón no válido.")
        if k == "respaldo_hora" and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v):
            raise ErrorNegocio("La hora del respaldo debe tener el formato HH:MM.")
        if k == "denominaciones":
            try:
                if not [int(x) for x in v.split(",") if x.strip()]:
                    raise ValueError
            except ValueError:
                raise ErrorNegocio("Las denominaciones deben ser números separados por comas.")
        if k in ("descuento_max_pct_cajero", "bloqueo_minutos", "respaldo_alerta_dias", "dias_cobertura_sugerido",
                 "conteo_recordatorio_dias"):
            if not re.fullmatch(r"\d+", v) or (k == "descuento_max_pct_cajero" and int(v) > 100):
                raise ErrorNegocio(f"Valor no válido para {k}.")
        if k == "negocio_logo" and len(v) > 400_000:
            raise ErrorNegocio("El logo es demasiado grande (máximo ~300 KB).")
        antes[k] = cfg(db, k) if k != "negocio_logo" else "…"
        cfg_set(db, k, v)
    auditar(db, adm.id, "CONFIG_CAMBIADA", "configuracion", antes={k: v for k, v in antes.items()},
            despues={k: ("…" if k == "negocio_logo" else v) for k, v in body.valores.items()})
    db.commit()
    return _config_dict(db, True)


# ───────────────────────────── Catálogos ─────────────────────────────
def _cat(c): return {"id": c.id, "nombre": c.nombre, "padre_id": c.padre_id}
def _prov(p): return {"id": p.id, "nombre": p.nombre, "nit": p.nit, "telefono": p.telefono, "email": p.email, "contacto": p.contacto, "activo": p.activo}
def _imp(i): return {"id": i.id, "nombre": i.nombre, "tipo": i.tipo, "tarifa_pct": i.tarifa_pct, "valor_fijo": i.valor_fijo, "activo": i.activo}
def _med(x): return {"id": x.id, "nombre": x.nombre, "tipo": x.tipo, "requiere_referencia": x.requiere_referencia, "activo": x.activo, "orden": x.orden}


@router.get("/catalogos")
def catalogos(_: Usuario, db: DB):
    """Todo lo que la interfaz necesita al iniciar, en una sola llamada."""
    caja = caja_svc.caja_principal(db)
    return {
        "categorias": [_cat(c) for c in db.scalars(select(m.Categoria).order_by(m.Categoria.nombre))],
        "proveedores": [_prov(p) for p in db.scalars(select(m.Proveedor).order_by(m.Proveedor.nombre))],
        "impuestos": [_imp(i) for i in db.scalars(select(m.Impuesto).order_by(m.Impuesto.id))],
        "medios_pago": [_med(x) for x in db.scalars(select(m.MedioPago).order_by(m.MedioPago.orden, m.MedioPago.id))],
        "caja": {"id": caja.id, "nombre": caja.nombre},
    }


@router.post("/categorias")
def crear_categoria(body: CategoriaIn, adm: Admin, db: DBW):
    nombre = body.nombre.strip()
    if not nombre:
        raise ErrorNegocio("Escriba el nombre de la categoría.")
    if db.scalar(select(m.Categoria.id).where(func.lower(m.Categoria.nombre) == nombre.lower(), m.Categoria.padre_id.is_(body.padre_id))):
        raise ErrorNegocio("Ya existe esa categoría.", 409)
    c = m.Categoria(nombre=nombre, padre_id=body.padre_id)
    db.add(c)
    db.flush()
    db.commit()
    return _cat(c)


@router.put("/categorias/{cid}")
def editar_categoria(cid: int, body: CategoriaIn, adm: Admin, db: DBW):
    c = db.get(m.Categoria, cid)
    if not c:
        raise ErrorNegocio("Categoría no encontrada.", 404)
    if body.padre_id == c.id:
        raise ErrorNegocio("Una categoría no puede ser hija de sí misma.")
    c.nombre, c.padre_id = body.nombre.strip() or c.nombre, body.padre_id
    db.commit()
    return _cat(c)


@router.delete("/categorias/{cid}")
def borrar_categoria(cid: int, adm: Admin, db: DBW):
    c = db.get(m.Categoria, cid)
    if not c:
        raise ErrorNegocio("Categoría no encontrada.", 404)
    if db.scalar(select(func.count()).select_from(m.Producto).where(m.Producto.categoria_id == cid)) or \
            db.scalar(select(func.count()).select_from(m.Categoria).where(m.Categoria.padre_id == cid)):
        raise ErrorNegocio("La categoría tiene productos o subcategorías; muévalos antes de borrarla.", 409)
    db.delete(c)
    db.commit()
    return {"ok": True}


@router.post("/proveedores")
def crear_proveedor(body: ProveedorIn, adm: Admin, db: DBW):
    if not (body.nombre or "").strip():
        raise ErrorNegocio("Escriba el nombre del proveedor.")
    if db.scalar(select(m.Proveedor.id).where(func.lower(m.Proveedor.nombre) == body.nombre.strip().lower())):
        raise ErrorNegocio("Ya existe un proveedor con ese nombre.", 409)
    p = m.Proveedor(nombre=body.nombre.strip(), nit=body.nit, telefono=body.telefono, email=body.email,
                    contacto=body.contacto, activo=True)
    db.add(p)
    db.flush()
    db.commit()
    return _prov(p)


@router.put("/proveedores/{pid}")
def editar_proveedor(pid: int, body: ProveedorIn, adm: Admin, db: DBW):
    p = db.get(m.Proveedor, pid)
    if not p:
        raise ErrorNegocio("Proveedor no encontrado.", 404)
    for k, v in body.model_dump(exclude_unset=True).items():
        if k == "nombre" and not (v or "").strip():
            continue
        setattr(p, k, v)
    db.commit()
    return _prov(p)


@router.post("/impuestos")
def crear_impuesto(body: ImpuestoIn, adm: Admin, db: DBW):
    if not (body.nombre or "").strip():
        raise ErrorNegocio("Escriba el nombre del impuesto.")
    if db.scalar(select(m.Impuesto.id).where(func.lower(m.Impuesto.nombre) == body.nombre.strip().lower())):
        raise ErrorNegocio("Ya existe un impuesto con ese nombre.", 409)
    i = m.Impuesto(nombre=body.nombre.strip(), tipo=body.tipo or "IVA", tarifa_pct=body.tarifa_pct or 0,
                   valor_fijo=body.valor_fijo or 0, activo=True)
    db.add(i)
    db.flush()
    auditar(db, adm.id, "IMPUESTO_CREADO", "impuesto", i.id, despues=_imp(i))
    db.commit()
    return _imp(i)


@router.put("/impuestos/{iid}")
def editar_impuesto(iid: int, body: ImpuestoIn, adm: Admin, db: DBW):
    i = db.get(m.Impuesto, iid)
    if not i:
        raise ErrorNegocio("Impuesto no encontrado.", 404)
    antes = _imp(i)
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(i, k, v)
    auditar(db, adm.id, "IMPUESTO_EDITADO", "impuesto", i.id, antes=antes, despues=_imp(i))
    db.commit()
    return _imp(i)


@router.post("/medios-pago")
def crear_medio(body: MedioPagoIn, adm: Admin, db: DBW):
    if not (body.nombre or "").strip() or body.tipo not in ("efectivo", "banco"):
        raise ErrorNegocio("Indique el nombre y el tipo (efectivo o banco).")
    if body.tipo == "efectivo" and db.scalar(select(m.MedioPago.id).where(m.MedioPago.tipo == "efectivo", m.MedioPago.activo.is_(True))):
        raise ErrorNegocio("Ya existe un medio de pago en efectivo activo.", 409)
    if db.scalar(select(m.MedioPago.id).where(func.lower(m.MedioPago.nombre) == body.nombre.strip().lower())):
        raise ErrorNegocio("Ya existe un medio de pago con ese nombre.", 409)
    x = m.MedioPago(nombre=body.nombre.strip(), tipo=body.tipo, requiere_referencia=bool(body.requiere_referencia),
                    activo=True, orden=body.orden or 99)
    db.add(x)
    db.flush()
    db.commit()
    return _med(x)


@router.put("/medios-pago/{mid}")
def editar_medio(mid: int, body: MedioPagoIn, adm: Admin, db: DBW):
    x = db.get(m.MedioPago, mid)
    if not x:
        raise ErrorNegocio("Medio de pago no encontrado.", 404)
    datos = body.model_dump(exclude_unset=True)
    datos.pop("tipo", None)  # el tipo no cambia: afecta el arqueo de turnos ya vendidos
    if datos.get("activo") is False and x.tipo == "efectivo":
        raise ErrorNegocio("El pago en efectivo no se puede desactivar.", 409)
    for k, v in datos.items():
        if v is not None:
            setattr(x, k, v)
    db.commit()
    return _med(x)


# ───────────────────────────── Clientes ─────────────────────────────
@router.get("/clientes")
def buscar_clientes(_: Usuario, db: DB, q: str = ""):
    qry = select(m.Cliente).order_by(m.Cliente.nombre).limit(30)
    if q.strip():
        like = f"%{q.strip()}%"
        qry = qry.where(or_(m.Cliente.nombre.ilike(like), m.Cliente.numero_documento.like(like)))
    return [{"id": c.id, "nombre": c.nombre, "documento": f"{c.tipo_documento} {c.numero_documento}",
             "email": c.email, "telefono": c.telefono} for c in db.scalars(qry)]


@router.post("/clientes")
def crear_cliente(body: ClienteIn, _: Usuario, db: DBW):
    if not body.nombre.strip() or not body.numero_documento.strip():
        raise ErrorNegocio("Indique nombre y documento del cliente.")
    existente = db.scalars(select(m.Cliente).where(m.Cliente.tipo_documento == body.tipo_documento,
                                                   m.Cliente.numero_documento == body.numero_documento.strip())).first()
    if existente:
        raise ErrorNegocio("Ya existe un cliente con ese documento.", 409)
    c = m.Cliente(tipo_documento=body.tipo_documento, numero_documento=body.numero_documento.strip(),
                  nombre=body.nombre.strip(), email=body.email, telefono=body.telefono)
    db.add(c)
    db.flush()
    db.commit()
    return {"id": c.id, "nombre": c.nombre, "documento": f"{c.tipo_documento} {c.numero_documento}"}
