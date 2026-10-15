@echo off
setlocal
cd /d "%~dp0"
title POS Supermercado

rem --- 1. Buscar Python 3.11 o superior
set "PY="
for %%C in ("py -3" "python" "python3") do (
  if not defined PY (
    %%~C -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul && set "PY=%%~C"
  )
)
if not defined PY goto :sinpython

rem --- 2. Preparar el programa la primera vez (necesita internet)
if exist ".venv\Scripts\python.exe" goto :iniciar
echo.
echo Preparando el programa por primera vez. Necesita internet y tarda unos minutos...
echo.
%PY% -m venv .venv
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
if errorlevel 1 goto :error
echo.
echo Instalando componentes opcionales: ventana propia y cajon monedero...
for %%P in (pywebview pyserial pywin32) do (
  ".venv\Scripts\python.exe" -m pip install %%P >nul 2>nul || echo   Aviso: no se pudo instalar %%P, que es opcional.
)

:iniciar
echo.
echo Iniciando POS Supermercado...
".venv\Scripts\python.exe" launcher.py %*
if errorlevel 1 goto :fallo
endlocal
exit /b 0

:sinpython
echo.
echo No se encontro Python 3.11 o superior en este computador.
echo.
echo 1. Descargue Python desde https://www.python.org/downloads/
echo 2. Al instalar, MARQUE la casilla "Add python.exe to PATH".
echo 3. Cuando termine, vuelva a abrir este archivo.
echo.
pause
exit /b 1

:error
echo.
echo No se pudo preparar el programa. Revise la conexion a internet y vuelva a intentar.
echo Si el problema sigue, borre la carpeta .venv y abra este archivo de nuevo.
echo.
pause
exit /b 1

:fallo
echo.
echo El programa se cerro con un error. El detalle esta en el archivo pos.log dentro de
echo la carpeta C:\ProgramData\POSSupermercado
echo.
pause
exit /b 1
