"""Esquemas de entrada (validación). Las respuestas son diccionarios construidos por los servicios."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Base(BaseModel):
    model_config = ConfigDict(extra="ignore")


class NegocioIn(Base):
    nombre: str = Field(min_length=1, max_length=120)
    nit: str = ""
    direccion: str = ""
    telefono: str = ""


class AdminIn(Base):
    nombre: str
    usuario: str
    password: str
    pin: str


class SetupIn(Base):
    negocio: NegocioIn
    admin: AdminIn


class LoginIn(Base):
    usuario: str
    password: str


class SecretoIn(Base):
    secreto: str


class PinIn(Base):
    pin: str


class CredencialesIn(Base):
    password_actual: str
    password_nueva: str | None = None
    pin_nuevo: str | None = None


class UsuarioIn(Base):
    nombre: str | None = None
    usuario: str | None = None
    password: str | None = None
    pin: str | None = None
    rol: str | None = None
    activo: bool | None = None


class ConfigIn(Base):
    valores: dict[str, str | int | float | bool]


class CategoriaIn(Base):
    nombre: str
    padre_id: int | None = None


class ProveedorIn(Base):
    nombre: str | None = None
    nit: str | None = None
    telefono: str | None = None
    email: str | None = None
    contacto: str | None = None
    activo: bool | None = None


class ImpuestoIn(Base):
    nombre: str | None = None
    tipo: str | None = None
    tarifa_pct: float | None = None
    valor_fijo: int | None = None
    activo: bool | None = None


class MedioPagoIn(Base):
    nombre: str | None = None
    tipo: str | None = None
    requiere_referencia: bool | None = None
    activo: bool | None = None
    orden: int | None = None


class ClienteIn(Base):
    tipo_documento: str = "CC"
    numero_documento: str
    nombre: str
    email: str | None = None
    telefono: str | None = None


class CodigoIn(Base):
    codigo: str
    unidades: int = 1


class ProductoIn(Base):
    codigo_interno: str | None = None
    nombre: str | None = None
    categoria_id: int | None = None
    marca: str | None = None
    proveedor_id: int | None = None
    impuesto_id: int | None = None
    costo_promedio: float | None = None
    precio_venta: int | None = None
    stock_minimo: int | None = None
    stock_maximo: int | None = None
    stock_inicial: int | None = None
    ubicacion: str | None = None
    activo: bool | None = None
    codigos: list[CodigoIn] | None = None


class PreciosMasivoIn(Base):
    porcentaje: float
    categoria_id: int | None = None
    proveedor_id: int | None = None
    redondeo: int = 50
    simular: bool = True


class DenominacionIn(Base):
    denominacion: int
    cantidad: int


class AbrirTurnoIn(Base):
    base: int | None = None
    denominaciones: list[DenominacionIn] | None = None


class CerrarTurnoIn(Base):
    denominaciones: list[DenominacionIn] | None = None
    efectivo_contado: int | None = None
    banco_reportado: int | None = None
    observaciones: str | None = None


class MovimientoCajaIn(Base):
    tipo: str
    monto: int
    motivo: str


class CajonIn(Base):
    motivo: str = ""


class ItemVentaIn(Base):
    producto_id: int
    cantidad: int
    descuento: int = 0


class PagoIn(Base):
    medio_pago_id: int
    monto: int
    recibido: int | None = None
    referencia: str | None = None


class VentaIn(Base):
    items: list[ItemVentaIn]
    pagos: list[PagoIn]
    descuento_global: int = 0
    cliente_id: int | None = None


class AnularIn(Base):
    motivo: str


class ItemDevolucionIn(Base):
    venta_item_id: int
    cantidad: int
    danado: bool = False


class DevolucionIn(Base):
    items: list[ItemDevolucionIn]
    medio_reintegro: str
    motivo: str


class SuspenderIn(Base):
    carrito: dict
    etiqueta: str | None = None


class MermaIn(Base):
    producto_id: int
    cantidad: int
    motivo: str
    nota: str | None = None


class AjusteIn(Base):
    producto_id: int
    nuevo_stock: int | None = None
    delta: int | None = None
    nota: str


class ItemCompraIn(Base):
    producto_id: int
    cantidad: int
    costo_unitario: float
    nuevo_precio: int | None = None


class CompraIn(Base):
    proveedor_id: int | None = None
    numero_factura: str | None = None
    nota: str | None = None
    items: list[ItemCompraIn]


class ProgramacionIn(Base):
    nombre: str
    tipo: str = "total"
    alcance: dict = {}
    frecuencia: str = "una_vez"
    intervalo: int = 1
    proxima_fecha: str
    activo: bool = True


class ConteoIn(Base):
    nombre: str
    tipo: str = "total"
    alcance: dict = {}
    programacion_id: int | None = None


class CapturaIn(Base):
    codigo: str | None = None
    producto_id: int | None = None
    cantidad: int
    ubicacion: str | None = None


class RecontarIn(Base):
    producto_ids: list[int]


class AplicarConteoIn(Base):
    asumir_cero_no_contados: bool = False


class RestaurarIn(Base):
    archivo: str
    password: str
