<#
 Prueba el instalador de punta a punta en Windows: instala en silencio, comprueba accesos directos, abre el programa,
 simula una ACTUALIZACIÓN encima (el programa abierto lo cierra el instalador y lo vuelve a abrir con /RELANZAR=1) y
 desinstala dejando los datos.
   ./scripts/ci/probar_instalador.ps1 -Instalador dist/Instalador-POS-Supermercado-1.1.0.exe
#>
param([Parameter(Mandatory = $true)][string]$Instalador, [int]$Puerto = 8798)
$ErrorActionPreference = "Stop"
$temp = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { $env:TEMP }
$destino = Join-Path $temp "pos-instalado"
$datos = Join-Path $env:ProgramData "POSSupermercado"
$registro = Join-Path $temp "instalacion.log"
$Instalador = (Resolve-Path $Instalador).Path
$env:POS_PUERTO = "$Puerto"; $env:POS_SIN_JOBS = "1"
$base = "http://127.0.0.1:$Puerto"

function Esperar-Salud([int]$segundos = 60) {
  # el programa que abre el instalador puede no heredar POS_PUERTO: se prueba también el puerto normal
  for ($i = 0; $i -lt $segundos; $i++) {
    foreach ($pt in $Puerto, 8765) {
      try { $r = Invoke-RestMethod "http://127.0.0.1:$pt/api/salud" -TimeoutSec 2; if ($r.ok) { return $r } } catch { }
    }
    Start-Sleep -Seconds 1
  }
  return $null
}
function Instalar($argumentos) {
  $p = Start-Process -FilePath $Instalador -ArgumentList $argumentos -Wait -PassThru
  if ($p.ExitCode -ne 0) { if (Test-Path $registro) { Get-Content $registro -Tail 40 }; throw "El instalador terminó con código $($p.ExitCode)" }
}

Write-Host "== 1. Instalación silenciosa"
Instalar @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/DIR=`"$destino`"", "/LOG=`"$registro`"")
$exe = Join-Path $destino "POSSupermercado.exe"
if (-not (Test-Path $exe)) { throw "No se instaló $exe" }
if (-not (Test-Path (Join-Path $destino "_internal\VERSION"))) { throw "Falta el archivo VERSION dentro de la instalación" }
$icono = Join-Path ([Environment]::GetFolderPath("CommonDesktopDirectory")) "POS Supermercado.lnk"
if (-not (Test-Path $icono)) { throw "No se creó el ícono del escritorio: $icono" }
Write-Host "  Ícono del escritorio: $icono"
$inicio = Get-ChildItem (Join-Path ([Environment]::GetFolderPath("CommonPrograms")) "POS Supermercado") -ErrorAction SilentlyContinue
Write-Host "  Menú Inicio: $($inicio.Name -join ', ')"
if (-not (Test-Path $datos)) { throw "No se creó la carpeta de datos $datos" }
$cuenta = (Get-Acl $datos).Access | Where-Object { $_.IdentityReference -match "Users|Usuarios" } | Select-Object -First 1
Write-Host "  Permisos de la carpeta de datos: $($cuenta.IdentityReference) $($cuenta.FileSystemRights)"

Write-Host "== 2. El programa instalado arranca"
$env:POS_DATA_DIR = Join-Path $temp "pos-datos-inst"
Remove-Item $env:POS_DATA_DIR -Recurse -Force -ErrorAction SilentlyContinue
$proceso = Start-Process -FilePath $exe -PassThru
$r = Esperar-Salud 90
if (-not $r) { throw "El programa instalado no respondió" }
Write-Host "  Responde, versión $($r.version) (proceso $($proceso.Id))"

Write-Host "== 3. Actualización encima con el programa ABIERTO (como lo hace el botón de actualizar)"
$antes = $proceso.Id
Instalar @("/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", "/RELANZAR=1", "/DIR=`"$destino`"", "/LOG=`"$registro`"")
$r = Esperar-Salud 90
if (-not $r) { if (Test-Path $registro) { Get-Content $registro -Tail 60 }; throw "Después de actualizar el programa no volvió a abrir solo" }
$nuevo = Get-Process -Name "POSSupermercado" -ErrorAction SilentlyContinue | Select-Object -First 1
Write-Host "  Volvió a abrir solo: proceso $($nuevo.Id) (antes $antes), versión $($r.version)"
if ($nuevo.Id -eq $antes) { throw "El programa nunca se cerró durante la actualización" }
$nuevo | Stop-Process -Force
Start-Sleep -Seconds 2

Write-Host "== 4. Desinstalar (los datos deben quedar)"
$desinst = Join-Path $destino "unins000.exe"
$p = Start-Process -FilePath $desinst -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -Wait -PassThru
if ($p.ExitCode -ne 0) { throw "El desinstalador terminó con código $($p.ExitCode)" }
Start-Sleep -Seconds 2
if (Test-Path $exe) { throw "El programa sigue instalado después de desinstalar" }
if (Test-Path $icono) { throw "El ícono del escritorio no se quitó" }
if (-not (Test-Path $datos)) { throw "La desinstalación borró la carpeta de datos (no debe)" }
Write-Host "Instalador OK: instala, crea íconos, actualiza con el programa abierto y desinstala conservando los datos."
