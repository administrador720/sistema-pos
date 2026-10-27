# POS Supermercado

Sistema de punto de venta para un supermercado que **funciona en un solo computador y guarda toda la
información en él** (no depende de internet). Interfaz moderna y descansada, pensada para usarse casi
todo con teclado y lector de código de barras.

![Panel de control](docs/img/dashboard.png)

## Qué incluye

| Área | Qué hace |
|---|---|
| **Caja** | Venta con lector de código de barras siempre enfocado · cantidad con `6*` · pago en **efectivo** (con devuelta), **banco** (débito, crédito, transferencia/QR) o **mixto** · ventas suspendidas · descuentos · anulaciones y devoluciones con PIN del administrador · cajón monedero · recibo en PDF. |
| **Verduras y frutas (por peso)** | Productos que se venden **por kilo**: el cajero escribe lo que marca la balanza (o «$5.000 de tomate») y el sistema calcula el valor. Código corto (PLU), botones rápidos para las verduras de todos los días (F1), stock en kilos con gramos, compras, mermas, conteos y devoluciones por peso. |
| **Turnos** | Al abrir caja pregunta la **base** (el efectivo con el que se da devueltas; se puede contar por billetes y monedas). Al cerrar hace un **arqueo ciego**: el cajero cuenta sin ver cuánto debería haber; el sistema calcula sobrante/faltante en efectivo y en banco. Retiros e ingresos con motivo y autorización. |
| **Inventario** | Productos con varios códigos de barras (y códigos de paca), kardex de cada movimiento, compras con **costo promedio ponderado**, mermas, ajustes, alertas de stock, importación desde Excel y cambio masivo de precios. |
| **Conteos** | El administrador decide **cuándo** contar (manual o programado: cada N días, semanal, quincenal, mensual) y qué (todo, una parte, o cíclico). Captura **ciega** con el lector, se puede contar con la tienda abierta (el stock teórico es el del momento exacto de cada captura), revisión de **inconsistencias** (faltantes/sobrantes en pesos, faltantes repetidos en conteos seguidos, exactitud), reconteo y aplicación de ajustes. |
| **Panel e informes** | Ventas, margen, ticket promedio, **rotación de inventario**, días de inventario, GMROI, análisis ABC, mapa de calor de horas, productos sin movimiento, sugerido de compras, mermas, IVA por tarifa, diferencias de caja por cajero… 22 informes con exportación a Excel y PDF. |
| **Seguridad** | Roles (administrador / cajero), PIN para acciones sensibles, auditoría de lo importante, bloqueo de pantalla, bloqueo tras intentos fallidos, respaldos automáticos con copia externa. |

## Capturas

| Caja: escaneo, carrito y atajos | Cobro en efectivo con devuelta |
|---|---|
| ![Caja](docs/img/caja.png) | ![Cobro](docs/img/cobro-efectivo.png) |

| Abrir caja con la base | Revisión de inconsistencias de un conteo |
|---|---|
| ![Abrir caja](docs/img/abrir-caja.png) | ![Conteo](docs/img/conteo-revision.png) |

| Rotación de inventario (informes) | Panel de control en tema oscuro |
|---|---|
| ![Informes](docs/img/informes.png) | ![Panel oscuro](docs/img/dashboard-oscuro.png) |

## Cómo empezar

### En Windows (paso a paso)

1. **Instale Python** desde <https://www.python.org/downloads/>. Durante la instalación **marque la casilla "Add python.exe to PATH"**. Se necesita la versión 3.11 o superior.
2. **Descargue el programa**: en GitHub entre al repositorio, botón verde **Code → Download ZIP**
   (o directo: <https://github.com/administrador720/sistema-pos/archive/refs/heads/claude/awesome-fermi-sodsun.zip>) y descomprímalo, por ejemplo en `C:\POS`.
3. Abra la carpeta descomprimida y haga **doble clic en `iniciar.bat`**.
   La primera vez necesita internet y tarda unos minutos preparando todo; después abre en segundos.
4. La primera vez le pide los datos del negocio y crea al administrador.

> **Desde la ventana de comandos** (cmd) primero entre a la carpeta y luego escriba solo `iniciar.bat`
> (sin `./` y sin `.sh`; ese archivo es para Linux/macOS):
> ```
> cd C:\POS\sistema-pos-claude-awesome-fermi-sodsun
> iniciar.bat
> ```

Para **conocerlo con datos de ejemplo** haga doble clic en `demo.bat` (borra lo que haya, no lo use en la tienda) y luego abra `iniciar.bat`.
Usuarios de la demostración: `admin` / `demo1234` (PIN 1234) · `ana` / `ana1234` y `luis` / `luis1234` (PIN 4321).

### En Linux o macOS

```bash
./iniciar.sh                                              # la primera vez prepara el entorno
cd backend && ../.venv/bin/python -m app.seed_demo --forzar   # opcional: datos de ejemplo
```

### En la tienda

1. Instale (instalador de Windows, ver *Empaquetado*) o ejecute `iniciar.bat`.
2. La **primera vez** el sistema pide los datos del negocio y crea al administrador (usuario, contraseña y PIN). No hay contraseñas por defecto.
3. Cargue los productos: **Productos → Importar Excel** (hay plantilla), o créelos uno a uno.
4. Haga un **conteo total inicial** (Conteos → Nuevo conteo → Todo el inventario): ese es el stock de arranque.
5. Cree los usuarios de los cajeros (Configuración → Usuarios) y configure el **cajón** y la **carpeta de respaldos externa**.

## Uso diario

**Cajero:** inicia sesión → *Abrir caja* (base) → vende → *Cerrar caja* (cuenta el efectivo).

| Tecla | Acción | | Tecla | Acción |
|---|---|---|---|---|
| `Enter` | agregar lo escaneado | | `F6` / `F7` | suspender / retomar venta |
| `6*` + escanear | 6 unidades | | `F8` | ventas del turno (recibo, anular, devolución) |
| `1,25*` + código corto | 1,250 kg sin preguntar | | `F9` `F10` `F11` | cobrar: efectivo / banco / mixto |
| `F1` | verduras y frutas (botones) | | `F12` | retiro, ingreso o abrir cajón |
| `F2` | buscar por nombre | | `Esc` | cancelar venta |
| `F3` | cambiar cantidad o peso | | `↑` `↓` `+` `-` | elegir línea / cantidad |
| `F4` / `Supr` | quitar línea | | `F5` | descuento |

## Verduras y frutas: venta por peso

El supermercado vende verduras por kilo y con mucha variedad. Cada una se crea como un producto **«Se vende por peso (kg)»**: el **precio y el costo son por kilo**, las existencias están en kilos (con gramos: 40,500 kg) y la caja pide el peso en vez de la cantidad.

![Caja con verduras por peso](docs/img/caja-peso.png)

**Configurar (una vez):** *Productos → Nuevo producto* → «Se vende por peso (kg)» → nombre, precio por kilo, costo por kilo y existencias en kg. Ponga un **código corto (PLU)** como `101` y marque **«Botón rápido en la caja»** en las que más se venden. También se pueden cargar todas desde Excel: la plantilla trae las columnas `unidad` (`kg`) y `plu`.

**Vender (balanza común en la caja):** el cajero pesa, y luego…

| Quiere | Haga |
|---|---|
| Elegir de los botones | `F1` → toque la verdura → escriba el peso → `Enter` |
| Escribir el código corto | `101` + `Enter` → escriba el peso → `Enter` |
| Escribir el peso antes | `1,25*101` + `Enter` (agrega 1,250 kg de una vez) |
| «$5.000 de tomate» | en la ventana de peso, pestaña **Valor en pesos** → `5000` (se cobra exacto y el peso se calcula) |
| Buscar por nombre | `F2`, escriba «tomate» y elija |
| Corregir un peso | seleccione la línea → `F3` |

| Botones rápidos (F1) | Ventana de peso |
|---|---|
| ![Botones rápidos](docs/img/rapidos.png) | ![Peso](docs/img/peso.png) |

* El valor de cada línea se calcula en pesos enteros (`0,350 kg × $3.500 = $1.225`), igual en pantalla, en el servidor y en el recibo.
* Las **devoluciones** también son por peso (se puede devolver 0,750 kg de 2 kg) y lo dañado sale como merma.
* En **conteos** de inventario, los productos por peso siempre preguntan los kilos contados.
* Un producto por unidad solo acepta cantidades enteras; uno por peso acepta hasta 3 decimales (gramos). El sistema avisa si se intenta otra cosa.
* No se puede cambiar la unidad de un producto que ya tiene movimientos (confundiría el historial): desactívelo y cree uno nuevo.
* Los informes suman unidades y kilos en la misma columna («Unid. / kg»); el panel cuenta como «artículos por tiquete» solo las unidades.

## Olvidé mi contraseña

* **Es cajero:** el administrador la cambia en *Configuración → Usuarios* (clic en el usuario → nueva contraseña o PIN).
* **Es el administrador:** cierre el programa y haga doble clic en **`restablecer_clave.bat`**. Muestra los usuarios, pregunta cuál restablecer y pide la nueva contraseña (y, si quiere, un PIN nuevo). Hay que estar en el computador donde está instalado; queda registrado en la auditoría.
* Para ingresar se usa el **usuario** (por ejemplo `admin`), no el nombre. Tras 5 intentos fallidos el ingreso se bloquea 5 minutos.

## Datos, respaldos y recuperación

* Base de datos: un archivo SQLite en `C:\ProgramData\POSSupermercado\data\pos.db` (Windows) o `~/.local/share/pos-supermercado/data/` (Linux). Variable `POS_DATA_DIR` para cambiarla.
* **Respaldo automático** diario (a la hora configurada; si el equipo estaba apagado, al encenderlo) y al cerrar cada turno. Se hace con la API de *backup* de SQLite: es consistente aunque se esté vendiendo y **no bloquea las ventas**.
* **Copia externa**: configure una carpeta en un USB, disco externo o carpeta sincronizada (Google Drive para escritorio, OneDrive, Dropbox). El panel avisa si el último respaldo externo es viejo.
* Restaurar: *Configuración → Respaldos → Restaurar* (pide contraseña; antes guarda una copia de lo actual).
* Un corte de luz no deja ventas a medias: cada venta es una transacción atómica (SQLite en modo WAL con `synchronous=FULL`). Se recomienda un **UPS**.

## Hardware

* **Lector de código de barras**: cualquier USB tipo teclado (no necesita drivers).
* **Cajón monedero**: Configuración → *Cajón monedero*. Tres formas de conexión: puerto serie/USB propio, a través de una impresora térmica instalada en Windows (cable RJ11), o dispositivo de archivo. Sin cajón configurado, todo funciona igual.
  Se abre al cobrar en efectivo, al abrir caja y en retiros. *Pendiente de probar con hardware real* (ver abajo).
* **Impresora**: por ahora el recibo es un PDF de 80 mm para ver/imprimir. La impresión directa en térmica (ESC/POS) es una mejora futura.

## Facturación electrónica (DIAN)

Todavía no está implementada: hoy se entrega un tiquete interno. El diseño ya está preparado (consecutivo configurable, datos del cliente, impuestos desglosados por línea, campos `estado_dian`/`cude`, interfaz `ProveedorDIAN` en `backend/app/fiscal/`). **Confirme con su contador si el negocio ya está obligado a emitir el documento equivalente electrónico POS**; si lo está, esta es la siguiente fase.

## Desarrollo

```
backend/app/          FastAPI: models, services (reglas de negocio), routers (API), jobs, hardware, fiscal
backend/tests/        pruebas (reglas de negocio, robustez, interfaz en navegador real, volumen)
frontend/             Vue 3 sin paso de compilación; librerías incluidas (funciona sin internet)
installer/            PyInstaller (.spec) e Inno Setup (.iss)
launcher.py           arranca el servidor local + la ventana de escritorio (pywebview)
docs/                 plan original y arquitectura
```

```bash
cd backend
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt   # Windows: .venv\Scripts\...
python -m pytest -q                       # 60+ pruebas; las de interfaz usan Chromium (python -m playwright install chromium)
python tests/perf_volumen.py              # 30.000 productos y un año de ventas (~1 millón de líneas)
python -m uvicorn app.main:app --reload   # API + interfaz en http://127.0.0.1:8765  (docs de la API: /api/docs)
```

### Rendimiento medido

Con 30.000 productos y 943.000 líneas de venta (un año a 300 ventas diarias):

| Operación | Tiempo | Objetivo |
|---|---:|---:|
| Escanear un código de barras | 6 ms | < 100 ms |
| Buscar un producto por nombre (F2) | 55 ms | < 300 ms |
| Cobrar una venta de 10 productos | 45 ms | < 300 ms |
| Panel de control, 30 días / 1 año | 0,4 s / 1,5 s | < 2 s / < 3 s |
| Informes anuales (ventas, rentabilidad, ABC, IVA, sin movimiento…) | 0,1 – 1,3 s | < 2 s |
| Rotación de inventario (30 días) | 0,9 s (la 1.ª vez 4,7 s: crea las fotos diarias) | < 2 s |
| Iniciar / cerrar captura / revisar un conteo de 30.000 productos | 0,04 s / 1,5 s / 0,9 s | < 5 s |
| Exportar a Excel las ventas por producto del año | 1,8 s | < 5 s |
| Respaldo manual de una base de 250 MB (no bloquea las ventas) | 11 s | < 20 s |

### Empaquetado (Windows)

`scripts\build_windows.bat` genera `dist\POSSupermercado\` con PyInstaller y, si tiene Inno Setup 6, el instalador `.exe`.
La ventana usa Microsoft Edge WebView2 (incluido en Windows 10/11 actualizados).
> **Estado:** el empaquetado se verificó construyendo y arrancando el ejecutable en Linux; los scripts de **Windows** (`.bat`, `.iss`) y la ventana nativa **no se han probado en Windows**.

## Seguridad

El servidor solo escucha en `127.0.0.1` y rechaza peticiones cuyo `Host` no sea local. Contraseñas y PIN con Argon2; sesiones por token; bloqueo temporal tras 5 intentos fallidos; precios y totales siempre se recalculan en el servidor; el cajero no recibe costos ni márgenes; las ventas nunca se borran (se anulan) y las acciones sensibles quedan en la auditoría con quién las autorizó.

## Limitaciones conocidas

No incluye (aún): balanza conectada por cable (hoy el cajero escribe el peso) o etiquetas de balanza con el precio en el código de barras, impresión directa en térmica, facturación DIAN, varias cajas en red, crédito (fiado), lotes y vencimientos, promociones, clientes en la pantalla de venta (la API ya los soporta). Ver `docs/plan.md` (fase 7).
