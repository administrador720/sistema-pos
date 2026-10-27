# -*- mode: python ; coding: utf-8 -*-
# PyInstaller: genera dist/POSSupermercado/ (carpeta con el .exe y todo lo necesario).
#   pyinstaller installer/pos.spec --noconfirm
import os
import sys
from PyInstaller.utils.hooks import collect_all, collect_submodules, collect_data_files

# Rutas absolutas a partir de la ubicación de este archivo (SPECPATH): funciona se ejecute desde donde se ejecute
RAIZ = os.path.abspath(os.path.join(SPECPATH, ".."))
BACKEND = os.path.join(RAIZ, "backend")
sys.path.insert(0, BACKEND)   # para que collect_submodules("app") encuentre el paquete

ocultos = (collect_submodules("uvicorn") + collect_submodules("app") + collect_submodules("argon2")
           + ["sqlalchemy.dialects.sqlite", "multipart", "python_multipart", "openpyxl", "serial", "email.mime.text"])
datos = [(os.path.join(RAIZ, "frontend"), "frontend"), (os.path.join(RAIZ, "VERSION"), ".")] + collect_data_files("reportlab")
binarios = []
if sys.platform == "win32":
    ocultos += ["win32print", "win32timezone", "win32com", "win32com.client"]
    # La ventana de escritorio (pywebview + WebView2 vía .NET): sus DLL y módulos se cargan dinámicamente
    for paquete in ("webview", "clr_loader", "pythonnet"):
        try:
            d, b, h = collect_all(paquete)
            datos += d
            binarios += b
            ocultos += h
        except Exception as e:  # noqa: BLE001
            print(f"AVISO: no se pudo recolectar {paquete}: {e}")
    ocultos += ["clr", "bottle", "proxy_tools"]

ICONO = os.path.join(RAIZ, "installer", "icono.ico")

a = Analysis(
    [os.path.join(RAIZ, "launcher.py")],
    pathex=[BACKEND],
    binaries=binarios,
    datas=datos,
    hiddenimports=ocultos,
    excludes=["tkinter", "matplotlib", "numpy", "pandas", "PIL.ImageTk"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="POSSupermercado",
    console=(sys.platform != "win32"),   # en Windows: sin ventana negra (los mensajes van a pos.log)
    disable_windowed_traceback=False,
    icon=ICONO if os.path.exists(ICONO) else None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="POSSupermercado")
