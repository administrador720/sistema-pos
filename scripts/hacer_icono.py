"""Genera el ícono del programa (installer/icono.ico) para el .exe, el instalador y el acceso directo del escritorio.

    python scripts/hacer_icono.py                       # usa installer/logo.png si existe; si no, un ícono genérico
    python scripts/hacer_icono.py --logo mi_logo.png    # con el logo del negocio
    python scripts/hacer_icono.py --generico            # fuerza el ícono genérico

Requiere Pillow (pip install pillow). El logo puede ser cualquier PNG/JPG: se centra en un cuadrado con un pequeño
margen. Si el logo tiene fondo transparente se conserva; si no, se ve tal cual.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw

RAIZ = Path(__file__).resolve().parents[1]
TAMANOS = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)]
VERDE_CLARO, VERDE_OSCURO = (20, 150, 139), (11, 90, 84)   # mismo verde de la interfaz


def _degradado(n: int) -> Image.Image:
    img = Image.new("RGB", (n, n))
    px = img.load()
    for y in range(n):
        t = y / (n - 1)
        color = tuple(round(a + (b - a) * t) for a, b in zip(VERDE_CLARO, VERDE_OSCURO))
        for x in range(n):
            px[x, y] = color
    return img


def icono_generico(n: int = 1024) -> Image.Image:
    """Cuadrado redondeado verde con una tienda blanca (toldo, fachada, ventana y puerta)."""
    fondo = _degradado(n).convert("RGBA")
    mascara = Image.new("L", (n, n), 0)
    ImageDraw.Draw(mascara).rounded_rectangle((0, 0, n - 1, n - 1), radius=int(n * 0.225), fill=255)
    fondo.putalpha(mascara)
    d = ImageDraw.Draw(fondo)
    blanco, crema = (255, 255, 255, 255), (214, 239, 236, 255)
    u = n / 1024

    def r(x0, y0, x1, y1):
        return (round(x0 * u), round(y0 * u), round(x1 * u), round(y1 * u))
    # techo
    d.rounded_rectangle(r(176, 236, 848, 300), radius=int(24 * u), fill=blanco)
    # toldo a rayas con borde festoneado
    x0, x1, y0, y1, franjas = 196, 828, 300, 452, 6
    ancho = (x1 - x0) / franjas
    for i in range(franjas):
        a, b = x0 + i * ancho, x0 + (i + 1) * ancho
        d.rectangle(r(a, y0, b, y1), fill=blanco if i % 2 == 0 else crema)
        d.pieslice(r(a, y1 - ancho / 2, b, y1 + ancho / 2), 0, 180, fill=blanco if i % 2 == 0 else crema)
    # fachada con ventana y puerta
    d.rectangle(r(236, 500, 788, 776), fill=blanco)
    verde = VERDE_OSCURO + (255,)
    d.rounded_rectangle(r(292, 548, 500, 690), radius=int(18 * u), fill=verde)
    d.rounded_rectangle(r(560, 548, 732, 776), radius=int(18 * u), fill=verde)
    d.ellipse(r(690, 668, 712, 690), fill=blanco)
    return fondo


def desde_logo(ruta: Path, n: int = 1024) -> Image.Image:
    logo = Image.open(ruta).convert("RGBA")
    lado = round(n * 0.9)
    logo.thumbnail((lado, lado), Image.LANCZOS)
    lienzo = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    lienzo.paste(logo, ((n - logo.width) // 2, (n - logo.height) // 2), logo)
    return lienzo


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--logo", type=Path, help="imagen con el logo del negocio (por defecto installer/logo.png si existe)")
    ap.add_argument("--generico", action="store_true", help="usar el ícono genérico aunque haya logo")
    ap.add_argument("--salida", type=Path, default=RAIZ / "installer" / "icono.ico")
    ap.add_argument("--png", type=Path, help="además, guardar una copia PNG de 512 px")
    a = ap.parse_args()
    logo = a.logo or (RAIZ / "installer" / "logo.png")
    if not a.generico and logo.is_file():
        base, origen = desde_logo(logo), f"logo {logo}"
    else:
        base, origen = icono_generico(), "ícono genérico"
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    grande = base.resize((256, 256), Image.LANCZOS)
    grande.save(a.salida, format="ICO", sizes=TAMANOS)
    if a.png:
        base.resize((512, 512), Image.LANCZOS).save(a.png)
    print(f"Ícono creado en {a.salida} a partir de: {origen}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
