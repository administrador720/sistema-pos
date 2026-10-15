"""Turnos de caja: apertura con base, movimientos, arqueo ciego y reporte Z."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m
from ..core import ErrorNegocio, ahora, auditar, autorizar, cfg_bool, denominaciones


def caja_principal(db: Session) -> m.Caja:
    c = db.scalars(select(m.Caja).order_by(m.Caja.id)).first()
    if not c:
        raise ErrorNegocio("No hay caja configurada.", 500)
    return c


def turno_abierto(db: Session, caja_id: int | None = None) -> m.Turno | None:
    caja_id = caja_id or caja_principal(db).id
    return db.scalars(select(m.Turno).where(m.Turno.caja_id == caja_id, m.Turno.estado == "abierto")).first()


def _total_denominaciones(denoms: list[dict] | None, validas: list[int]) -> int:
    total = 0
    for d in denoms or []:
        valor, cant = int(d.get("denominacion", 0)), int(d.get("cantidad", 0))
        if valor not in validas:
            raise ErrorNegocio(f"Denominación {valor} no configurada.")
        if cant < 0:
            raise ErrorNegocio("La cantidad de billetes/monedas no puede ser negativa.")
        total += valor * cant
    return total


def _guardar_denominaciones(db: Session, turno_id: int, momento: str, denoms: list[dict] | None):
    for d in denoms or []:
        if int(d.get("cantidad", 0)) > 0:
            db.add(m.TurnoDenominacion(turno_id=turno_id, momento=momento, denominacion=int(d["denominacion"]),
                                       cantidad=int(d["cantidad"])))


def abrir_turno(db: Session, usuario: m.Usuario, *, base: int | None = None,
                denominaciones_: list[dict] | None = None) -> m.Turno:
    caja = caja_principal(db)
    existente = turno_abierto(db, caja.id)
    if existente:
        raise ErrorNegocio(f"Ya hay un turno abierto en {caja.nombre} (#{existente.id}).", 409, "TURNO_ABIERTO")
    if denominaciones_:
        total = _total_denominaciones(denominaciones_, denominaciones(db))
        if base is not None and int(base) != total:
            raise ErrorNegocio("La base digitada no coincide con el conteo por denominaciones.")
        base = total
    if base is None or int(base) < 0:
        raise ErrorNegocio("Indique la base con la que inicia el turno (puede ser 0).")
    t = m.Turno(caja_id=caja.id, usuario_id=usuario.id, abierto_en=ahora(), base_efectivo=int(base), estado="abierto")
    db.add(t)
    db.flush()
    _guardar_denominaciones(db, t.id, "apertura", denominaciones_)
    auditar(db, usuario.id, "APERTURA_TURNO", "turno", t.id, despues={"base": int(base)})
    return t


def registrar_movimiento_caja(db: Session, usuario: m.Usuario, turno: m.Turno, tipo: str, monto: int,
                              motivo: str, pin: str | None = None) -> m.MovimientoCaja:
    if turno.estado != "abierto":
        raise ErrorNegocio("El turno está cerrado.", 409)
    if tipo not in ("ingreso", "retiro"):
        raise ErrorNegocio("Tipo de movimiento no válido.")
    if int(monto) <= 0:
        raise ErrorNegocio("El monto debe ser mayor a cero.")
    if not (motivo or "").strip():
        raise ErrorNegocio("Escriba el motivo del movimiento.")
    autoriza = None
    if tipo == "retiro" and cfg_bool(db, "retiro_requiere_autorizacion"):
        autoriza = autorizar(db, usuario, pin, "El retiro de caja requiere el PIN del administrador.")
    mov = m.MovimientoCaja(turno_id=turno.id, tipo=tipo, monto=int(monto), motivo=motivo.strip(),
                           usuario_id=usuario.id, autorizado_por=autoriza.id if autoriza else None, fecha=ahora())
    db.add(mov)
    db.flush()
    auditar(db, usuario.id, f"CAJA_{tipo.upper()}", "turno", turno.id,
            despues={"monto": int(monto), "motivo": motivo}, autorizado_por=autoriza.id if autoriza else None)
    return mov


def calcular(db: Session, turno: m.Turno) -> dict:
    """Totales del turno. Efectivo esperado = base + ventas en efectivo (lo aplicado, no lo recibido)
    + ingresos − retiros − devoluciones pagadas en efectivo."""
    por_medio = []
    ventas_efectivo = ventas_banco = 0
    for nombre, tipo, monto, n in db.execute(
            select(m.MedioPago.nombre, m.MedioPago.tipo, func.sum(m.VentaPago.monto), func.count(m.VentaPago.id))
            .join(m.VentaPago, m.VentaPago.medio_pago_id == m.MedioPago.id)
            .join(m.Venta, m.Venta.id == m.VentaPago.venta_id)
            .where(m.Venta.turno_id == turno.id, m.Venta.estado == "completada")
            .group_by(m.MedioPago.id).order_by(m.MedioPago.orden)):
        por_medio.append({"medio": nombre, "tipo": tipo, "monto": int(monto), "pagos": n})
        if tipo == "efectivo":
            ventas_efectivo += int(monto)
        else:
            ventas_banco += int(monto)

    ventas = db.execute(select(func.count(m.Venta.id), func.coalesce(func.sum(m.Venta.total), 0),
                               func.coalesce(func.sum(m.Venta.descuento_total), 0),
                               func.coalesce(func.sum(m.Venta.impuesto_total), 0))
                        .where(m.Venta.turno_id == turno.id, m.Venta.estado == "completada")).one()
    anuladas = db.execute(select(func.count(m.Venta.id), func.coalesce(func.sum(m.Venta.total), 0))
                          .where(m.Venta.turno_id == turno.id, m.Venta.estado == "anulada")).one()

    dev = {"efectivo": 0, "banco": 0}
    n_dev = 0
    for medio, total, n in db.execute(select(m.Devolucion.medio_reintegro, func.sum(m.Devolucion.total),
                                             func.count(m.Devolucion.id))
                                      .where(m.Devolucion.turno_id == turno.id).group_by(m.Devolucion.medio_reintegro)):
        dev[medio] = int(total)
        n_dev += n

    mov = {"ingreso": 0, "retiro": 0}
    for tipo, total in db.execute(select(m.MovimientoCaja.tipo, func.sum(m.MovimientoCaja.monto))
                                  .where(m.MovimientoCaja.turno_id == turno.id).group_by(m.MovimientoCaja.tipo)):
        mov[tipo] = int(total)

    efectivo_esperado = turno.base_efectivo + ventas_efectivo + mov["ingreso"] - mov["retiro"] - dev["efectivo"]
    banco_esperado = ventas_banco - dev["banco"]
    return {
        "turno_id": turno.id, "ventas_n": ventas[0], "ventas_total": int(ventas[1]),
        "descuentos": int(ventas[2]), "impuestos": int(ventas[3]),
        "anuladas_n": anuladas[0], "anuladas_total": int(anuladas[1]),
        "devoluciones_n": n_dev, "devoluciones_efectivo": dev["efectivo"], "devoluciones_banco": dev["banco"],
        "por_medio": por_medio, "ventas_efectivo": ventas_efectivo, "ventas_banco": ventas_banco,
        "ingresos": mov["ingreso"], "retiros": mov["retiro"], "base": turno.base_efectivo,
        "efectivo_esperado": efectivo_esperado, "banco_esperado": banco_esperado,
    }


def _usuario_nombre(db: Session, uid: int | None) -> str | None:
    return db.scalar(select(m.Usuario.nombre).where(m.Usuario.id == uid)) if uid else None


def serializar_turno(db: Session, t: m.Turno) -> dict:
    return {
        "id": t.id, "caja_id": t.caja_id, "usuario_id": t.usuario_id,
        "usuario": _usuario_nombre(db, t.usuario_id), "abierto_en": t.abierto_en.isoformat(),
        "cerrado_en": t.cerrado_en.isoformat() if t.cerrado_en else None,
        "base_efectivo": t.base_efectivo, "estado": t.estado,
        "efectivo_esperado": t.efectivo_esperado, "efectivo_contado": t.efectivo_contado,
        "diferencia_efectivo": t.diferencia_efectivo, "banco_esperado": t.banco_esperado,
        "banco_reportado": t.banco_reportado, "diferencia_banco": t.diferencia_banco,
        "observaciones": t.observaciones,
    }


def resumen_ciego(db: Session, turno: m.Turno) -> dict:
    """Lo que ve un cajero con el turno abierto: sin totales de efectivo (cierre ciego)."""
    c = calcular(db, turno)
    return {"turno_id": turno.id, "ventas_n": c["ventas_n"], "ventas_total": c["ventas_total"],
            "anuladas_n": c["anuladas_n"], "devoluciones_n": c["devoluciones_n"], "ciego": True}


def cerrar_turno(db: Session, usuario: m.Usuario, turno: m.Turno, *, denominaciones_: list[dict] | None = None,
                 efectivo_contado: int | None = None, banco_reportado: int | None = None,
                 observaciones: str | None = None) -> dict:
    if turno.estado != "abierto":
        raise ErrorNegocio("El turno ya está cerrado.", 409)
    if usuario.rol != "admin" and usuario.id != turno.usuario_id:
        raise ErrorNegocio("Solo el cajero del turno o un administrador puede cerrarlo.", 403)
    pendientes = db.scalar(select(func.count()).select_from(m.VentaSuspendida)
                           .where(m.VentaSuspendida.turno_id == turno.id)) or 0
    if pendientes:
        raise ErrorNegocio(f"Hay {pendientes} venta(s) suspendida(s). Retómelas o descártelas antes de cerrar.",
                           409, "VENTAS_SUSPENDIDAS")
    if denominaciones_:
        efectivo_contado = _total_denominaciones(denominaciones_, denominaciones(db))
    if efectivo_contado is None or int(efectivo_contado) < 0:
        raise ErrorNegocio("Cuente el efectivo de la caja antes de cerrar.")
    c = calcular(db, turno)
    hay_banco = c["banco_esperado"] != 0 or banco_reportado not in (None, 0)
    if hay_banco and banco_reportado is None:
        raise ErrorNegocio("Digite el total del cierre del datáfono / transferencias.")
    banco_reportado = int(banco_reportado or 0)
    turno.efectivo_esperado = c["efectivo_esperado"]
    turno.efectivo_contado = int(efectivo_contado)
    turno.diferencia_efectivo = int(efectivo_contado) - c["efectivo_esperado"]
    turno.banco_esperado = c["banco_esperado"]
    turno.banco_reportado = banco_reportado
    turno.diferencia_banco = banco_reportado - c["banco_esperado"]
    turno.cerrado_en = ahora()
    turno.estado = "cerrado"
    turno.observaciones = (observaciones or "").strip() or None
    _guardar_denominaciones(db, turno.id, "cierre", denominaciones_)
    auditar(db, usuario.id, "CIERRE_TURNO", "turno", turno.id,
            despues={"dif_efectivo": turno.diferencia_efectivo, "dif_banco": turno.diferencia_banco})
    db.flush()
    return reporte_z(db, turno)


def reporte_z(db: Session, turno: m.Turno) -> dict:
    c = calcular(db, turno)
    denoms = [{"momento": mo, "denominacion": d, "cantidad": q} for mo, d, q in db.execute(
        select(m.TurnoDenominacion.momento, m.TurnoDenominacion.denominacion, m.TurnoDenominacion.cantidad)
        .where(m.TurnoDenominacion.turno_id == turno.id).order_by(m.TurnoDenominacion.denominacion.desc()))]
    movs = [{"id": mv.id, "tipo": mv.tipo, "monto": mv.monto, "motivo": mv.motivo, "fecha": mv.fecha.isoformat(),
             "usuario": _usuario_nombre(db, mv.usuario_id), "autorizado_por": _usuario_nombre(db, mv.autorizado_por)}
            for mv in db.scalars(select(m.MovimientoCaja).where(m.MovimientoCaja.turno_id == turno.id)
                                 .order_by(m.MovimientoCaja.fecha))]
    caja = db.get(m.Caja, turno.caja_id)
    return {"turno": serializar_turno(db, turno), "caja": caja.nombre if caja else "", "totales": c,
            "denominaciones": denoms, "movimientos": movs}
