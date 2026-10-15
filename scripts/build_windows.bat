@echo off
rem Genera el instalador de Windows. Requisitos: Python 3.11+ y (opcional) Inno Setup 6 con iscc.exe en el PATH.
setlocal
cd /d "%~dp0\.."
if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r backend\requirements.txt pywebview pyserial pywin32 pyinstaller
if errorlevel 1 goto :error
".venv\Scripts\pyinstaller.exe" installer\pos.spec --noconfirm --distpath dist --workpath build
if errorlevel 1 goto :error
echo.
echo Carpeta lista: dist\POSSupermercado\POSSupermercado.exe
where iscc >nul 2>nul
if errorlevel 1 (
  echo Inno Setup no encontrado: instale Inno Setup 6 para generar el instalador .exe
) else (
  iscc installer\instalador.iss
)
endlocal
exit /b 0
:error
echo Fallo la construccion.
exit /b 1
