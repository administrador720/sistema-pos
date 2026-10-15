"""Ventas: cobro atómico (efectivo / banco / mixto), anulaciones, devoluciones y ventas suspendidas."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from .. import models as m
from ..core import (ErrorNegocio, ahora, auditar, autorizar, cfg, cfg_int, cfg_set, desglosar_impuesto,
                    prorratear, redondear)
from . import caja as caja_svc
from . import inventario as inv


# ───────────────────────────── Cobro ─────────────────────────────
def _validar_turno_para_vender(db: Session, usuario: m.Usuario) -> m.Turno:
    turno = caja_svc.turno_abierto(db)
    if not turno:
        raise ErrorNegocio("Debe abrir la caja (turno) antes de vender.", 409, "SIN_TURNO")
    if usuario.rol != "admin" and usuario.id != turno.usuario_id:
        raise ErrorNegocio("El turno abierto pertenece a otro cajero.", 403)
    return turno


def crear_venta(db: Session, usuario: m.Usuario, datos: dict, pin: str | None = None) -> m.Venta:
    turno = _validar_turno_para_vender(db, usuario)
    entradas = datos.get("items") or []
    if not entradas:
        raise ErrorNegocio("La venta no tiene productos.")

    # ── productos y cantidades
    ids = {int(e["producto_id"]) for e in entradas}
    productos = {p.id: p for p in db.scalars(select(m.Producto).where(m.Producto.id.in_(ids))
                                             .options(selectinload(m.Producto.impuesto)))}
    pedido: dict[int, int] = defaultdict(int)
    for e in entradas:
        p = productos.get(int(e["producto_id"]))
        if not p or not p.activo:
            raise ErrorNegocio("Hay un producto inexistente o inactivo en la venta.", 404)
        if int(e["cantidad"]) <= 0:
            raise ErrorNegocio(f"Cantidad no válida para «{p.nombre}».")
        pedido[p.id] += int(e["cantidad"])
    for pid, cant in pedido.items():
        inv.verificar_stock(db, productos[pid], cant)

    # ── líneas: el precio SIEMPRE sale de la base de datos
    lineas = []
    for e in entradas:
        p = productos[int(e["producto_id"])]
        cant = int(e["cantidad"])
        bruto = p.precio_venta * cant
        desc = min(max(int(e.get("descuento") or 0), 0), bruto)
        lineas.append({"p": p, "cant": cant, "bruto": bruto, "desc_linea": desc, "desc_global": 0})

    desc_global = max(int(datos.get("descuento_global") or 0), 0)
    reparto = prorratear(desc_global, [l["bruto"] - l["desc_linea"] for l in lineas])
    for l, r in zip(lineas, reparto):
        l["desc_global"] = r
        l["total"] = l["bruto"] - l["desc_linea"] - r
        imp = l["p"].impuesto
        l["impuesto"] = desglosar_impuesto(l["total"], l["cant"], imp.tarifa_pct if imp else 0,
                                           imp.valor_fijo if imp else 0)

    subtotal = sum(l["bruto"] for l in lineas)
    descuento_total = sum(l["desc_linea"] + l["desc_global"] for l in lineas)
    total = sum(l["total"] for l in lineas)
    impuesto_total = sum(l["impuesto"] for l in lineas)
    if total <= 0:
        raise ErrorNegocio("El total de la venta debe ser mayor a cero.")

    # ── descuentos por encima del límite del cajero requieren autorización
    limite = cfg_int(db, "descuento_max_pct_cajero")
    maximo_pct = max([(l["desc_linea"] + l["desc_global"]) * 100 / l["bruto"] for l in lineas if l["bruto"]] + [0])
    autorizado = None
    if descuento_total and maximo_pct > limite and usuario.rol != "admin":
        autorizado = autorizar(db, usuario, pin, f"Un descuento mayor al {limite}% requiere el PIN del administrador.")

    # ── pagos
    pagos_in = datos.get("pagos") or []
    if not pagos_in:
        raise ErrorNegocio("Indique el medio de pago.")
    medios = {md.id: md for md in db.scalars(select(m.MedioPago).where(
        m.MedioPago.id.in_([int(p["medio_pago_id"]) for p in pagos_in])))}
    pagos, suma, n_efectivo = [], 0, 0
    for pg in pagos_in:
        medio = medios.get(int(pg["medio_pago_id"]))
        if not medio or not medio.activo:
            raise ErrorNegocio("Medio de pago no válido.")
        monto = int(pg["monto"])
        if monto <= 0:
            raise ErrorNegocio("Cada pago debe ser mayor a cero.")
        suma += monto
        referencia = (pg.get("referencia") or "").strip() or None
        if medio.tipo == "efectivo":
            n_efectivo += 1
            recibido = int(pg.get("recibido") or monto)
            if recibido < monto:
                raise ErrorNegocio("El efectivo recibido es menor al valor a pagar.")
            devuelta = recibido - monto
        else:
            recibido, devuelta = monto, 0
            if medio.requiere_referencia and not referencia:
                raise ErrorNegocio(f"{medio.nombre} requiere número de referencia / aprobación.")
        pagos.append((medio, monto, recibido, devuelta, referencia))
    if n_efectivo > 1:
        raise ErrorNegocio("Solo puede haber un pago en efectivo por venta.")
    if suma != total:
        raise ErrorNegocio(f"La suma de los pagos (${suma:,}) no coincide con el total (${total:,}).".replace(",", "."))

    # ── consecutivo sin huecos (si algo falla, el incremento se revierte con la transacción)
    prefijo = cfg(db, "prefijo_venta") or "POS"
    consecutivo = cfg_int(db, "consecutivo_venta") or 1
    cfg_set(db, "consecutivo_venta", str(consecutivo + 1))

    venta = m.Venta(prefijo=prefijo, consecutivo=consecutivo, turno_id=turno.id, usuario_id=usuario.id,
                    cliente_id=datos.get("cliente_id"), fecha=ahora(), subtotal=subtotal,
                    descuento_total=descuento_total, impuesto_total=impuesto_total, total=total)
    db.add(venta)
    db.flush()
    for l in lineas:
        p, imp = l["p"], l["p"].impuesto
        item = m.VentaItem(venta_id=venta.id, producto_id=p.id, descripcion=p.nombre, cantidad=l["cant"],
                           precio_unitario=p.precio_venta, descuento=l["desc_linea"] + l["desc_global"],
                           impuesto_id=imp.id if imp else None, tarifa_pct=imp.tarifa_pct if imp else 0,
                           valor_impuesto=l["impuesto"], total=l["total"], costo_unitario=p.costo_promedio)
        db.add(item)
        inv.registrar_movimiento(db, p, "VENTA", -l["cant"], costo_unitario=p.costo_promedio,
                                 referencia_tipo="venta", referencia_id=venta.id, usuario_id=usuario.id)
    for medio, monto, recibido, devuelta, referencia in pagos:
        db.add(m.VentaPago(venta_id=venta.id, medio_pago_id=medio.id, monto=monto, recibido=recibido,
                           devuelta=devuelta, referencia=referencia))
    if autorizado:
        auditar(db, usuario.id, "DESCUENTO_AUTORIZADO", "venta", venta.id,
                despues={"descuento": descuento_total, "pct_max": round(maximo_pct, 1)},
                autorizado_por=autorizado.id)
    db.flush()
    db.refresh(venta)
    return venta


def tiene_efectivo(venta: m.Venta) -> bool:
    return any(p.medio.tipo == "efectivo" for p in venta.pagos)


# ───────────────────────────── Anulación ─────────────────────────────
def anular_venta(db: Session, usuario: m.Usuario, venta_id: int, motivo: str, pin: str | None = None) -> m.Venta:
    v = db.get(m.Venta, venta_id)
    if not v:
        raise ErrorNegocio("Venta no encontrada.", 404)
    if v.estado != "completada":
        raise ErrorNegocio("La venta ya está anulada.", 409)
    if not (motivo or "").strip():
        raise ErrorNegocio("Escriba el motivo de la anulación.")
    turno = caja_svc.turno_abierto(db)
    if not turno or v.turno_id != turno.id:
        raise ErrorNegocio("Solo se pueden anular ventas del turno abierto. Para ventas de turnos anteriores "
                           "use una devolución.", 409, "FUERA_DE_TURNO")
    if db.scalar(select(func.count()).select_from(m.Devolucion).where(m.Devolucion.venta_id == v.id)):
        raise ErrorNegocio("La venta tiene devoluciones; no se puede anular.", 409)
    autoriza = autorizar(db, usuario, pin, "Anular una venta requiere el PIN del administrador.")
    for it in v.items:
        p = db.get(m.Producto, it.producto_id)
        inv.registrar_movimiento(db, p, "ANULACION_VENTA", it.cantidad, costo_unitario=it.costo_unitario,
                                 referencia_tipo="venta", referencia_id=v.id, usuario_id=usuario.id,
                                 nota=motivo.strip())
    v.estado = "anulada"
    v.anulada_por = usuario.id
    v.anulada_en = ahora()
    v.motivo_anulacion = motivo.strip()
    auditar(db, usuario.id, "ANULACION_VENTA", "venta", v.id, antes={"total": v.total, "numero": v.numero},
            despues={"motivo": motivo.strip()}, autorizado_por=autoriza.id)
    return v


# ───────────────────────────── Devolución ─────────────────────────────
def devolver(db: Session, usuario: m.Usuario, venta_id: int, items: list[dict], medio_reintegro: str,
             motivo: str, pin: str | None = None) -> m.Devolucion:
    v = db.get(m.Venta, venta_id)
    if not v:
        raise ErrorNegocio("Venta no encontrada.", 404)
    if v.estado != "completada":
        raise ErrorNegocio("No se puede devolver una venta anulada.", 409)
    turno = caja_svc.turno_abierto(db)
    if not turno:
        raise ErrorNegocio("Abra un turno para registrar la devolución (el reintegro sale de esa caja).", 409, "SIN_TURNO")
    if medio_reintegro not in ("efectivo", "banco"):
        raise ErrorNegocio("Indique si el reintegro es en efectivo o por banco.")
    if not (motivo or "").strip():
        raise ErrorNegocio("Escriba el motivo de la devolución.")
    if not items:
        raise ErrorNegocio("Seleccione los productos a devolver.")
    autoriza = autorizar(db, usuario, pin, "Una devolución requiere el PIN del administrador.")

    por_id = {it.id: it for it in v.items}
    dev = m.Devolucion(venta_id=v.id, turno_id=turno.id, usuario_id=usuario.id, autorizado_por=autoriza.id,
                       fecha=ahora(), motivo=motivo.strip(), total=0, impuesto_total=0, medio_reintegro=medio_reintegro)
    db.add(dev)
    db.flush()
    total_dev = imp_dev = 0
    for e in items:
        it = por_id.get(int(e["venta_item_id"]))
        cant = int(e["cantidad"])
        if not it:
            raise ErrorNegocio("Un producto no pertenece a la venta.")
        if cant <= 0:
            continue
        prev_c, prev_t, prev_i = db.execute(select(
            func.coalesce(func.sum(m.DevolucionItem.cantidad), 0), func.coalesce(func.sum(m.DevolucionItem.total), 0),
            func.coalesce(func.sum(m.DevolucionItem.valor_impuesto), 0)).where(
            m.DevolucionItem.venta_item_id == it.id)).one()
        restante = it.cantidad - prev_c
        if cant > restante:
            raise ErrorNegocio(f"De «{it.descripcion}» solo se pueden devolver {restante} unidad(es).")
        if cant == restante:  # última devolución de la línea: cierra sin diferencias de redondeo
            valor, imp = it.total - prev_t, it.valor_impuesto - prev_i
        else:
            valor, imp = redondear(it.total * cant / it.cantidad), redondear(it.valor_impuesto * cant / it.cantidad)
        danado = bool(e.get("danado"))
        db.add(m.DevolucionItem(devolucion_id=dev.id, venta_item_id=it.id, producto_id=it.producto_id, cantidad=cant,
                                total=valor, valor_impuesto=imp, costo_unitario=it.costo_unitario, danado=danado))
        p = db.get(m.Producto, it.producto_id)
        inv.registrar_movimiento(db, p, "DEVOLUCION_VENTA", cant, costo_unitario=it.costo_unitario,
                                 referencia_tipo="devolucion", referencia_id=dev.id, usuario_id=usuario.id,
                                 nota=motivo.strip())
        if danado:  # el producto no vuelve a la góndola: queda como merma
            inv.registrar_movimiento(db, p, "MERMA", -cant, costo_unitario=it.costo_unitario,
                                     referencia_tipo="devolucion", referencia_id=dev.id, usuario_id=usuario.id,
                                     motivo="DANADO", nota="Devolución de producto dañado")
        total_dev += valor
        imp_dev += imp
    if total_dev <= 0:
        raise ErrorNegocio("No hay cantidades a devolver.")
    if medio_reintegro == "banco":
        pagado_banco = sum(p.monto for p in v.pagos if p.medio.tipo == "banco")
        ya = db.scalar(select(func.coalesce(func.sum(m.Devolucion.total), 0)).where(
            m.Devolucion.venta_id == v.id, m.Devolucion.medio_reintegro == "banco", m.Devolucion.id != dev.id)) or 0
        if ya + total_dev > pagado_banco:
            raise ErrorNegocio("El reintegro por banco supera lo que el cliente pagó por banco en esta venta.")
    dev.total, dev.impuesto_total = total_dev, imp_dev
    auditar(db, usuario.id, "DEVOLUCION", "venta", v.id, despues={"total": total_dev, "motivo": motivo.strip(),
                                                                  "medio": medio_reintegro},
            autorizado_por=autoriza.id)
    db.flush()
    return dev


# ───────────────────────────── Suspendidas ─────────────────────────────
def suspender(db: Session, usuario: m.Usuario, carrito: dict, etiqueta: str | None) -> m.VentaSuspendida:
    turno = _validar_turno_para_vender(db, usuario)
    if not carrito.get("items"):
        raise ErrorNegocio("No hay productos para suspender.")
    s = m.VentaSuspendida(turno_id=turno.id, usuario_id=usuario.id, etiqueta=(etiqueta or "").strip() or None,
                          datos=json.dumps(carrito, ensure_ascii=False), total=int(carrito.get("total") or 0),
                          creado_en=ahora())
    db.add(s)
    db.flush()
    return s


def listar_suspendidas(db: Session) -> list[dict]:
    turno = caja_svc.turno_abierto(db)
    if not turno:
        return []
    return [{"id": s.id, "etiqueta": s.etiqueta, "total": s.total, "creado_en": s.creado_en.isoformat(),
             "items": len(json.loads(s.datos).get("items", []))}
            for s in db.scalars(select(m.VentaSuspendida).where(m.VentaSuspendida.turno_id == turno.id)
                                .order_by(m.VentaSuspendida.id))]


def retomar(db: Session, suspendida_id: int) -> dict:
    s = db.get(m.VentaSuspendida, suspendida_id)
    if not s:
        raise ErrorNegocio("La venta suspendida ya no existe.", 404)
    datos = json.loads(s.datos)
    db.delete(s)
    return datos


# ───────────────────────────── Consultas y serialización ─────────────────────────────
def serializar(db: Session, v: m.Venta) -> dict:
    devs = db.scalars(select(m.Devolucion).where(m.Devolucion.venta_id == v.id).options(
        selectinload(m.Devolucion.items))).all()
    devuelto: dict[int, int] = defaultdict(int)
    for d in devs:
        for di in d.items:
            devuelto[di.venta_item_id] += di.cantidad
    cajero = db.scalar(select(m.Usuario.nombre).where(m.Usuario.id == v.usuario_id))
    return {
        "id": v.id, "numero": v.numero, "prefijo": v.prefijo, "consecutivo": v.consecutivo, "turno_id": v.turno_id,
        "fecha": v.fecha.isoformat(), "cajero": cajero, "estado": v.estado, "subtotal": v.subtotal,
        "descuento_total": v.descuento_total, "impuesto_total": v.impuesto_total, "total": v.total,
        "motivo_anulacion": v.motivo_anulacion, "estado_dian": v.estado_dian,
        "cliente": {"id": v.cliente.id, "nombre": v.cliente.nombre,
                    "documento": f"{v.cliente.tipo_documento} {v.cliente.numero_documento}"} if v.cliente else None,
        "items": [{"id": i.id, "producto_id": i.producto_id, "descripcion": i.descripcion, "cantidad": i.cantidad,
                   "precio_unitario": i.precio_unitario, "descuento": i.descuento, "tarifa_pct": i.tarifa_pct,
                   "valor_impuesto": i.valor_impuesto, "total": i.total, "devuelto": devuelto.get(i.id, 0)}
                  for i in v.items],
        "pagos": [{"medio": p.medio.nombre, "tipo": p.medio.tipo, "monto": p.monto, "recibido": p.recibido,
                   "devuelta": p.devuelta, "referencia": p.referencia} for p in v.pagos],
        "devoluciones": [{"id": d.id, "fecha": d.fecha.isoformat(), "total": d.total, "motivo": d.motivo,
                          "medio_reintegro": d.medio_reintegro} for d in devs],
    }


def obtener(db: Session, venta_id: int) -> m.Venta:
    v = db.get(m.Venta, venta_id)
    if not v:
        raise ErrorNegocio("Venta no encontrada.", 404)
    return v


def listar(db: Session, *, desde: date | None = None, hasta: date | None = None, turno_id: int | None = None,
           estado: str | None = None, q: str | None = None, usuario_id: int | None = None,
           limite: int = 200) -> list[dict]:
    qry = select(m.Venta, m.Usuario.nombre).join(m.Usuario, m.Usuario.id == m.Venta.usuario_id)
    if desde:
        qry = qry.where(m.Venta.fecha >= datetime.combine(desde, time.min))
    if hasta:
        qry = qry.where(m.Venta.fecha < datetime.combine(hasta + timedelta(days=1), time.min))
    if turno_id:
        qry = qry.where(m.Venta.turno_id == turno_id)
    if usuario_id:
        qry = qry.where(m.Venta.usuario_id == usuario_id)
    if estado:
        qry = qry.where(m.Venta.estado == estado)
    if q:
        digitos = "".join(ch for ch in q if ch.isdigit())
        conds = [m.Venta.prefijo.ilike(f"%{q}%")]
        if digitos:
            conds.append(m.Venta.consecutivo == int(digitos))
        qry = qry.where(or_(*conds))
    qry = qry.order_by(m.Venta.id.desc()).limit(limite)
    return [{"id": v.id, "numero": v.numero, "fecha": v.fecha.isoformat(), "cajero": nombre, "total": v.total,
             "estado": v.estado, "turno_id": v.turno_id} for v, nombre in db.execute(qry)]
