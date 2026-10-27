<#
 Prueba el programa empaquetado (PyInstaller) como lo usaría la tienda: lo abre, espera que responda, hace una venta de
 punta a punta por la API (contraseñas Argon2, SQLite, recibo PDF, Excel) y comprueba que abrió su ventana de escritorio.
   ./scripts/ci/probar_exe.ps1 -Exe dist/POSSupermercado/POSSupermercado.exe
#>
param(
  [Parameter(Mandatory = $true)][string]$Exe,
  [int]$Puerto = 8799,
  [string]$Captura = ""
)
$ErrorActionPreference = "Stop"
$temp = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { $env:TEMP }
$datos = Join-Path $temp "pos-datos-$Puerto"
Remove-Item $datos -Recurse -Force -ErrorAction SilentlyContinue
$env:POS_DATA_DIR = $datos; $env:POS_PUERTO = "$Puerto"; $env:POS_SIN_JOBS = "1"
$base = "http://127.0.0.1:$Puerto"

function Registro { if (Test-Path "$datos\pos.log") { Write-Host "----- pos.log -----"; Get-Content "$datos\pos.log" -Tail 60 } }
function Llamar($metodo, $ruta, $cuerpo = $null, $token = $null) {
  $h = @{}; if ($token) { $h["Authorization"] = "Bearer $token" }
  $p = @{ Method = $metodo; Uri = "$base$ruta"; Headers = $h; TimeoutSec = 30 }
  if ($null -ne $cuerpo) { $p["Body"] = ($cuerpo | ConvertTo-Json -Depth 8); $p["ContentType"] = "application/json" }
  Invoke-RestMethod @p
}

Write-Host "Abriendo $Exe"
$proceso = Start-Process -FilePath $Exe -PassThru
try {
  $ok = $false
  for ($i = 0; $i -lt 90; $i++) {
    if ($proceso.HasExited) { break }
    try { $r = Invoke-RestMethod "$base/api/salud" -TimeoutSec 2; if ($r.ok) { $ok = $true; break } } catch { }
    Start-Sleep -Seconds 1
  }
  if (-not $ok) { Registro; throw "El programa empaquetado no respondió (terminó: $($proceso.HasExited))." }
  Write-Host "Responde. Versión: $($r.version)"

  # la interfaz está dentro del paquete
  foreach ($ruta in "/", "/js/app.js", "/css/app.css", "/vendor/vue.global.prod.js", "/fonts/inter.woff2") {
    try { $x = Invoke-WebRequest "$base$ruta" -UseBasicParsing -TimeoutSec 20; Write-Host "  $ruta -> $($x.StatusCode) ($($x.Content.Length) bytes)" }
    catch { if ($ruta -like "/fonts/*") { Write-Host "  $ruta (opcional) no está" } else { throw "Falta $ruta en el paquete: $_" } }
  }

  # una jornada mínima por la API
  $s = Llamar POST "/api/setup" @{ negocio = @{ nombre = "Prueba Windows"; nit = "1" }; admin = @{ nombre = "Admin"; usuario = "admin"; password = "secreto1"; pin = "1234" } }
  $t = $s.token
  $cat = Llamar GET "/api/catalogos" $null $t
  $imp = ($cat.impuestos | Where-Object { $_.nombre -eq "Excluido" }).id
  $ef = ($cat.medios_pago | Where-Object { $_.nombre -eq "Efectivo" }).id
  $tomate = Llamar POST "/api/productos" @{ nombre = "Tomate"; precio_venta = 3500; costo_promedio = 2400; stock_inicial = 40.5; unidad = "kg"; impuesto_id = $imp; codigo_interno = "101" } $t
  $leche = Llamar POST "/api/productos" @{ nombre = "Leche"; precio_venta = 4200; costo_promedio = 3000; stock_inicial = 10; impuesto_id = $imp; codigos = @(@{ codigo = "7701"; unidades = 1 }) } $t
  Llamar POST "/api/turnos/abrir" @{ base = 50000 } $t | Out-Null
  $v = Llamar POST "/api/ventas" @{ items = @(@{ producto_id = $tomate.id; cantidad = 1.25 }, @{ producto_id = $leche.id; cantidad = 2 }); pagos = @(@{ medio_pago_id = $ef; monto = 12775; recibido = 20000 }) } $t
  if ($v.total -ne 12775) { throw "Total inesperado: $($v.total)" }
  Write-Host "Venta registrada: $($v.numero) por $($v.total) (peso: $($v.items[0].cantidad) kg)"
  $pdf = Invoke-WebRequest "$base/api/ventas/$($v.id)/recibo" -Headers @{ Authorization = "Bearer $t" } -UseBasicParsing
  if ([System.Text.Encoding]::ASCII.GetString($pdf.Content[0..3]) -ne "%PDF") { throw "El recibo no es un PDF" }
  $xlsx = Invoke-WebRequest "$base/api/informes/ventas_producto?formato=xlsx" -Headers @{ Authorization = "Bearer $t" } -UseBasicParsing
  if ($xlsx.Content[0] -ne 80 -or $xlsx.Content[1] -ne 75) { throw "El informe de Excel no es un .xlsx" }
  $rs = Llamar POST "/api/respaldos" $null $t
  Write-Host "Respaldo creado: $($rs.archivo)"
  Write-Host "Jornada de prueba OK (contraseñas, SQLite, recibo PDF, Excel, respaldo)."

  # ventana de escritorio (WebView2): el proceso debe tener una ventana con el nombre del programa
  $titulo = ""
  for ($i = 0; $i -lt 40; $i++) {
    $proceso.Refresh()
    if ($proceso.MainWindowTitle) { $titulo = $proceso.MainWindowTitle; break }
    Start-Sleep -Seconds 1
  }
  if ($Captura) {
    try {
      Add-Type -AssemblyName System.Windows.Forms, System.Drawing
      $b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
      $bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
      [System.Drawing.Graphics]::FromImage($bmp).CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
      $bmp.Save($Captura); Write-Host "Captura de pantalla: $Captura"
    } catch { Write-Host "No se pudo capturar la pantalla: $_" }
  }
  Registro
  if ($titulo -eq "POS Supermercado") { Write-Host "VENTANA: OK (título «$titulo»)" }
  else { Write-Host "VENTANA: NO se detectó la ventana de escritorio (título «$titulo»); el programa usó el navegador."; if ($env:EXIGIR_VENTANA -eq "1") { throw "Sin ventana de escritorio" } }
}
finally {
  Get-Process -Name "POSSupermercado" -ErrorAction SilentlyContinue | Stop-Process -Force
}
