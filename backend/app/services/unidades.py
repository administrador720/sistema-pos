"""Unidades de medida: productos por unidad (u) y productos por peso (kg).

Las cantidades de un producto por peso son kilos con hasta 3 decimales (gramos): 1,250 kg. Las de un producto por
unidad son siempre enteras. El dinero sigue en pesos enteros: `core.valor_linea` calcula precio × cantidad con
aritmética entera, así el total de una línea nunca tiene fracciones de peso.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..core import ErrorNegocio, cant

UNIDADES = {"u": "Unidad", "kg": "Kilo"}
MAX_KG_POR_LINEA = 1000  # tope de cordura: evita escribir 25 kg como 2500


def es_peso(producto: m.Producto) -> bool:
    return producto.unidad == "kg"


def texto(unidad: str, cantidad) -> str:
    """Cantidad legible: «6» o «1,250 kg»."""
    c = cant(cantidad)
    if unidad == "kg":
        return f"{c:.3f}".replace(".", ",") + " kg"
    return str(int(c)) if c == int(c) else str(c).replace(".", ",")


def normalizar(producto: m.Producto, cantidad, *, permitir_cero: bool = False, permitir_negativo: bool = False):
    """Valida y redondea la cantidad que se le pide a un producto según su unidad."""
    try:
        c = float(cantidad)
    except (TypeError, ValueError):
        raise ErrorNegocio(f"Cantidad no válida para «{producto.nombre}».")
    if c != c or c in (float("inf"), float("-inf")):
        raise ErrorNegocio(f"Cantidad no válida para «{producto.nombre}».")
    if es_peso(producto):
        c = cant(c)
        if abs(c) > MAX_KG_POR_LINEA:
            raise ErrorNegocio(f"{texto('kg', c)} de «{producto.nombre}» parece un error de digitación (máximo "
                               f"{MAX_KG_POR_LINEA} kg por línea).")
    else:
        if c != int(c):
            raise ErrorNegocio(f"«{producto.nombre}» se vende por unidad: la cantidad debe ser un número entero.")
        c = int(c)
    if c < 0 and not permitir_negativo:
        raise ErrorNegocio(f"La cantidad de «{producto.nombre}» no puede ser negativa.")
    if c == 0 and not permitir_cero:
        raise ErrorNegocio(f"Indique una cantidad mayor a cero para «{producto.nombre}»."
                           + (" El peso mínimo es 0,001 kg (1 gramo)." if es_peso(producto) else ""))
    return c


def mapa(db: Session, producto_ids) -> dict[int, str]:
    """{producto_id: unidad} para un conjunto de productos (una consulta)."""
    ids = list({int(i) for i in producto_ids})
    if not ids:
        return {}
    return {pid: u for pid, u in db.execute(select(m.Producto.id, m.Producto.unidad).where(m.Producto.id.in_(ids)))}
