# Novedades

Cada versión publicada aparece en el botón **Configuración → Actualizaciones** del programa con estas notas.
(Una sección por versión: `## 1.2.0`, la más nueva arriba.)

## 1.2.0

**App del celular (Android) por la red local**
- Nueva app **POS Móvil** (archivo `.apk`) que se conecta por el Wi-Fi de la tienda, sin internet.
- Con la cámara del celular: **contar inventario**, **consultar precio y existencias**, **registrar facturas de compra**, **vender y cobrar** (efectivo o banco, también verduras por peso) y ver el **panel de ventas**.
- Seguridad: el acceso desde celulares viene **apagado**; se activa en Configuración → Celulares. Cada celular se vincula con un código de 6 números o un QR y se puede desvincular en cualquier momento. Solo entra el administrador, y desde el celular no se puede anular ventas, restaurar respaldos, cambiar usuarios ni actualizar el programa.
- El instalador de Windows abre el firewall solo para redes privadas.

**Correcciones en la caja**
- Al subir la cantidad con el botón **+** del mouse y luego escanear otro producto, el programa sumaba una unidad de más al producto anterior (2 cigarrillos y 1 chicle aparecían como 3 cigarrillos) y el producto nuevo no se registraba. Pasaba sobre todo con productos agregados a mano, sin código de barras. Ya no pasa.
- Escribir la cantidad junto al nombre, por ejemplo `2*kumis`, perdía la cantidad. Ahora se respeta (también `2*` y luego el nombre).

## 1.1.1

**Corrección en la caja**
- Si se subía la cantidad de un producto con el botón **+** del mouse y luego se escaneaba otro producto, el programa sumaba una unidad de más al producto anterior (por ejemplo, 2 cigarrillos y 1 chicle aparecían como 3 cigarrillos) y el producto nuevo no se registraba. Ya no pasa: el campo de escaneo recupera el foco después de usar los botones de cantidad.

## 1.1.0

**Verduras y frutas por peso**
- Se pueden crear productos que se venden **por kilo**: precio y costo por kilo, existencias en kilos con gramos.
- En la caja el cajero escribe el peso de la balanza, o «$5.000 de tomate». También por **código corto** (`101`), con `1,25*101`, o con los **botones rápidos** (tecla F1).
- Compras, mermas, conteos de inventario, devoluciones, recibos e informes funcionan con kilos.
- La plantilla de Excel trae las columnas `unidad` y `plu`.

**Instalador y actualizaciones**
- Instalador de Windows con ícono en el escritorio.
- Botón **Configuración → Actualizaciones**: busca la versión nueva, la descarga, verifica que no esté dañada, hace un respaldo y se instala sola.
- El programa avisa cuando hay una versión nueva.
