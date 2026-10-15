# -*- mode: python ; coding: utf-8 -*-
# PyInstaller: genera dist/POSSupermercado/ (carpeta con el .exe y todo lo necesario).
#   pyinstaller installer/pos.spec --noconfirm
import os
import sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# Rutas absolutas a partir de la ubicación de este archivo (SPECPATH): funciona se ejecute desde donde se ejecute
RAIZ = os.path.abspath(os.path.join(SPECPATH, ".."))
BACKEND = os.path.join(RAIZ, "backend")
sys.path.insert(0, BACKEND)   # para que collect_submodules("app") encuentre el paquete

ocultos = (collect_submodules("uvicorn") + collect_submodules("app") + collect_submodules("argon2")
           + ["sqlalchemy.dialects.sqlite", "multipart", "python_multipart", "openpyxl", "serial", "email.mime.text"])
if sys.platform == "win32":
    ocultos += ["win32print", "win32timezone"]

a = Analysis(
    [os.path.join(RAIZ, "launcher.py")],
    pathex=[BACKEND],
    datas=[(os.path.join(RAIZ, "frontend"), "frontend")] + collect_data_files("reportlab"),
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
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="POSSupermercado")
