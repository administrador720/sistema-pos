# Arquitectura y decisiones (estado real, v1.0)

Este documento describe **lo que se construyó** y en qué se aparta del plan original (`plan.md`).

## Vista general

```
┌──────────────── Computador de la tienda ─────────────────┐
│ launcher.py ─► uvicorn (127.0.0.1:8765) ─► FastAPI        │
│      │                                       ├─ routers/   (API; validan y autorizan)
│      │                                       ├─ services/  (reglas de negocio)
│      ▼                                       ├─ jobs.py    (hilo: fotos de inventario, respaldos)
│ ventana pywebview ◄── HTML/JS (Vue 3) ───────┤ hardware/   (cajón)  fiscal/ (DIAN, vacío)
│  (o navegador)                               └─ SQLite pos.db (WAL, synchronous=FULL)
└────────────────────────────────────────────────────────────┘
```

* **Routers delgados, servicios con las reglas.** Todo cambio de dinero o de stock pasa por un servicio y ocurre en **una transacción**; el endpoint confirma (`db.commit()`) explícitamente al final.
* **Escrituras con `BEGIN IMMEDIATE`** (sesión `get_db_w`) y lecturas con `BEGIN` normal: en modo WAL las lecturas nunca bloquean y no hay "database is locked" por promoción lectura→escritura.
* **Una sola caja hoy**, pero `turnos.caja_id` ya existe: pasar a varias cajas es agregar filas y un selector.

## Reglas de negocio que el código garantiza (con pruebas)

1. No se vende sin turno abierto. El **precio y los totales los calcula el servidor**, nunca el cliente.
2. Una venta es atómica: venta + líneas + pagos + movimientos de inventario + consecutivo (sin huecos) o nada.
3. Σ pagos = total; la devuelta solo sale del efectivo; banco siempre exacto; máximo un pago en efectivo por venta.
4. **Efectivo esperado** = base + ventas en efectivo (lo aplicado, no lo recibido) + ingresos − retiros − devoluciones en efectivo. **Banco esperado** = ventas por banco − devoluciones por banco. El cajero cierra a ciegas.
5. Las ventas no se borran: se **anulan** (solo dentro del turno en que se hicieron, con PIN del administrador; después, devolución). Devolución parcial o total, con reintegro en efectivo o banco; un producto dañado entra y sale del kardex como merma.
6. El costo unitario se congela en cada línea vendida: la rentabilidad histórica no cambia cuando cambia el costo.
7. **Costo promedio ponderado** al comprar (si el stock era ≤ 0 se toma el costo de la compra).
8. **Conteo:** stock teórico de un producto = `stock_actual − Σ movimientos posteriores a su captura`. Por eso se puede contar con la tienda abierta sin falsas diferencias. El ajuste es `contado − teórico` aplicado sobre el stock *actual*.
9. Los conteos aplicados, turnos cerrados y ventas son inmutables; se corrigen con ajustes auditados.

## Informes

Todos devuelven `{titulo, columnas, filas, totales, nota}` y la misma estructura alimenta la pantalla, Excel y PDF. Las ventas se calculan **netas de devoluciones**. Para que sean rápidos con un año de datos, las consultas **agrupan primero por producto y unen los nombres después**.

**Rotación:** `costo de ventas / inventario promedio a costo`; días de inventario = días del periodo / rotación; GMROI = margen bruto / inventario promedio. El inventario promedio sale de `inventario_diario` (una foto por día: stock y costo). Las fotos de días pasados se reconstruyen con el kardex (`stock actual − movimientos posteriores`), así el sistema nunca queda con huecos aunque el equipo haya estado apagado.

## Dónde se aparta del plan original

| Plan | Realidad | Por qué |
|---|---|---|
| Vue + Vite + Tailwind + Pinia + vue-router | **Vue 3 sin paso de compilación**, CSS propio, estado reactivo simple y router por `#`. ECharts y la fuente Inter van incluidos | El PC de la tienda no necesita Node; el instalador y el desarrollo son más simples; funciona sin internet |
| Alembic | Migraciones mínimas en `db.MIGRACIONES` (cada una corre una vez) | Una sola base local; menos piezas que fallen |
| APScheduler | Un hilo que revisa cada minuto (`jobs.py`) | Misma función, una dependencia menos |
| Modelos en paquete | `models.py` único | Son ~30 tablas; un archivo se lee entero |
| Ventas "suspendidas" dentro de `ventas` | Tabla propia `ventas_suspendidas` (JSON del carrito) | Mantiene el consecutivo de `ventas` sin huecos |
| Cantidades con decimales | `Cantidad` (TypeDecorator sobre INTEGER, 3 decimales); dinero siempre con aritmética entera (`valor_linea`) | Un producto por peso se guarda en kilos (1,250); no se cambia el esquema de las bases anteriores y el stock no acumula ruido de coma flotante |
| Costos como pesos enteros | Costos `REAL`; precios y montos de venta `INTEGER` | Un promedio ponderado necesita decimales (un costo de $83,33 no debe redondearse) |
| Respaldo a Google Drive por API | Copia a una **carpeta externa** configurable (USB, disco, o carpeta sincronizada de Drive/OneDrive/Dropbox) | Sin credenciales ni OAuth; igual de efectivo |
| Informes "Kardex" sueltos | Kardex en Inventario y también como informe exportable | — |
| Respaldo dentro de la transacción | Respaldo **sin transacción de escritura abierta** | Con una base grande, copiar tarda segundos; no debe frenar las ventas (hay prueba) |

## Seguridad

* Solo `127.0.0.1`; middleware rechaza `Host` no local (DNS-rebinding). Autenticación por token `Bearer` (no cookies → sin CSRF).
* Argon2 para contraseñas y PIN; tokens de sesión guardados con hash; vencen a los 7 días; bloqueo de 5 min tras 5 intentos fallidos (login, PIN de administrador, desbloqueo).
* Autorización de acciones sensibles por **PIN de administrador en cabecera** (`X-Autorizacion-Pin`); la interfaz reintenta sola la petición tras pedir el PIN. Queda en `auditoria` quién la hizo y quién la autorizó.
* El cajero no recibe costos, márgenes ni proveedor. Todas las consultas SQL usan parámetros; los parámetros de informes se filtran contra los declarados.
* El respaldo/restauración solo acepta archivos de la carpeta de respaldos, verifica `integrity_check` y guarda copia previa.

## Pruebas

* `tests/test_*.py` — reglas de negocio por API (jornada de caja, pagos, anulaciones, devoluciones, descuentos, conteos con ventas durante el conteo, informes con cifras calculadas a mano, respaldos, planificador).
* `tests/test_sistema.py` — robustez: atomicidad, 8 hilos vendiendo a la vez (consecutivos sin huecos), **corte de energía real** (`SIGKILL` a mitad de una venta, antes y después de confirmar), el respaldo no bloquea ventas.
* `tests/e2e/` — navegador real (Playwright): abrir caja → escanear → cobrar → cerrar a ciegas; conteo completo; todas las pantallas sin errores de consola; PIN del administrador; tema y bloqueo.
* `tests/perf_volumen.py` — 30.000 productos y ~1 millón de líneas.

## Qué no se pudo verificar aquí

Windows (instalador, ventana WebView2), cajón monedero real, lector de código de barras físico. El lector se simula tecleando; el cajón tiene implementaciones para serie/USB, ESC/POS por impresora de Windows y por archivo, pero solo se probó la ruta "sin cajón" y el manejo de errores.
