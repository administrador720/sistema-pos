# Plan — Sistema POS para Supermercado (local, una caja)

> **Estado (v1.0):** las fases 0 a 6 de este plan están implementadas y probadas. Lo construido, y en qué se aparta de este plan,
> está en [`arquitectura.md`](arquitectura.md). La fase 7 (futuro) sigue pendiente. El resto de este documento es el plan original.

> Versión 1 · Octubre 2026 · Plan original

---

## 1. Resumen

Sistema de punto de venta (POS) que corre en **un solo computador** y guarda toda la
información **localmente** (sin depender de internet). Incluye:

- **Caja**: venta con lector de código de barras, apertura de turno con **base**, pago en
  **efectivo** (con cálculo de devuelta) o **banco**, cajón monedero y cierre con arqueo.
- **Inventario**: productos, compras/entradas, mermas, ajustes y kardex.
- **Tomas de inventario físico** programadas por el administrador, con reporte de
  **inconsistencias** y aplicación de ajustes.
- **Dashboard e informes**: ventas, márgenes, **rotación de inventario**, análisis ABC,
  productos sin movimiento, sugerido de compras, diferencias de caja, etc.
- Interfaz moderna y "descansada" a la vista, pensada para usarse casi todo con teclado.

### Decisiones ya tomadas

| Tema | Decisión |
|---|---|
| Número de cajas | **Una sola caja** (un PC). El modelo de datos deja un campo `caja_id` para crecer después sin rehacer nada. |
| Facturación electrónica | **DIAN después**. Por ahora tiquete interno; el diseño queda preparado (consecutivos, datos del cliente, estado de envío). |
| Hardware | **Lector de código de barras + cajón monedero**. Sin impresora por ahora (ver nota en §9). |
| Tecnología | **Python (FastAPI) + SQLite + interfaz web (Vue 3)** dentro de una ventana de escritorio. |
| Productos por peso | Fuera del alcance inicial (solo unidades). |

---

## 2. Arquitectura

```
┌───────────────────────── PC del supermercado ─────────────────────────┐
│                                                                        │
│   Ventana de escritorio (pywebview)                                    │
│   ┌──────────────────────────────────────┐                             │
│   │  Frontend: Vue 3 + Tailwind + ECharts│  ← lector de barras (USB,   │
│   └───────────────┬──────────────────────┘    funciona como teclado)   │
│                   │ HTTP (solo localhost: 127.0.0.1)                   │
│   ┌───────────────▼──────────────────────┐                             │
│   │  Backend: FastAPI (Python 3.12)      │ → cajón monedero (USB/serial│
│   │  servicios: ventas, caja, inventario,│   o vía impresora ESC/POS)  │
│   │  conteos, reportes, respaldos        │                             │
│   └───────────────┬──────────────────────┘                             │
│   ┌───────────────▼──────────────────────┐   ┌───────────────────────┐ │
│   │  SQLite (archivo pos.db, modo WAL)   │──►│ Respaldos automáticos │ │
│   └──────────────────────────────────────┘   │ (carpeta + USB/nube)  │ │
│                                              └───────────────────────┘ │
└────────────────────────────────────────────────────────────────────────┘
```

**Por qué esta combinación**

- **SQLite**: un solo archivo, sin instalar servidor de base de datos, muy rápido para una
  caja (aguanta sin problema decenas de miles de productos y millones de líneas de venta).
  Se configura en modo `WAL` y `synchronous=FULL` para no perder ventas en un corte de luz.
- **FastAPI**: tú ya programas en Python; validaciones claras con Pydantic, documentación
  automática de la API (`/docs`) para probar.
- **Interfaz web (Vue 3 + Tailwind)**: es la forma más rápida de lograr un diseño moderno.
  Corre dentro de una ventana nativa con `pywebview`, así que el cajero no ve un navegador.
- **Bonus**: si en el futuro se quieren 2+ cajas, el mismo backend se expone en la red local
  y se migra SQLite → PostgreSQL con cambios mínimos (gracias a SQLAlchemy).
- **100 % offline**: fuentes, íconos y librerías van empaquetados (nada de CDN).

### Stack detallado

| Capa | Librerías |
|---|---|
| Backend | Python 3.12, FastAPI, Uvicorn, SQLAlchemy 2, Alembic (migraciones), Pydantic v2, argon2-cffi (contraseñas), APScheduler (tareas programadas) |
| Archivos | openpyxl (importar/exportar Excel), reportlab (PDF de informes y cierres) |
| Hardware | pyserial (cajón serial/USB), python-escpos (si luego se usa impresora térmica) |
| Frontend | Vue 3 + Vite, Pinia (estado), Vue Router, Tailwind CSS, Apache ECharts, íconos Lucide, fuente Inter (local) |
| Escritorio | pywebview (ventana), PyInstaller + Inno Setup (instalador para Windows) |
| Pruebas | pytest (reglas de negocio), Playwright (flujo completo de caja) |

### Estructura del proyecto (recomendado como repositorio propio)

```
pos-supermercado/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI + montaje del frontend compilado
│   │   ├── config.py            # rutas de datos, ajustes
│   │   ├── db.py                # motor SQLite (WAL, foreign_keys=ON)
│   │   ├── models/              # tablas SQLAlchemy
│   │   ├── schemas/             # Pydantic (entrada/salida de la API)
│   │   ├── routers/             # auth, productos, caja, ventas, compras,
│   │   │                        # inventario, conteos, reportes, config
│   │   ├── services/            # reglas de negocio (aquí vive la lógica)
│   │   ├── hardware/cajon.py    # CajonSerial / CajonEscPos / CajonNulo
│   │   ├── fiscal/              # interfaz ProveedorDIAN (vacía por ahora)
│   │   └── jobs/                # respaldos, foto diaria de inventario, recordatorios
│   ├── migrations/              # Alembic
│   └── tests/
├── frontend/
│   └── src/
│       ├── views/               # Caja, Apertura, Cierre, Productos, Compras,
│       │                        # Inventario, Conteos, Dashboard, Informes, Config
│       ├── components/
│       ├── stores/
│       └── api/
├── launcher.py                  # arranca Uvicorn + abre la ventana pywebview
└── installer/                   # spec de PyInstaller + script Inno Setup
```

Datos en: `C:\ProgramData\POSSupermercado\data\pos.db` y respaldos en
`C:\ProgramData\POSSupermercado\respaldos\` (se asume Windows; también funciona en Linux).

---

## 3. Módulos funcionales

### 3.1 Usuarios, roles y permisos

| Rol | Puede |
|---|---|
| **Administrador** | Todo: productos, precios, compras, conteos, informes, configuración, autorizar acciones sensibles. |
| **Cajero** | Abrir/cerrar su turno, vender, suspender/retomar ventas, registrar retiros con motivo. |

- Ingreso con usuario + contraseña; el cajero puede usar **PIN** corto para desbloquear.
- **Acciones sensibles** piden PIN del administrador en el momento (sin cerrar sesión):
  anular venta, devolución, descuento mayor al límite, quitar un producto ya cobrado,
  abrir cajón sin venta, ajuste manual de inventario.
- Bloqueo automático de pantalla tras X minutos sin uso.

### 3.2 Caja: apertura, movimientos y cierre

**Apertura de turno (obligatoria para vender)**

1. Al entrar el cajero, si no hay turno abierto, el sistema muestra **"Abrir caja"**.
2. Pide la **base** (efectivo inicial para dar devueltas). Dos formas:
   - Digitar el valor total, o
   - Contar por denominaciones (billetes $100.000, $50.000, $20.000, $10.000, $5.000,
     $2.000 y monedas $1.000, $500, $200, $100, $50) y el sistema suma.
3. Se abre el cajón para verificar el dinero. Queda registrado quién, cuándo y cuánto.
4. Solo puede haber **un turno abierto por caja**.

**Movimientos de caja durante el turno**

- **Retiro** (p. ej. "recogida" de billetes grandes por seguridad, pago a un proveedor en
  efectivo) y **Ingreso** (p. ej. reforzar la base). Siempre con motivo; los retiros
  requieren autorización del administrador.

**Cierre de turno (arqueo)**

1. **Cierre ciego**: el cajero cuenta el efectivo por denominaciones **sin ver** cuánto
   debería haber (evita "ajustar" el conteo).
2. El cajero digita el **total del cierre del datáfono** / transferencias recibidas.
3. El sistema calcula:

   ```
   Efectivo esperado = Base
                     + Ventas cobradas en efectivo   (lo aplicado, no lo recibido)
                     + Ingresos de caja
                     − Retiros de caja
                     − Devoluciones pagadas en efectivo

   Diferencia efectivo = Efectivo contado − Efectivo esperado   (+ sobrante / − faltante)
   Diferencia banco    = Reportado datáfono − Σ pagos con banco del turno
   ```
4. Se genera el **reporte de cierre (tipo "Z")**: ventas por medio de pago, número de
   transacciones, anulaciones, devoluciones, descuentos, retiros y diferencias. Se puede
   ver en pantalla y exportar a PDF.
5. El turno queda cerrado e inmutable.

### 3.3 Ventas (pantalla de caja)

**Flujo principal**

- El campo de escaneo está **siempre enfocado**. El lector USB funciona como teclado y
  envía el código + Enter → el producto se agrega al instante con un "bip".
- Escanear el mismo producto otra vez **suma cantidad**.
- Cantidad rápida: escribir `6*` y escanear agrega 6 unidades.
- Un producto puede tener **varios códigos de barras**, y un código puede representar
  varias unidades (p. ej. el código de la paca de 6 gaseosas descuenta 6 unidades).
- Producto sin código o no encontrado: búsqueda por nombre (F2), con sonido distinto y
  aviso claro si el código no existe (opción de crearlo rápido si es administrador).
- **Suspender venta** (el cliente olvidó algo) y atender al siguiente; luego **retomarla**.
- Descuentos por línea o al total, con límite configurable.

**Medios de pago**

| Medio | Comportamiento |
|---|---|
| **Efectivo** | Se digita lo que entrega el cliente (botones rápidos: exacto, $20.000, $50.000, $100.000). El sistema muestra la **devuelta en grande**. Abre el cajón. |
| **Banco** | Subtipos configurables: tarjeta débito, tarjeta crédito (datáfono), transferencia / QR (Nequi, Daviplata, Bancolombia, etc.). Se registra referencia o número de aprobación (opcional/obligatorio según configuración). El valor debe ser exacto (no hay devuelta). |
| **Mixto** (recomendado) | Parte en efectivo y parte con banco. La suma de pagos debe ser igual al total; la devuelta solo sale de la parte en efectivo. |

**Después del cobro**

- Se guarda la venta con **consecutivo** sin huecos (p. ej. `POS-000001`).
- Recibo en pantalla y opción de exportar a PDF (impresión cuando haya impresora).
- Cliente opcional (por defecto "Consumidor final") — necesario más adelante para DIAN.

**Anulaciones y devoluciones**

- Las ventas **nunca se borran**: se **anulan** (con motivo y autorización), lo que
  devuelve el inventario y queda en la auditoría.
- **Devolución** parcial o total referenciando la venta original; el producto regresa
  al inventario (o a merma si está dañado) y el reintegro se descuenta del turno actual.

**Impuestos (Colombia)**

- Precio de venta **con IVA incluido** (como se exhibe al público); el sistema desglosa
  base e impuesto por línea.
- Tarifas configurables por producto: IVA 19 %, IVA 5 %, exento, excluido; además
  impuestos al consumo que apliquen (bolsas plásticas, bebidas azucaradas,
  ultraprocesados). **Las tarifas vigentes se deben confirmar con el contador** y se
  cambian desde configuración sin tocar código.

### 3.4 Productos

- Campos: código interno, códigos de barras (uno o varios), nombre, categoría
  (con subcategorías), marca, proveedor principal, impuesto, **costo promedio**, precio de
  venta, stock actual, stock mínimo y máximo, ubicación (pasillo/góndola), activo.
- Margen calculado en vivo al editar precio o costo (alerta si el margen es negativo).
- Cambio masivo de precios (por % y por categoría/proveedor) con **historial de precios**.
- **Carga inicial desde Excel/CSV** (plantilla descargable) para no digitar todo a mano.

### 3.5 Inventario

- **Kardex**: cada movimiento de stock es un registro (venta, compra, devolución,
  anulación, merma, ajuste, ajuste por conteo) con fecha, usuario, cantidad, costo y
  saldo resultante. El stock del producto se actualiza en la **misma transacción**.
- **Compras / entrada de mercancía**: proveedor, número de factura, se escanean los
  productos y se digita cantidad y costo → actualiza stock y **costo promedio ponderado**:

  ```
  nuevo costo promedio = (stock actual × costo actual + cantidad comprada × costo compra)
                         / (stock actual + cantidad comprada)
  ```
- **Mermas / bajas**: vencido, dañado, robo, consumo interno — con motivo, para medirlas.
- **Stock negativo**: permitido con alerta (configurable). En supermercados es común que
  el sistema descuadre antes de registrar una compra; bloquear la venta frena la caja.
- **Alertas**: stock bajo el mínimo, agotados, stock negativo, productos sin movimiento.

### 3.6 Tomas de inventario físico (conteos) e inconsistencias

**Programación (el administrador decide cuándo)**

- Crear un conteo **manual** en cualquier momento, o **programarlo**:
  una sola vez (fecha), cada N días, semanal, quincenal o mensual.
- El sistema muestra un **recordatorio en el dashboard** cuando un conteo programado está
  por vencer o vencido. El administrador lo inicia cuando quiera.
- **Alcance** del conteo:
  - **Total**: todo el inventario.
  - **Parcial**: por categoría, pasillo/ubicación o proveedor.
  - **Cíclico**: el sistema elige N productos (priorizando los de mayor valor/rotación o
    con diferencias en conteos anteriores) para contar un poco cada semana sin cerrar.

**Captura**

- Pantalla de conteo con el lector: escanear producto → digitar cantidad contada.
- Si el mismo producto está en varios lugares, cada captura se **suma**.
- **Conteo ciego**: quien cuenta no ve el stock del sistema.
- Se puede contar **con la tienda abierta**: el stock teórico de cada producto se toma
  del kardex **en el momento exacto en que se contó**, así las ventas que ocurran durante
  el conteo no generan diferencias falsas.

**Revisión de inconsistencias**

Por cada producto: stock teórico, contado, diferencia en unidades, **diferencia
valorizada a costo** y porcentaje. Con filtros y vistas de:

- Faltantes y sobrantes, ordenados por valor (lo que más plata representa primero).
- Productos **no contados** dentro del alcance (en conteo total: decidir si se dejan igual o
  se asumen en cero).
- **Faltantes recurrentes**: productos que salen con faltante en varios conteos
  seguidos (posible robo, error de codificación o venta con código equivocado).
- **Exactitud del inventario** = productos sin diferencia / productos contados.
- Botón **"Reconteo"** para productos con diferencias grandes antes de aprobar.

**Aprobación**

1. Estados: `Borrador → En conteo → En revisión → Aplicado` (o `Cancelado`).
2. El administrador aprueba y el sistema genera los movimientos **AJUSTE_CONTEO** en el
   kardex. Una vez aplicado el conteo queda cerrado y no se puede modificar.
3. Informe del conteo exportable a PDF/Excel.

### 3.7 Dashboard

Tarjetas y gráficos (filtro: hoy / semana / mes / rango, comparado con el periodo anterior):

- Ventas netas, número de transacciones, **ticket promedio**, unidades por ticket.
- **Margen bruto** en pesos y porcentaje.
- Ventas por hora y día de la semana (mapa de calor → útil para turnos de personal).
- Ventas por medio de pago (efectivo vs. banco).
- Top 10 productos y categorías (por ventas y por margen).
- Valor del inventario a costo, productos agotados y bajo mínimo.
- Próximo conteo programado y último resultado de exactitud.
- Diferencias de caja de los últimos turnos.

### 3.8 Informes administrativos

Todos con filtros por fecha, exportación a **Excel** y **PDF**.

| Informe | Para qué sirve |
|---|---|
| Ventas por día / producto / categoría / cajero / medio de pago / hora | Saber qué y cuándo se vende. |
| Detalle de tiquetes, anulaciones, devoluciones y descuentos | Control y auditoría. |
| **Rentabilidad** por producto y categoría | Usa el costo congelado en cada venta, no el costo de hoy. |
| **Rotación de inventario** por producto y categoría | Ver fórmulas abajo. |
| **Días de inventario y cobertura** | Cuántos días alcanza el stock actual. |
| **Análisis ABC (Pareto)** | Qué 20 % de productos genera ~80 % de las ventas o del margen. |
| **Productos sin movimiento** (30/60/90 días) | Dinero inmovilizado en estantería. |
| **Sugerido de compras** por proveedor | Cantidad a pedir según venta promedio y días de cobertura deseados. |
| Kardex por producto | Historia completa de un producto. |
| Valorización del inventario | Stock × costo promedio, por categoría. |
| Mermas por motivo | Cuánto se pierde y por qué. |
| Compras por proveedor | Seguimiento a proveedores. |
| Cierres de caja e historial de diferencias por cajero | Detectar faltantes recurrentes. |
| Inconsistencias de conteos (histórico) | Evolución de la exactitud del inventario. |
| IVA e impuestos por tarifa | Para entregar al contador. |

**Fórmulas clave**

```
Costo de ventas (periodo)   = Σ (cantidad vendida × costo unitario al momento de la venta)
Inventario promedio a costo = promedio de las fotos diarias de (stock × costo promedio)
Rotación (veces)            = Costo de ventas / Inventario promedio a costo
Días de inventario          = Días del periodo / Rotación
Cobertura (días)            = Stock actual / Venta promedio diaria (últimos 30 días)
Margen bruto %              = (Ventas sin impuestos − Costo de ventas) / Ventas sin impuestos
GMROI                       = Margen bruto en $ / Inventario promedio a costo
Sugerido de compra          = max(0, Venta diaria promedio × Días de cobertura deseados
                                     + Stock mínimo − Stock actual)
Merma %                     = Valor de mermas / Ventas del periodo
```

Para la rotación se guarda una **foto diaria del inventario** (tarea automática a medianoche
o al cerrar el último turno del día) en la tabla `inventario_diario`. Así los informes son
rápidos y exactos sin recalcular todo el kardex.

### 3.9 Configuración

Datos del negocio (nombre, NIT, dirección, teléfono, logo), consecutivos, impuestos,
medios de pago bancarios, denominaciones, límites de descuento, comportamiento del stock
negativo, cajón monedero (puerto), respaldos, usuarios.

### 3.10 Auditoría y respaldos

- **Auditoría**: tabla con quién, qué, cuándo, valor anterior y valor nuevo para cambios de
  precio, anulaciones, devoluciones, ajustes, aperturas de cajón sin venta, cambios de
  configuración y autorizaciones.
- **Respaldos automáticos** (crítico porque todo vive en un solo PC):
  - Copia diaria (y al cerrar cada turno) usando la API de *backup* de SQLite (segura
    aunque la base esté en uso), comprimida y con fecha.
  - Destino principal en el disco + copia a **USB/disco externo** y opcionalmente a
    **Google Drive** cuando haya internet.
  - Retención: 30 diarios + 12 mensuales. Restauración desde la interfaz (solo admin).
  - Aviso en el dashboard si el último respaldo externo tiene más de N días.

---

## 4. Diseño de la interfaz ("descansada" y moderna)

**Principios**

- Fondo gris muy claro cálido (`#F5F6F8`), tarjetas blancas, **un solo color de acento**
  (verde azulado) para acciones principales; verde/ámbar/rojo suaves solo para estados.
- **Modo oscuro** opcional para turnos de noche.
- Tipografía Inter, números tabulares (las cifras no "bailan"); el **total en 56–64 px**.
- Espacios generosos, esquinas redondeadas (12 px), sombras suaves, sin bordes duros.
- Botones de mínimo 48 px de alto (sirve también con pantalla táctil).
- **Caja 100 % operable con teclado** — el cajero no necesita el mouse.
- Retroalimentación: sonido corto al escanear bien, sonido distinto y aviso cuando el
  código no existe, la devuelta se muestra grande en verde.

**Boceto de la pantalla de caja**

```
┌───────────────────────────────────────────────────────────────────────────────┐
│  Supermercado ·  Caja 1 · Turno #128 · Ana                      10:42 a. m.   │
├─────────────────────────────────────────────────────┬─────────────────────────┤
│  ▌Escanee o busque un producto…               (F2)  │                         │
│                                                     │   TOTAL                 │
│   #  Producto               Cant.  Precio    Total  │   $ 48.700              │
│   1  Leche entera 1 L         2    4.200     8.400  │   12 artículos          │
│   2  Arroz blanco 500 g       1    2.900     2.900  │                         │
│   3  Aceite vegetal 1 L       1   11.500    11.500  │  ┌───────────────────┐  │
│   …                                                 │  │ F9   Efectivo     │  │
│                                                     │  ├───────────────────┤  │
│                                                     │  │ F10  Banco        │  │
│                                                     │  ├───────────────────┤  │
│                                                     │  │ F11  Mixto        │  │
│                                                     │  └───────────────────┘  │
├─────────────────────────────────────────────────────┴─────────────────────────┤
│ F3 Cantidad · F4 Quitar · F5 Descuento · F6 Suspender · F7 Retomar · Esc Salir│
└───────────────────────────────────────────────────────────────────────────────┘
```

**Modal de pago en efectivo**

```
   Total a pagar          $ 48.700
   Recibido               $ [ 50.000 ]     [Exacto] [20.000] [50.000] [100.000]
   ───────────────────────────────────
   DEVUELTA               $ 1.300          ← grande, en verde
                          [ Enter  Confirmar ]
```

**Atajos de teclado (caja)**

| Tecla | Acción |
|---|---|
| Enter | Agregar producto escaneado / confirmar |
| F2 | Buscar producto por nombre |
| F3 | Cambiar cantidad de la línea seleccionada |
| F4 | Quitar línea (pide autorización si aplica) |
| F5 | Descuento |
| F6 / F7 | Suspender / retomar venta |
| F9 / F10 / F11 | Pagar en efectivo / banco / mixto |
| F12 | Movimientos de caja (retiro/ingreso) |
| Esc | Cancelar / cerrar modal |

**Menú lateral (administrador)**: Caja · Productos · Compras · Inventario · Conteos ·
Dashboard · Informes · Cierres de caja · Configuración.

---

## 5. Modelo de datos (SQLite)

Reglas generales: **dinero en pesos como `INTEGER`** (sin decimales, evita errores de
redondeo), cantidades como `INTEGER` (unidades), fechas en ISO 8601, llaves foráneas activas.

| Tabla | Columnas principales |
|---|---|
| `usuarios` | id, nombre, usuario, hash_password, hash_pin, rol, activo, creado_en |
| `configuracion` | clave, valor |
| `categorias` | id, nombre, padre_id |
| `proveedores` | id, nit, nombre, telefono, email, contacto, activo |
| `impuestos` | id, nombre, tipo (IVA, INC, BOLSA, SALUDABLE…), tarifa_pct, valor_fijo, activo |
| `productos` | id, codigo_interno, nombre, categoria_id, marca, proveedor_id, impuesto_id, costo_promedio, precio_venta, stock_actual, stock_minimo, stock_maximo, ubicacion, activo, creado_en, actualizado_en |
| `codigos_barra` | codigo (PK), producto_id, unidades_por_codigo (1 por defecto; 6 para una paca) |
| `historial_precios` | id, producto_id, precio_anterior, precio_nuevo, usuario_id, fecha |
| `cajas` | id, nombre (hoy una sola fila) |
| `turnos` | id, caja_id, usuario_id, abierto_en, base_efectivo, cerrado_en, efectivo_esperado, efectivo_contado, diferencia_efectivo, banco_reportado, diferencia_banco, estado, observaciones |
| `turno_denominaciones` | turno_id, momento (apertura/cierre), denominacion, cantidad |
| `movimientos_caja` | id, turno_id, tipo (ingreso/retiro), monto, motivo, usuario_id, autorizado_por, fecha |
| `medios_pago` | id, nombre, tipo (efectivo/banco), requiere_referencia, activo |
| `clientes` | id, tipo_documento, numero_documento, nombre, email, telefono |
| `ventas` | id, prefijo, consecutivo, turno_id, usuario_id, cliente_id, fecha, subtotal, descuento_total, impuesto_total, total, estado (completada/anulada/suspendida), anulada_por, motivo_anulacion, estado_dian, cude |
| `venta_items` | id, venta_id, producto_id, descripcion, cantidad, precio_unitario, descuento, impuesto_id, tarifa_pct, valor_impuesto, total, **costo_unitario** (congelado al vender) |
| `venta_pagos` | id, venta_id, medio_pago_id, monto, recibido, devuelta, referencia |
| `devoluciones` / `devolucion_items` | venta original, turno, usuario, autorizado_por, motivo, ítems, total, medio de reintegro |
| `compras` / `compra_items` | proveedor, número de factura, fecha, ítems con cantidad y costo, totales, usuario |
| `movimientos_inventario` | id, producto_id, fecha, tipo, cantidad (+/−), costo_unitario, stock_resultante, referencia_tipo, referencia_id, usuario_id, nota |
| `programacion_conteos` | id, nombre, alcance (json), frecuencia, intervalo, proxima_fecha, activo |
| `conteos` | id, nombre, tipo (total/parcial/cíclico), alcance (json), estado, creado_por, iniciado_en, cerrado_en, aprobado_por |
| `conteo_capturas` | id, conteo_id, producto_id, cantidad, ubicacion, usuario_id, capturado_en |
| `conteo_items` | conteo_id, producto_id, stock_teorico, cantidad_contada, diferencia, costo_unitario, reconteo |
| `inventario_diario` | fecha, producto_id, stock, costo_promedio |
| `auditoria` | id, fecha, usuario_id, accion, entidad, entidad_id, datos_antes (json), datos_despues (json) |

Índices clave: `codigos_barra.codigo`, `ventas(fecha)`, `ventas(turno_id)`,
`venta_items(producto_id)`, `movimientos_inventario(producto_id, fecha)`,
`inventario_diario(fecha)`.

### Reglas de negocio que no se negocian

1. No se puede vender sin turno abierto.
2. Una venta es **atómica**: venta + ítems + pagos + movimientos de inventario + stock se
   guardan todos juntos o ninguno (una transacción).
3. Las ventas, turnos cerrados y conteos aplicados **no se editan ni se borran**; se
   corrigen con anulaciones/ajustes que quedan auditados.
4. Consecutivo de venta sin huecos.
5. Σ pagos = total de la venta; la devuelta solo sale del efectivo; banco siempre exacto.
6. El costo unitario se guarda en cada línea vendida (la rentabilidad histórica no cambia
   cuando cambia el costo).

---

## 6. Preparación para DIAN (sin implementarla aún)

Desde 2024 la DIAN viene exigiendo el **documento equivalente electrónico POS**
(Resolución 000165 de 2023). **Confirmar con el contador si el supermercado ya está
obligado** — si lo está, la Fase 7 debe adelantarse.

Lo que se deja listo desde el inicio:

- Prefijo y consecutivo configurables (para la resolución de numeración).
- Datos del cliente (tipo y número de documento, nombre, correo); "consumidor final" por
  defecto.
- Campos `estado_dian` (pendiente / enviado / aceptado / rechazado) y `cude` en `ventas`.
- Desglose de impuestos por línea (lo exige el documento electrónico).
- Interfaz `ProveedorDIAN` en `backend/app/fiscal/` con una implementación vacía. Luego se
  conecta la API de un **proveedor tecnológico** autorizado, con cola de envío para
  cuando no haya internet (la venta nunca se bloquea por falta de conexión).

---

## 7. Plan de trabajo por fases

Estimaciones **orientativas** para un desarrollador a tiempo completo.

| Fase | Contenido | Entregable / criterio de terminado | Duración |
|---|---|---|---|
| **0. Fundamentos** | Repositorio, estructura, SQLite + Alembic, login, roles, layout base, sistema de diseño (colores, tipografía, componentes), ventana pywebview | Se instala, abre, se inicia sesión y se navega el menú vacío | 1 semana |
| **1. Productos** | CRUD de productos, categorías, proveedores, impuestos, códigos de barras múltiples, importación desde Excel | Se cargan los productos reales desde Excel y se encuentran escaneando | 1 semana |
| **2. Caja (MVP)** | Apertura con base, pantalla de venta con escáner, efectivo / banco / mixto, devuelta, cajón monedero, suspender/retomar, cierre ciego con arqueo y reporte Z, respaldo diario básico | **Se puede operar una jornada completa de ventas** | 2 semanas |
| **3. Inventario** | Compras/entradas, costo promedio, kardex, mermas, ajustes, alertas de stock | Stock y costo correctos después de compras y ventas | 1,5 semanas |
| **4. Conteos** | Programación, recordatorios, captura con escáner, conteo ciego, inconsistencias, reconteo, aprobación y ajustes | Un conteo parcial real termina con ajustes aplicados y reporte | 1,5 semanas |
| **5. Dashboard e informes** | Foto diaria de inventario, dashboard, todos los informes de §3.8, exportación Excel/PDF | El administrador ve rotación, ABC, márgenes y sugerido de compras | 2 semanas |
| **6. Control y salida en vivo** | Anulaciones, devoluciones, auditoría, respaldos externos y restauración, instalador, pruebas | Instalador probado en el PC de la tienda | 1,5 semanas |
| **7. Futuro** | DIAN, impresora térmica, productos por peso, varias cajas, clientes/fidelización, crédito ("fiado"), lotes y vencimientos, promociones | — | — |

**MVP utilizable**: Fases 0 + 1 + 2 (≈ 4 semanas).

### Puesta en marcha

1. Cargar productos desde Excel (con códigos de barras, costos y precios).
2. Hacer un **conteo total inicial** con el propio sistema → ese es el stock de arranque.
3. Capacitar cajeros (1–2 horas; la caja está pensada para aprenderse rápido).
4. **Piloto** de 1–2 semanas, idealmente en paralelo con el método actual.
5. Salida en vivo; primer conteo cíclico a la semana.

---

## 8. Pruebas

- **pytest** para todas las reglas de negocio: devuelta, pagos mixtos, arqueo, costo
  promedio, stock teórico durante conteos, rotación, sugerido de compras.
- **Playwright** para el flujo completo: abrir caja → vender → pagar → cerrar caja.
- **Prueba de volumen**: 30.000 productos y un año de ventas simuladas (~300 ventas/día,
  ~1 millón de líneas) → escaneo < 100 ms e informes < 2 s.
- Prueba de **corte de luz**: matar el proceso a mitad de una venta y verificar que no
  queden ventas a medias.

---

## 9. Hardware recomendado

| Equipo | Recomendación |
|---|---|
| PC | Core i3 / Ryzen 3 o superior, 8 GB RAM, **disco SSD**, Windows 10/11 |
| Lector de código de barras | USB tipo teclado (HID). 1D sirve para EAN-13/UPC; 2D si se quieren leer QR. No requiere drivers. |
| Cajón monedero | **Importante**: la mayoría de cajones se abren **a través de la impresora térmica** (puerto RJ11). Sin impresora se necesita un cajón con **interfaz USB** o un adaptador "kicker" USB/serial. El sistema soporta las dos vías (`CajonSerial` y `CajonEscPos`). |
| UPS (regulador con batería) | **Muy recomendado**: con la base de datos en el mismo PC, un apagón es el mayor riesgo. |
| USB / disco externo | Para los respaldos fuera del PC. |
| Impresora térmica 80 mm (opcional) | Considerarla: resuelve la apertura del cajón y servirá para entregar el documento DIAN. |

---

## 10. Riesgos y cómo se mitigan

| Riesgo | Mitigación |
|---|---|
| Daño o robo del PC = pérdida de datos | Respaldos automáticos diarios fuera del PC (USB/nube) + aviso si no se hacen |
| Apagón a mitad de una venta | Transacciones atómicas, SQLite en WAL, UPS |
| Obligación DIAN ya vigente | Validar con el contador antes de salir en vivo; diseño ya preparado |
| Inventario inicial inexacto | Conteo total inicial antes de arrancar |
| Faltantes de caja | Cierre ciego, retiros autorizados, auditoría, informe de diferencias por cajero |
| Cajeros lentos con el sistema nuevo | Caja por teclado, capacitación corta, piloto en paralelo |

---

## 11. Preguntas pendientes (no bloquean el inicio)

1. ¿Cuántos productos maneja aproximadamente el supermercado? ¿Ya existe un listado en Excel?
2. ¿Qué medios bancarios usan hoy? (datáfono de qué banco, Nequi, Daviplata, QR…)
3. ¿Venden a crédito / "fiado" a clientes conocidos?
4. ¿Manejan promociones (2×1, combos, precio por cantidad)?
5. ¿Hay productos con fecha de vencimiento que quieran controlar por lote?
6. ¿Qué sistema operativo tiene el PC de la caja?
7. ¿El cajón monedero ya existe? ¿Qué conexión tiene (RJ11, USB, serial)?
8. Nombre comercial y logo del supermercado para la interfaz y los informes.
