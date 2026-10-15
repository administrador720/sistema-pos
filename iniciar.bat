@echo off
rem Inicia el POS en modo desarrollo (crea el entorno de Python la primera vez).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Preparando el entorno la primera vez, esto tarda unos minutos...
  py -3 -m venv .venv || goto :error
  .venv\Scripts\python -m pip install --upgrade pip
  .venv\Scripts\python -m pip install -r backend\requirements.txt || goto :error
)
.venv\Scripts\python launcher.py %*
exit /b
:error
echo No se pudo preparar el entorno. Verifique que Python 3.11 o superior este instalado.
pause
