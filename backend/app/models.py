"""Modelo de datos (SQLite).

Convenciones: precios y montos de venta en pesos como INTEGER; costos como REAL
(promedios ponderados); cantidades con el tipo `Cantidad` (unidades enteras o kilos con hasta 3 decimales);
fechas locales sin zona horaria.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String,
                        Text, UniqueConstraint)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator


class Base(DeclarativeBase):
    pass


def _norm_cant(v):
    r = round(float(v), 3)
    return int(r) if r == int(r) else r


class Cantidad(TypeDecorator):
    """Cantidad de producto: 5 unidades o 1,250 kg. En SQLite la columna sigue siendo INTEGER (guarda enteros
    como enteros y decimales como reales), así que las bases de datos anteriores no necesitan migración.
    Se redondea a 3 decimales (gramos) al guardar y al leer."""
    impl = Integer
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else _norm_cant(value)

    def process_result_value(self, value, dialect):
        return None if value is None else _norm_cant(value)


# ───────────────────────────── Usuarios y configuración ─────────────────────────────
class Usuario(Base):
    __tablename__ = "usuarios"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    usuario: Mapped[str] = mapped_column(String(60), unique=True)
    hash_password: Mapped[str] = mapped_column(String(200))
    hash_pin: Mapped[str | None] = mapped_column(String(200))
    rol: Mapped[str] = mapped_column(String(20))  # admin | cajero
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime)


class Sesion(Base):
    __tablename__ = "sesiones"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime)


class Configuracion(Base):
    __tablename__ = "configuracion"
    clave: Mapped[str] = mapped_column(String(80), primary_key=True)
    valor: Mapped[str] = mapped_column(Text, default="")


# ───────────────────────────── Catálogos ─────────────────────────────
class Categoria(Base):
    __tablename__ = "categorias"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    padre_id: Mapped[int | None] = mapped_column(ForeignKey("categorias.id"))
    __table_args__ = (UniqueConstraint("nombre", "padre_id"),)


class Proveedor(Base):
    __tablename__ = "proveedores"
    id: Mapped[int] = mapped_column(primary_key=True)
    nit: Mapped[str | None] = mapped_column(String(30))
    nombre: Mapped[str] = mapped_column(String(160), unique=True)
    telefono: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(120))
    contacto: Mapped[str | None] = mapped_column(String(120))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Impuesto(Base):
    __tablename__ = "impuestos"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80), unique=True)
    tipo: Mapped[str] = mapped_column(String(20), default="IVA")  # IVA | INC | BOLSA | OTRO
    tarifa_pct: Mapped[float] = mapped_column(Float, default=0)
    valor_fijo: Mapped[int] = mapped_column(Integer, default=0)  # por unidad, incluido en el precio
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class MedioPago(Base):
    __tablename__ = "medios_pago"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80), unique=True)
    tipo: Mapped[str] = mapped_column(String(10))  # efectivo | banco
    requiere_referencia: Mapped[bool] = mapped_column(Boolean, default=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    orden: Mapped[int] = mapped_column(Integer, default=0)


class Cliente(Base):
    __tablename__ = "clientes"
    id: Mapped[int] = mapped_column(primary_key=True)
    tipo_documento: Mapped[str] = mapped_column(String(10), default="CC")
    numero_documento: Mapped[str] = mapped_column(String(30))
    nombre: Mapped[str] = mapped_column(String(160))
    email: Mapped[str | None] = mapped_column(String(120))
    telefono: Mapped[str | None] = mapped_column(String(40))
    __table_args__ = (UniqueConstraint("tipo_documento", "numero_documento"),)


# ───────────────────────────── Productos ─────────────────────────────
class Producto(Base):
    __tablename__ = "productos"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo_interno: Mapped[str | None] = mapped_column(String(40), unique=True)
    nombre: Mapped[str] = mapped_column(String(200), index=True)
    categoria_id: Mapped[int | None] = mapped_column(ForeignKey("categorias.id"), index=True)
    marca: Mapped[str | None] = mapped_column(String(80))
    proveedor_id: Mapped[int | None] = mapped_column(ForeignKey("proveedores.id"), index=True)
    impuesto_id: Mapped[int | None] = mapped_column(ForeignKey("impuestos.id"))
    costo_promedio: Mapped[float] = mapped_column(Float, default=0)
    precio_venta: Mapped[int] = mapped_column(Integer, default=0)
    unidad: Mapped[str] = mapped_column(String(3), default="u", server_default="u")  # u (unidad) | kg (por peso)
    rapido: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")  # botón de acceso rápido en caja
    stock_actual: Mapped[float] = mapped_column(Cantidad, default=0)
    stock_minimo: Mapped[float] = mapped_column(Cantidad, default=0)
    stock_maximo: Mapped[float] = mapped_column(Cantidad, default=0)
    ubicacion: Mapped[str | None] = mapped_column(String(60), index=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime)

    categoria: Mapped[Categoria | None] = relationship()
    proveedor: Mapped[Proveedor | None] = relationship()
    impuesto: Mapped[Impuesto | None] = relationship()
    codigos: Mapped[list[CodigoBarra]] = relationship(back_populates="producto", cascade="all, delete-orphan")


class CodigoBarra(Base):
    __tablename__ = "codigos_barra"
    codigo: Mapped[str] = mapped_column(String(64), primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"), index=True)
    unidades_por_codigo: Mapped[int] = mapped_column(Integer, default=1)
    producto: Mapped[Producto] = relationship(back_populates="codigos")


class HistorialPrecio(Base):
    __tablename__ = "historial_precios"
    id: Mapped[int] = mapped_column(primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"), index=True)
    precio_anterior: Mapped[int] = mapped_column(Integer)
    precio_nuevo: Mapped[int] = mapped_column(Integer)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    fecha: Mapped[datetime] = mapped_column(DateTime)


# ───────────────────────────── Caja ─────────────────────────────
class Caja(Base):
    __tablename__ = "cajas"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(60))


class Turno(Base):
    __tablename__ = "turnos"
    id: Mapped[int] = mapped_column(primary_key=True)
    caja_id: Mapped[int] = mapped_column(ForeignKey("cajas.id"))
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    abierto_en: Mapped[datetime] = mapped_column(DateTime)
    base_efectivo: Mapped[int] = mapped_column(Integer, default=0)
    cerrado_en: Mapped[datetime | None] = mapped_column(DateTime)
    efectivo_esperado: Mapped[int | None] = mapped_column(Integer)
    efectivo_contado: Mapped[int | None] = mapped_column(Integer)
    diferencia_efectivo: Mapped[int | None] = mapped_column(Integer)
    banco_esperado: Mapped[int | None] = mapped_column(Integer)
    banco_reportado: Mapped[int | None] = mapped_column(Integer)
    diferencia_banco: Mapped[int | None] = mapped_column(Integer)
    estado: Mapped[str] = mapped_column(String(10), default="abierto")  # abierto | cerrado
    observaciones: Mapped[str | None] = mapped_column(Text)
    usuario: Mapped[Usuario] = relationship()

    __table_args__ = (Index("ix_turnos_caja_estado", "caja_id", "estado"),)


class TurnoDenominacion(Base):
    __tablename__ = "turno_denominaciones"
    id: Mapped[int] = mapped_column(primary_key=True)
    turno_id: Mapped[int] = mapped_column(ForeignKey("turnos.id"), index=True)
    momento: Mapped[str] = mapped_column(String(10))  # apertura | cierre
    denominacion: Mapped[int] = mapped_column(Integer)
    cantidad: Mapped[int] = mapped_column(Integer)


class MovimientoCaja(Base):
    __tablename__ = "movimientos_caja"
    id: Mapped[int] = mapped_column(primary_key=True)
    turno_id: Mapped[int] = mapped_column(ForeignKey("turnos.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(10))  # ingreso | retiro
    monto: Mapped[int] = mapped_column(Integer)
    motivo: Mapped[str] = mapped_column(String(255))
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    autorizado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    fecha: Mapped[datetime] = mapped_column(DateTime)


# ───────────────────────────── Ventas ─────────────────────────────
class Venta(Base):
    __tablename__ = "ventas"
    id: Mapped[int] = mapped_column(primary_key=True)
    prefijo: Mapped[str] = mapped_column(String(10))
    consecutivo: Mapped[int] = mapped_column(Integer)
    turno_id: Mapped[int] = mapped_column(ForeignKey("turnos.id"), index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("clientes.id"))
    fecha: Mapped[datetime] = mapped_column(DateTime, index=True)
    subtotal: Mapped[int] = mapped_column(Integer)  # bruto antes de descuentos
    descuento_total: Mapped[int] = mapped_column(Integer, default=0)
    impuesto_total: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer)
    estado: Mapped[str] = mapped_column(String(12), default="completada")  # completada | anulada
    anulada_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    anulada_en: Mapped[datetime | None] = mapped_column(DateTime)
    motivo_anulacion: Mapped[str | None] = mapped_column(String(255))
    estado_dian: Mapped[str] = mapped_column(String(15), default="no_aplica")
    cude: Mapped[str | None] = mapped_column(String(120))

    items: Mapped[list[VentaItem]] = relationship(back_populates="venta", cascade="all, delete-orphan",
                                                  order_by="VentaItem.id")
    pagos: Mapped[list[VentaPago]] = relationship(back_populates="venta", cascade="all, delete-orphan",
                                                  order_by="VentaPago.id")
    usuario: Mapped[Usuario] = relationship(foreign_keys=[usuario_id])
    cliente: Mapped[Cliente | None] = relationship()

    __table_args__ = (UniqueConstraint("prefijo", "consecutivo"),)

    @property
    def numero(self) -> str:
        return f"{self.prefijo}-{self.consecutivo:06d}"


class VentaItem(Base):
    __tablename__ = "venta_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    venta_id: Mapped[int] = mapped_column(ForeignKey("ventas.id"), index=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"), index=True)
    descripcion: Mapped[str] = mapped_column(String(200))
    cantidad: Mapped[float] = mapped_column(Cantidad)
    precio_unitario: Mapped[int] = mapped_column(Integer)
    descuento: Mapped[int] = mapped_column(Integer, default=0)
    impuesto_id: Mapped[int | None] = mapped_column(ForeignKey("impuestos.id"))
    tarifa_pct: Mapped[float] = mapped_column(Float, default=0)
    valor_impuesto: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer)
    costo_unitario: Mapped[float] = mapped_column(Float, default=0)  # congelado al vender
    venta: Mapped[Venta] = relationship(back_populates="items")
    producto: Mapped[Producto] = relationship()

    __table_args__ = (Index("ix_venta_items_prod_venta", "producto_id", "venta_id"),)


class VentaPago(Base):
    __tablename__ = "venta_pagos"
    id: Mapped[int] = mapped_column(primary_key=True)
    venta_id: Mapped[int] = mapped_column(ForeignKey("ventas.id"), index=True)
    medio_pago_id: Mapped[int] = mapped_column(ForeignKey("medios_pago.id"))
    monto: Mapped[int] = mapped_column(Integer)  # valor aplicado a la venta
    recibido: Mapped[int] = mapped_column(Integer)
    devuelta: Mapped[int] = mapped_column(Integer, default=0)
    referencia: Mapped[str | None] = mapped_column(String(80))
    venta: Mapped[Venta] = relationship(back_populates="pagos")
    medio: Mapped[MedioPago] = relationship()


class VentaSuspendida(Base):
    __tablename__ = "ventas_suspendidas"
    id: Mapped[int] = mapped_column(primary_key=True)
    turno_id: Mapped[int] = mapped_column(ForeignKey("turnos.id"), index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    etiqueta: Mapped[str | None] = mapped_column(String(80))
    datos: Mapped[str] = mapped_column(Text)  # JSON del carrito
    total: Mapped[int] = mapped_column(Integer, default=0)
    creado_en: Mapped[datetime] = mapped_column(DateTime)


class Devolucion(Base):
    __tablename__ = "devoluciones"
    id: Mapped[int] = mapped_column(primary_key=True)
    venta_id: Mapped[int] = mapped_column(ForeignKey("ventas.id"), index=True)
    turno_id: Mapped[int] = mapped_column(ForeignKey("turnos.id"), index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    autorizado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    fecha: Mapped[datetime] = mapped_column(DateTime, index=True)
    motivo: Mapped[str] = mapped_column(String(255))
    total: Mapped[int] = mapped_column(Integer)
    impuesto_total: Mapped[int] = mapped_column(Integer, default=0)
    medio_reintegro: Mapped[str] = mapped_column(String(10))  # efectivo | banco
    items: Mapped[list[DevolucionItem]] = relationship(back_populates="devolucion", cascade="all, delete-orphan")
    venta: Mapped[Venta] = relationship()


class DevolucionItem(Base):
    __tablename__ = "devolucion_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    devolucion_id: Mapped[int] = mapped_column(ForeignKey("devoluciones.id"), index=True)
    venta_item_id: Mapped[int] = mapped_column(ForeignKey("venta_items.id"), index=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"), index=True)
    cantidad: Mapped[float] = mapped_column(Cantidad)
    total: Mapped[int] = mapped_column(Integer)
    valor_impuesto: Mapped[int] = mapped_column(Integer, default=0)
    costo_unitario: Mapped[float] = mapped_column(Float, default=0)
    danado: Mapped[bool] = mapped_column(Boolean, default=False)
    devolucion: Mapped[Devolucion] = relationship(back_populates="items")


# ───────────────────────────── Compras e inventario ─────────────────────────────
class Compra(Base):
    __tablename__ = "compras"
    id: Mapped[int] = mapped_column(primary_key=True)
    proveedor_id: Mapped[int | None] = mapped_column(ForeignKey("proveedores.id"), index=True)
    numero_factura: Mapped[str | None] = mapped_column(String(60))
    fecha: Mapped[datetime] = mapped_column(DateTime, index=True)
    total: Mapped[float] = mapped_column(Float, default=0)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    nota: Mapped[str | None] = mapped_column(String(255))
    items: Mapped[list[CompraItem]] = relationship(back_populates="compra", cascade="all, delete-orphan")
    proveedor: Mapped[Proveedor | None] = relationship()


class CompraItem(Base):
    __tablename__ = "compra_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    compra_id: Mapped[int] = mapped_column(ForeignKey("compras.id"), index=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"), index=True)
    cantidad: Mapped[float] = mapped_column(Cantidad)
    costo_unitario: Mapped[float] = mapped_column(Float)
    compra: Mapped[Compra] = relationship(back_populates="items")
    producto: Mapped[Producto] = relationship()


class MovimientoInventario(Base):
    __tablename__ = "movimientos_inventario"
    id: Mapped[int] = mapped_column(primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"))
    fecha: Mapped[datetime] = mapped_column(DateTime)
    tipo: Mapped[str] = mapped_column(String(20))
    cantidad: Mapped[float] = mapped_column(Cantidad)  # con signo
    costo_unitario: Mapped[float] = mapped_column(Float, default=0)
    stock_resultante: Mapped[float] = mapped_column(Cantidad)
    referencia_tipo: Mapped[str | None] = mapped_column(String(20))
    referencia_id: Mapped[int | None] = mapped_column(Integer)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    motivo: Mapped[str | None] = mapped_column(String(30))
    nota: Mapped[str | None] = mapped_column(String(255))
    producto: Mapped[Producto] = relationship()

    __table_args__ = (Index("ix_mov_prod_fecha", "producto_id", "fecha"),
                      Index("ix_mov_tipo_fecha", "tipo", "fecha"))


class InventarioDiario(Base):
    __tablename__ = "inventario_diario"
    fecha: Mapped[date] = mapped_column(Date, primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"), primary_key=True)
    stock: Mapped[float] = mapped_column(Cantidad)
    costo_promedio: Mapped[float] = mapped_column(Float)


# ───────────────────────────── Conteos ─────────────────────────────
class ProgramacionConteo(Base):
    __tablename__ = "programacion_conteos"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    tipo: Mapped[str] = mapped_column(String(10), default="total")  # total | parcial | ciclico
    alcance: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    frecuencia: Mapped[str] = mapped_column(String(12), default="una_vez")  # una_vez|dias|semanal|quincenal|mensual
    intervalo: Mapped[int] = mapped_column(Integer, default=1)
    proxima_fecha: Mapped[date | None] = mapped_column(Date)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Conteo(Base):
    __tablename__ = "conteos"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    tipo: Mapped[str] = mapped_column(String(10))  # total | parcial | ciclico
    alcance: Mapped[str] = mapped_column(Text, default="{}")
    estado: Mapped[str] = mapped_column(String(12), default="borrador")
    # borrador | en_conteo | en_revision | aplicado | cancelado
    programacion_id: Mapped[int | None] = mapped_column(ForeignKey("programacion_conteos.id"))
    creado_por: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime)
    iniciado_en: Mapped[datetime | None] = mapped_column(DateTime)
    cerrado_en: Mapped[datetime | None] = mapped_column(DateTime)
    aprobado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    asumio_cero: Mapped[bool] = mapped_column(Boolean, default=False)
    exactitud_pct: Mapped[float | None] = mapped_column(Float)
    items: Mapped[list[ConteoItem]] = relationship(back_populates="conteo", cascade="all, delete-orphan")


class ConteoItem(Base):
    __tablename__ = "conteo_items"
    conteo_id: Mapped[int] = mapped_column(ForeignKey("conteos.id"), primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"), primary_key=True)
    stock_teorico: Mapped[float | None] = mapped_column(Cantidad)
    cantidad_contada: Mapped[float | None] = mapped_column(Cantidad)
    diferencia: Mapped[float | None] = mapped_column(Cantidad)
    costo_unitario: Mapped[float] = mapped_column(Float, default=0)
    no_contado: Mapped[bool] = mapped_column(Boolean, default=False)
    reconteo: Mapped[bool] = mapped_column(Boolean, default=False)
    conteo: Mapped[Conteo] = relationship(back_populates="items")
    producto: Mapped[Producto] = relationship()


class ConteoCaptura(Base):
    __tablename__ = "conteo_capturas"
    id: Mapped[int] = mapped_column(primary_key=True)
    conteo_id: Mapped[int] = mapped_column(ForeignKey("conteos.id"), index=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"), index=True)
    cantidad: Mapped[float] = mapped_column(Cantidad)
    ubicacion: Mapped[str | None] = mapped_column(String(60))
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    capturado_en: Mapped[datetime] = mapped_column(DateTime)
    reemplazada: Mapped[bool] = mapped_column(Boolean, default=False)  # por un reconteo


# ───────────────────────────── Auditoría y respaldos ─────────────────────────────
class Auditoria(Base):
    __tablename__ = "auditoria"
    id: Mapped[int] = mapped_column(primary_key=True)
    fecha: Mapped[datetime] = mapped_column(DateTime, index=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    accion: Mapped[str] = mapped_column(String(40), index=True)
    entidad: Mapped[str | None] = mapped_column(String(40))
    entidad_id: Mapped[int | None] = mapped_column(Integer)
    datos_antes: Mapped[str | None] = mapped_column(Text)
    datos_despues: Mapped[str | None] = mapped_column(Text)
    autorizado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    usuario: Mapped[Usuario | None] = relationship(foreign_keys=[usuario_id])


class Respaldo(Base):
    __tablename__ = "respaldos"
    id: Mapped[int] = mapped_column(primary_key=True)
    fecha: Mapped[datetime] = mapped_column(DateTime, index=True)
    archivo: Mapped[str] = mapped_column(String(255))
    tipo: Mapped[str] = mapped_column(String(15))  # diario | turno | manual | previo_restauracion
    tamano: Mapped[int] = mapped_column(Integer, default=0)
    copia_externa: Mapped[bool] = mapped_column(Boolean, default=False)
