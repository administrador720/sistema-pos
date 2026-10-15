@echo off
rem Genera el instalador de Windows. Requisitos: Python 3.11+ y (opcional) Inno Setup 6 (iscc.exe en el PATH).
cd /d "%~dp0\.."
if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv || goto :error
.venv\Scripts\python -m pip install --upgrade pip || goto :error
.venv\Scripts\python -m pip install -r backend\requirements.txt pyinstaller pywin32 || goto :error
.venv\Scripts\pyinstaller installer\pos.spec --noconfirm --distpath dist --workpath build || goto :error
echo.
echo Carpeta lista: dist\POSSupermercado\POSSupermercado.exe
where iscc >nul 2>nul && (iscc installer\instalador.iss) || echo (Inno Setup no encontrado: instale Inno Setup 6 para generar el instalador .exe)
exit /b 0
:error
echo Fallo la construccion.
exit /b 1
