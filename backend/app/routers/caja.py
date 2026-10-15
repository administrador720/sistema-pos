"""Turnos de caja, movimientos de efectivo y cajón monedero."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter
from fastapi.responses import Response
from sqlalchemy import select

from .. import jobs
from .. import models as m
from ..core import ErrorNegocio, auditar, autorizar, cfg
from ..deps import DB, DBW, Admin, Pin, Usuario
from ..hardware import cajon as cajon_hw
from ..schemas import AbrirTurnoIn, CajonIn, CerrarTurnoIn, MovimientoCajaIn
from ..services import caja as svc
from ..services import exportacion

router = APIRouter(prefix="/api")


def _denoms(lista):
    return [d.model_dump() for d in lista] if lista else None


def abrir_cajon(db) -> tuple[bool, str]:
    return cajon_hw.crear(cfg(db, "cajon_modo"), cfg(db, "cajon_puerto")).abrir()


@router.get("/turnos/actual")
def turno_actual(u: Usuario, db: DB):
    t = svc.turno_abierto(db)
    if not t:
        return {"turno": None}
    base = {"turno": svc.serializar_turno(db, t), "es_mio": t.usuario_id == u.id}
    if u.rol == "admin":
        base["resumen"] = svc.calcular(db, t)
    else:
        base["resumen"] = svc.resumen_ciego(db, t)
        base["turno"].pop("efectivo_esperado", None)
    return base


@router.post("/turnos/abrir")
def abrir(body: AbrirTurnoIn, u: Usuario, db: DBW):
    t = svc.abrir_turno(db, u, base=body.base, denominaciones_=_denoms(body.denominaciones))
    db.commit()
    ok, aviso = abrir_cajon(db)  # se abre el cajón para verificar la base
    return {"turno": svc.serializar_turno(db, t), "cajon": {"ok": ok, "mensaje": aviso}}


@router.post("/turnos/{tid}/cerrar")
def cerrar(tid: int, body: CerrarTurnoIn, u: Usuario, db: DBW):
    t = db.get(m.Turno, tid)
    if not t:
        raise ErrorNegocio("Turno no encontrado.", 404)
    z = svc.cerrar_turno(db, u, t, denominaciones_=_denoms(body.denominaciones), efectivo_contado=body.efectivo_contado,
                         banco_reportado=body.banco_reportado, observaciones=body.observaciones)
    db.commit()
    jobs.tras_cierre_turno()  # foto del inventario + respaldo, en segundo plano
    return z


@router.get("/turnos")
def listar_turnos(_: Admin, db: DB, desde: date | None = None, hasta: date | None = None, limite: int = 100):
    q = select(m.Turno).order_by(m.Turno.id.desc()).limit(limite)
    return [svc.serializar_turno(db, t) for t in db.scalars(q)]


@router.get("/turnos/{tid}/reporte")
def reporte(tid: int, u: Usuario, db: DB, formato: str = "json"):
    t = db.get(m.Turno, tid)
    if not t:
        raise ErrorNegocio("Turno no encontrado.", 404)
    if u.rol != "admin" and (t.usuario_id != u.id or t.estado != "cerrado"):
        raise ErrorNegocio("Solo puede ver el reporte de sus turnos ya cerrados.", 403)
    z = svc.reporte_z(db, t)
    if formato == "pdf":
        return Response(exportacion.a_pdf(_z_a_informe(z), cfg(db, "negocio_nombre")), media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="cierre-turno-{tid}.pdf"'})
    return z


def _z_a_informe(z: dict) -> dict:
    t, c = z["turno"], z["totales"]
    din = lambda v: exportacion._fmt(v, "dinero")  # noqa: E731
    filas = [("Cajero", t["usuario"]), ("Apertura", t["abierto_en"][:16].replace("T", " ")),
             ("Cierre", (t["cerrado_en"] or "")[:16].replace("T", " ")), ("Base inicial", din(c["base"])),
             ("Ventas (tiquetes)", str(c["ventas_n"])), ("Ventas totales", din(c["ventas_total"]))]
    filas += [(f"   · {x['medio']}", din(x["monto"])) for x in c["por_medio"]]
    filas += [("Ingresos de caja", din(c["ingresos"])), ("Retiros de caja", din(c["retiros"])),
              ("Devoluciones (efectivo)", din(c["devoluciones_efectivo"])),
              ("Devoluciones (banco)", din(c["devoluciones_banco"])), ("Anulaciones", str(c["anuladas_n"])),
              ("Descuentos", din(c["descuentos"])), ("Efectivo esperado", din(t["efectivo_esperado"])),
              ("Efectivo contado", din(t["efectivo_contado"])), ("DIFERENCIA EFECTIVO", din(t["diferencia_efectivo"])),
              ("Banco esperado", din(t["banco_esperado"])), ("Banco reportado (datáfono)", din(t["banco_reportado"])),
              ("DIFERENCIA BANCO", din(t["diferencia_banco"]))]
    return {"titulo": f"Cierre de turno #{t['id']} — {z['caja']}",
            "columnas": [{"key": "concepto", "titulo": "Concepto", "tipo": "texto"},
                         {"key": "valor", "titulo": "Valor", "tipo": "texto"}],
            "filas": [{"concepto": a, "valor": b} for a, b in filas], "nota": t.get("observaciones")}


@router.post("/turnos/{tid}/movimientos")
def movimiento(tid: int, body: MovimientoCajaIn, u: Usuario, db: DBW, pin: Pin = None):
    t = db.get(m.Turno, tid)
    if not t:
        raise ErrorNegocio("Turno no encontrado.", 404)
    if u.rol != "admin" and t.usuario_id != u.id:
        raise ErrorNegocio("Solo el cajero del turno puede registrar movimientos.", 403)
    mv = svc.registrar_movimiento_caja(db, u, t, body.tipo, body.monto, body.motivo, pin)
    db.commit()
    if body.tipo == "retiro":
        abrir_cajon(db)
    return {"id": mv.id, "tipo": mv.tipo, "monto": mv.monto, "motivo": mv.motivo}


@router.post("/cajon/abrir")
def abrir_sin_venta(body: CajonIn, u: Usuario, db: DBW, pin: Pin = None):
    """Abrir el cajón sin una venta es una acción sensible: cajero necesita PIN de administrador."""
    autoriza = autorizar(db, u, pin, "Abrir el cajón sin una venta requiere el PIN del administrador.")
    auditar(db, u.id, "CAJON_SIN_VENTA", "cajon", despues={"motivo": body.motivo}, autorizado_por=autoriza.id)
    db.commit()
    ok, msg = abrir_cajon(db)
    return {"ok": ok, "mensaje": msg}
