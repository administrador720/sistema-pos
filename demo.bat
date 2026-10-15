@echo off
setlocal
cd /d "%~dp0backend"
if not exist "..\.venv\Scripts\python.exe" (
  echo Primero abra iniciar.bat una vez para preparar el programa.
  pause
  exit /b 1
)
echo.
echo ATENCION: esto BORRA toda la informacion actual del sistema y carga datos de ejemplo
echo (productos, ventas de los ultimos 30 dias, cierres de caja y un conteo).
echo Sirve para conocer el sistema. NO lo use en la computadora de la tienda.
echo.
set /p OK=Escriba SI para continuar: 
if /i not "%OK%"=="SI" exit /b 0
"..\.venv\Scripts\python.exe" -m app.seed_demo --dias 30 --ventas-dia 90 --forzar
if errorlevel 1 goto :error
echo.
echo Listo. Ahora abra iniciar.bat
echo   Administrador: usuario admin  contrasena demo1234  PIN 1234
echo   Cajera:        usuario ana    contrasena ana1234   PIN 4321
echo.
pause
endlocal
exit /b 0
:error
echo.
echo No se pudo cargar la demostracion.
pause
exit /b 1
