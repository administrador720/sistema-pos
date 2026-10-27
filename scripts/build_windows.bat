@echo off
rem Genera el instalador de Windows. Requisitos: Python 3.11+ y (opcional) Inno Setup 6 con iscc.exe en el PATH.
rem Para poner el logo del negocio como icono: guarde el PNG en installer\logo.png antes de ejecutar esto.
setlocal
cd /d "%~dp0\.."
set /p VERSION=<VERSION
if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r backend\requirements.txt pywebview pyserial pywin32 pyinstaller pillow
if errorlevel 1 goto :error
".venv\Scripts\python.exe" scripts\hacer_icono.py
if errorlevel 1 goto :error
".venv\Scripts\pyinstaller.exe" installer\pos.spec --noconfirm --distpath dist --workpath build
if errorlevel 1 goto :error
echo.
echo Carpeta lista: dist\POSSupermercado\POSSupermercado.exe
where iscc >nul 2>nul
if errorlevel 1 (
  echo Inno Setup no encontrado: instale Inno Setup 6 para generar el instalador .exe
) else (
  iscc /DVersion=%VERSION% installer\instalador.iss
)
endlocal
exit /b 0
:error
echo Fallo la construccion.
exit /b 1
