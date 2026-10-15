"""Facturación electrónica DIAN — punto de extensión (aún no implementado).

Cuando el supermercado deba emitir el *documento equivalente electrónico POS*, se implementa
``ProveedorDIAN`` conectando la API de un proveedor tecnológico autorizado y se registra en
``proveedor_activo``. El flujo previsto:

1. Al cobrar, la venta queda con ``estado_dian = 'pendiente'`` (hoy: ``'no_aplica'``).
2. Una cola en segundo plano llama a ``enviar(venta)``; si no hay internet, reintenta después
   (la venta NUNCA se bloquea por falta de conexión).
3. La respuesta actualiza ``estado_dian`` (enviado / aceptado / rechazado) y guarda el ``cude``.

Ya están listos: prefijo y consecutivo configurables, datos del cliente (tipo y número de documento),
desglose de impuestos por línea y los campos ``estado_dian`` y ``cude`` en ``ventas``.
"""
from __future__ import annotations

from typing import Protocol


class ProveedorDIAN(Protocol):
    def enviar(self, venta_id: int) -> dict:
        """Envía el documento equivalente de la venta. Devuelve {'estado': ..., 'cude': ...}."""
        ...


class ProveedorNulo:
    """Por ahora no se emite nada: las ventas quedan con estado «no_aplica»."""

    def enviar(self, venta_id: int) -> dict:
        return {"estado": "no_aplica", "cude": None}


proveedor_activo: ProveedorDIAN = ProveedorNulo()
