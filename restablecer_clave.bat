@echo off
setlocal
cd /d "%~dp0backend"
title Restablecer contrasena - POS Supermercado
if not exist "..\.venv\Scripts\python.exe" (
  echo Primero abra iniciar.bat una vez para preparar el programa.
  pause
  exit /b 1
)
echo.
echo RESTABLECER CONTRASENA
echo Cierre el programa antes de continuar si esta abierto.
echo.
"..\.venv\Scripts\python.exe" -m app.reset_clave %*
echo.
pause
endlocal
