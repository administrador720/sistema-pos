"""Carga de datos de DEMOSTRACIÓN: productos de supermercado y semanas de ventas simuladas.

    python -m app.seed_demo [--dias 30] [--ventas-dia 90] [--forzar]

Usa los mismos servicios que la aplicación (ventas, compras, mermas, cierres, conteos), con un reloj
simulado, así el dashboard, la rotación y los informes tienen historia real que mostrar.
NO usar en el computador de la tienda: borra la base de datos si se pasa --forzar.
"""
from __future__ import annotations

import argparse
import random
from datetime import datetime, time, timedelta

from sqlalchemy import func, select

from . import config, core, db as db_mod
from . import models as m
from .services import caja as caja_svc
from .services import compras as compras_svc
from .services import conteos as conteos_svc
from .services import inventario as inv
from .services import productos as prod_svc
from .services import respaldos
from .services import setup as setup_svc
from .services import ventas as ventas_svc

PROVEEDORES = ["Distribuidora Lácteos del Valle", "Alimentos La Sabana", "Bebidas Andinas", "Aseo y Hogar S.A.S.",
               "Carnes y Frescos del Campo", "Mayorista Central"]

# (nombre, categoría, proveedor, impuesto, costo, precio, stock, mínimo)
CATALOGO = [
    ("Leche entera 1 L", "Lácteos", 0, "Excluido", 3100, 4200, 120, 40), ("Leche deslactosada 1 L", "Lácteos", 0, "Excluido", 3500, 4800, 60, 24),
    ("Yogurt fresa 1 L", "Lácteos", 0, "IVA 19%", 4800, 6500, 40, 12), ("Queso campesino 500 g", "Lácteos", 0, "Excluido", 9500, 13500, 25, 8),
    ("Mantequilla 250 g", "Lácteos", 0, "IVA 19%", 6200, 8800, 20, 6), ("Kumis 1 L", "Lácteos", 0, "IVA 19%", 4300, 5900, 18, 6),
    ("Huevos AA x30", "Lácteos", 5, "Excluido", 15500, 21000, 30, 10), ("Huevos A x12", "Lácteos", 5, "Excluido", 6800, 9200, 36, 12),
    ("Crema de leche 200 ml", "Lácteos", 0, "IVA 19%", 3600, 5100, 16, 5),
    ("Arroz blanco 500 g", "Despensa", 1, "Exento (0%)", 2100, 2900, 200, 60), ("Arroz blanco 1 kg", "Despensa", 1, "Exento (0%)", 3900, 5400, 90, 30),
    ("Azúcar 1 kg", "Despensa", 1, "IVA 5%", 3800, 5200, 80, 24), ("Aceite vegetal 1 L", "Despensa", 1, "IVA 19%", 8200, 11500, 70, 20),
    ("Sal refinada 1 kg", "Despensa", 1, "Excluido", 900, 1500, 60, 18), ("Pasta espagueti 250 g", "Despensa", 1, "IVA 19%", 1700, 2600, 110, 30),
    ("Lentejas 500 g", "Despensa", 1, "Excluido", 2900, 4100, 45, 15), ("Frijol cargamanto 500 g", "Despensa", 1, "Excluido", 5200, 7300, 40, 12),
    ("Panela 500 g", "Despensa", 1, "Excluido", 2400, 3400, 50, 15), ("Harina de trigo 1 kg", "Despensa", 1, "IVA 5%", 3100, 4400, 36, 12),
    ("Harina de maíz precocida 1 kg", "Despensa", 1, "Exento (0%)", 3500, 4900, 90, 30), ("Atún en lata 170 g", "Despensa", 1, "IVA 19%", 4200, 6200, 60, 18),
    ("Sardinas en salsa 155 g", "Despensa", 1, "IVA 19%", 2600, 3900, 36, 12), ("Salsa de tomate 400 g", "Despensa", 1, "IVA 19%", 3300, 4800, 40, 12),
    ("Mayonesa 400 g", "Despensa", 1, "IVA 19%", 4900, 7000, 30, 10), ("Caldo de gallina x8", "Despensa", 1, "IVA 19%", 3200, 4700, 40, 12),
    ("Avena en hojuelas 400 g", "Despensa", 1, "IVA 19%", 2900, 4200, 35, 10), ("Café molido 500 g", "Despensa", 1, "IVA 5%", 14500, 19800, 40, 12),
    ("Chocolate de mesa 500 g", "Despensa", 1, "IVA 5%", 8400, 11800, 30, 10), ("Galletas saltinas x3", "Despensa", 1, "IVA 19%", 2300, 3500, 55, 18),
    ("Cereal de maíz 300 g", "Despensa", 1, "IVA 19%", 6300, 8900, 20, 6), ("Mermelada de fresa 300 g", "Despensa", 1, "IVA 19%", 4100, 5900, 18, 6),
    ("Gaseosa cola 1,5 L", "Bebidas", 2, "IVA 19%", 3200, 4800, 150, 48), ("Gaseosa cola 400 ml", "Bebidas", 2, "IVA 19%", 1300, 2000, 120, 36),
    ("Agua sin gas 600 ml", "Bebidas", 2, "IVA 19%", 1000, 1800, 160, 48), ("Jugo de naranja 1 L", "Bebidas", 2, "IVA 19%", 3000, 4500, 45, 15),
    ("Cerveza lata 330 ml", "Bebidas", 2, "IVA 19%", 2400, 3500, 140, 48), ("Té frío limón 500 ml", "Bebidas", 2, "IVA 19%", 1900, 2900, 60, 18),
    ("Bebida energizante 250 ml", "Bebidas", 2, "IVA 19%", 3600, 5400, 40, 12), ("Malta 330 ml", "Bebidas", 2, "IVA 19%", 1800, 2800, 50, 15),
    ("Detergente en polvo 1 kg", "Aseo del hogar", 3, "IVA 19%", 8800, 12900, 40, 12), ("Jabón de loza 500 g", "Aseo del hogar", 3, "IVA 19%", 3900, 5800, 40, 12),
    ("Suavizante de ropa 1 L", "Aseo del hogar", 3, "IVA 19%", 6100, 8900, 25, 8), ("Cloro 1 L", "Aseo del hogar", 3, "IVA 19%", 2300, 3600, 40, 12),
    ("Papel higiénico x12", "Aseo del hogar", 3, "IVA 19%", 14500, 21500, 45, 15), ("Servilletas x200", "Aseo del hogar", 3, "IVA 19%", 2100, 3300, 40, 12),
    ("Toallas de cocina x2", "Aseo del hogar", 3, "IVA 19%", 4400, 6600, 25, 8), ("Bolsas de basura x10", "Aseo del hogar", 3, "IVA 19%", 3200, 4900, 30, 10),
    ("Limpiapisos 1 L", "Aseo del hogar", 3, "IVA 19%", 4200, 6200, 28, 8),
    ("Jabón de baño x3", "Cuidado personal", 3, "IVA 19%", 5400, 7900, 36, 12), ("Shampoo 400 ml", "Cuidado personal", 3, "IVA 19%", 9800, 14200, 20, 6),
    ("Crema dental 100 ml", "Cuidado personal", 3, "IVA 19%", 3900, 5800, 45, 15), ("Cepillo de dientes", "Cuidado personal", 3, "IVA 19%", 2800, 4300, 30, 10),
    ("Desodorante en barra", "Cuidado personal", 3, "IVA 19%", 6900, 9900, 20, 6), ("Toallas higiénicas x10", "Cuidado personal", 3, "IVA 19%", 3800, 5700, 36, 12),
    ("Pañales etapa 3 x30", "Cuidado personal", 3, "IVA 19%", 28500, 39900, 14, 5), ("Afeitadoras x2", "Cuidado personal", 3, "IVA 19%", 2900, 4400, 24, 8),
    ("Pechuga de pollo 1 kg", "Carnes", 4, "Excluido", 13500, 18500, 30, 10), ("Carne molida 500 g", "Carnes", 4, "Excluido", 9800, 13900, 25, 8),
    ("Chorizo x6", "Carnes", 4, "IVA 19%", 7600, 10900, 20, 6), ("Salchichas x8", "Carnes", 4, "IVA 19%", 5400, 7800, 28, 8),
    ("Jamón de cerdo 250 g", "Carnes", 4, "IVA 19%", 6900, 9800, 20, 6), ("Costilla de cerdo 500 g", "Carnes", 4, "Excluido", 8800, 12500, 16, 5),
    ("Plátano maduro und", "Frutas y verduras", 4, "Excluido", 1100, 1800, 80, 24),
    ("Banano x6", "Frutas y verduras", 4, "Excluido", 2200, 3300, 36, 12), ("Limón tahití malla", "Frutas y verduras", 4, "Excluido", 2100, 3200, 24, 8),
    ("Aguacate hass und", "Frutas y verduras", 4, "Excluido", 2600, 3900, 30, 10),
    ("Papas fritas 120 g", "Snacks y dulces", 5, "IVA 19%", 3300, 4900, 70, 20), ("Chocolatina 30 g", "Snacks y dulces", 5, "IVA 19%", 1100, 1800, 90, 30),
    ("Maní salado 100 g", "Snacks y dulces", 5, "IVA 19%", 1800, 2800, 45, 15), ("Chicles x12", "Snacks y dulces", 5, "IVA 19%", 1500, 2400, 50, 15),
    ("Dulces surtidos bolsa", "Snacks y dulces", 5, "IVA 19%", 2700, 4100, 30, 10), ("Galletas de chocolate x6", "Snacks y dulces", 5, "IVA 19%", 2900, 4400, 45, 15),
    ("Pan tajado 500 g", "Panadería", 5, "IVA 19%", 4800, 6900, 40, 15), ("Arepas de maíz x5", "Panadería", 5, "IVA 19%", 3200, 4700, 36, 12),
    ("Pandebono und", "Panadería", 5, "IVA 19%", 800, 1500, 60, 20), ("Pan de bono x4", "Panadería", 5, "IVA 19%", 3100, 4500, 24, 8),
]
# Verduras y frutas que se venden por peso (precio y costo por KILO): (nombre, costo, precio, stock kg, mínimo kg, botón rápido)
CATALOGO_PESO = [
    ("Tomate chonto", 2400, 3500, 60, 15, True), ("Cebolla cabezona blanca", 2000, 3000, 50, 12, True),
    ("Cebolla larga", 2600, 3800, 20, 6, True), ("Papa pastusa", 1700, 2600, 120, 30, True),
    ("Papa criolla", 3200, 4600, 30, 8, True), ("Zanahoria", 1500, 2400, 45, 12, True),
    ("Pimentón rojo", 3800, 5600, 15, 4, True), ("Pimentón verde", 3000, 4400, 15, 4, False),
    ("Lechuga batavia", 2800, 4200, 14, 4, True), ("Repollo", 1400, 2200, 22, 6, False),
    ("Cilantro", 5200, 7800, 6, 2, True), ("Ajo", 9500, 13500, 8, 2, False),
    ("Pepino cohombro", 2100, 3200, 18, 5, False), ("Habichuela", 3600, 5400, 12, 4, False),
    ("Remolacha", 1800, 2800, 14, 4, False), ("Ahuyama", 1300, 2100, 25, 6, False),
    ("Yuca", 1600, 2500, 35, 10, True), ("Plátano verde", 1900, 2900, 50, 14, True),
    ("Mango tommy", 3100, 4800, 25, 8, False), ("Papaya", 2600, 3900, 22, 6, False),
    ("Tomate de árbol", 3500, 5200, 12, 4, False), ("Mora", 7200, 10500, 8, 3, False),
    ("Naranja", 1700, 2700, 60, 16, True), ("Limón mandarino", 2300, 3500, 20, 6, False),
    ("Fresa", 6800, 9800, 10, 3, False), ("Maracuyá", 4200, 6200, 14, 4, False),
]
FACTOR_DIA = {0: 0.85, 1: 0.8, 2: 0.85, 3: 0.95, 4: 1.2, 5: 1.45, 6: 1.1}  # lunes=0
HORAS_MANANA = ([7, 8, 9, 10, 11, 12, 13], [1, 1.5, 2, 3, 4, 4.5, 3])
HORAS_TARDE = ([14, 15, 16, 17, 18, 19, 20], [2.5, 2, 2.5, 3.5, 4.5, 4, 2])


def ean13(n: int) -> str:
    base = f"770{n:09d}"
    suma = sum(int(c) * (3 if i % 2 else 1) for i, c in enumerate(base))
    return base + str((10 - suma % 10) % 10)


def _redondeo_efectivo(total: int) -> int:
    for billete in (1000, 2000, 5000, 10000, 20000, 50000, 100000):
        if billete >= total:
            return billete
    return ((total // 100000) + 1) * 100000


def generar(dias: int = 30, ventas_dia: int = 90, semilla: int = 7):
    rnd = random.Random(semilla)
    inicio = datetime.combine(datetime.now().date() - timedelta(days=dias), time(6, 0))
    reloj = [inicio]
    core.reloj = lambda: reloj[0]
    s = db_mod.nueva_sesion(escritura=True)
    try:
        # ── negocio, usuarios, catálogos
        admin = setup_svc.primera_configuracion(
            s, negocio={"nombre": "Supermercado La Esquina (DEMO)", "nit": "900.123.456-7", "direccion": "Cra 10 # 20-30", "telefono": "601 555 0101"},
            admin={"nombre": "Administrador Demo", "usuario": "admin", "password": "demo1234", "pin": "1234"})
        cajeros = []
        for nombre, usuario in (("Ana Gómez", "ana"), ("Luis Pérez", "luis")):
            u = m.Usuario(nombre=nombre, usuario=usuario, hash_password=core.hashear(f"{usuario}1234"), hash_pin=core.hashear("4321"),
                          rol="cajero", activo=True, creado_en=core.ahora())
            s.add(u)
            cajeros.append(u)
        provs = []
        for nombre in PROVEEDORES:
            p = m.Proveedor(nombre=nombre, nit=f"8{rnd.randint(10000000, 99999999)}-{rnd.randint(0, 9)}", telefono="601 555 02" + str(rnd.randint(10, 99)))
            s.add(p)
            provs.append(p)
        s.flush()
        cats = {}
        for _n, cat, *_r in CATALOGO:
            if cat not in cats:
                cats[cat] = m.Categoria(nombre=cat)
                s.add(cats[cat])
        s.flush()
        impuestos = {i.nombre: i for i in s.scalars(select(m.Impuesto))}
        medios = {x.nombre: x for x in s.scalars(select(m.MedioPago))}
        objetivos: dict[int, tuple[int, int]] = {}
        costo_base: dict[int, float] = {}
        productos = []
        for n, (nombre, cat, pv, imp, costo, precio, stock, minimo) in enumerate(CATALOGO, start=1):
            p = prod_svc.crear(s, admin, {
                "nombre": nombre, "categoria_id": cats[cat].id, "proveedor_id": provs[pv].id, "impuesto_id": impuestos[imp].id,
                "costo_promedio": costo, "precio_venta": precio, "stock_inicial": int(stock * 0.9), "stock_minimo": minimo,
                "stock_maximo": stock * 2, "ubicacion": f"Pasillo {1 + n % 8}", "codigos": [{"codigo": ean13(n), "unidades": 1}]})
            objetivos[p.id] = (stock, minimo)
            costo_base[p.id] = costo
            productos.append(p)
        for j, (nombre, costo, precio, stock, minimo, rapido) in enumerate(CATALOGO_PESO, start=1):
            p = prod_svc.crear(s, admin, {
                "nombre": nombre, "categoria_id": cats["Frutas y verduras"].id, "proveedor_id": provs[4].id,
                "impuesto_id": impuestos["Excluido"].id, "unidad": "kg", "rapido": rapido, "codigo_interno": str(100 + j),
                "costo_promedio": costo, "precio_venta": precio, "stock_inicial": round(stock * 0.9, 1), "stock_minimo": minimo,
                "stock_maximo": stock * 2, "ubicacion": "Frescos", "codigos": []})
            objetivos[p.id] = (stock, minimo)
            costo_base[p.id] = costo
            productos.append(p)
        s.commit()
        pesos = [1 / ((i + 1) ** 0.85) for i in range(len(productos))]
        rnd.shuffle(pesos)

        # ── días
        for d in range(dias):
            dia = inicio.date() + timedelta(days=d)
            fijar = lambda h, mi=0, se=0: reloj.__setitem__(0, datetime.combine(dia, time(h, mi, se)))  # noqa: E731
            # compras de reposición y mermas en la mañana
            fijar(6, 30)
            por_prov: dict[int, list] = {}
            for p in productos:
                objetivo, minimo = objetivos[p.id]
                if p.stock_actual <= minimo * 1.3:
                    deriva = 1 + 0.0015 * d + rnd.uniform(-0.02, 0.03)  # inflación lenta sobre el costo de catálogo
                    por_prov.setdefault(p.proveedor_id, []).append(
                        {"producto_id": p.id, "cantidad": core.cant(max(1, objetivo - p.stock_actual)),
                         "costo_unitario": round(costo_base[p.id] * deriva)})
            for prov_id, items in por_prov.items():
                compras_svc.crear_compra(s, admin, {"proveedor_id": prov_id, "numero_factura": f"FV-{dia:%m%d}-{prov_id}", "items": items})
            fijar(6, 45)
            if rnd.random() < 0.35:
                for p in rnd.sample(productos, rnd.randint(1, 2)):
                    if p.stock_actual > 3:
                        inv.registrar_merma(s, admin, p.id, rnd.randint(1, 3), rnd.choice(["VENCIDO", "DANADO", "DANADO", "CONSUMO_INTERNO", "ROBO"]))
            s.commit()

            total_dia = int(ventas_dia * FACTOR_DIA[dia.weekday()] * rnd.uniform(0.9, 1.1))
            for turno_idx, (cajero, horas, base, frac) in enumerate(((cajeros[0], HORAS_MANANA, 120000, 0.45), (cajeros[1], HORAS_TARDE, 100000, 0.55))):
                fijar(horas[0][0], 0, 5)
                turno = caja_svc.abrir_turno(s, cajero, base=base)
                n_ventas = int(total_dia * frac)
                momentos = sorted(datetime.combine(dia, time(rnd.choices(horas[0], horas[1])[0], rnd.randint(0, 59), rnd.randint(0, 59)))
                                  for _ in range(n_ventas))
                retiro_hecho = False
                for k, momento in enumerate(momentos):
                    reloj[0] = max(momento, reloj[0] + timedelta(seconds=1))
                    n_items = min(14, 1 + int(rnd.expovariate(1 / 4.2)))
                    elegidos = {}
                    for p in rnd.choices(productos, pesos, k=n_items):
                        if p.stock_actual > 0 and p.id not in elegidos:
                            if p.unidad == "kg":  # por peso: unos kilos, o «$3.000 de tomate»
                                if rnd.random() < 0.15:
                                    elegidos[p.id] = {"producto_id": p.id, "valor": rnd.choice([1000, 2000, 3000, 5000]), "descuento": 0}
                                else:
                                    elegidos[p.id] = {"producto_id": p.id, "descuento": 0,
                                                      "cantidad": rnd.choice([0.25, 0.35, 0.5, 0.75, 1, 1.25, 1.5, 2, 3])}
                            else:
                                elegidos[p.id] = {"producto_id": p.id, "cantidad": rnd.choices([1, 2, 3, 4], [78, 15, 5, 2])[0], "descuento": 0}
                    items = list(elegidos.values())
                    if not items:
                        continue
                    for it in items:
                        pr = s.get(m.Producto, it["producto_id"])
                        if pr.unidad == "kg":
                            if "valor" in it and it["valor"] / pr.precio_venta > pr.stock_actual:
                                del it["valor"]
                                it["cantidad"] = pr.stock_actual
                            elif "cantidad" in it:
                                it["cantidad"] = min(it["cantidad"], pr.stock_actual)
                        else:
                            it["cantidad"] = min(it["cantidad"], max(1, pr.stock_actual))
                    bruto = sum(it["valor"] if "valor" in it else
                                core.valor_linea(s.get(m.Producto, it["producto_id"]).precio_venta, it["cantidad"]) for it in items)
                    if rnd.random() < 0.03:  # descuento de hasta el 10 % en una línea
                        it = items[0]
                        base_linea = it["valor"] if "valor" in it else core.valor_linea(
                            s.get(m.Producto, it["producto_id"]).precio_venta, it["cantidad"])
                        it["descuento"] = int(base_linea * rnd.choice([0.05, 0.1]))
                        bruto -= it["descuento"]
                    azar = rnd.random()
                    if azar < 0.58:
                        recibido = bruto if rnd.random() < 0.3 else _redondeo_efectivo(bruto)
                        pagos = [{"medio_pago_id": medios["Efectivo"].id, "monto": bruto, "recibido": recibido}]
                    elif azar < 0.84:
                        pagos = [{"medio_pago_id": medios["Tarjeta débito"].id, "monto": bruto}]
                    elif azar < 0.92:
                        pagos = [{"medio_pago_id": medios["Tarjeta crédito"].id, "monto": bruto}]
                    elif azar < 0.96 or bruto < 3000:
                        pagos = [{"medio_pago_id": medios["Transferencia / QR"].id, "monto": bruto}]
                    else:  # mixto
                        banco = int(bruto * rnd.uniform(0.4, 0.7) // 100 * 100)
                        pagos = [{"medio_pago_id": medios["Tarjeta débito"].id, "monto": banco},
                                 {"medio_pago_id": medios["Efectivo"].id, "monto": bruto - banco, "recibido": _redondeo_efectivo(bruto - banco)}]
                    v = ventas_svc.crear_venta(s, cajero, {"items": items, "pagos": pagos})
                    if rnd.random() < 0.006:
                        ventas_svc.anular_venta(s, admin, v.id, rnd.choice(["Error de digitación", "El cliente se arrepintió", "Cobro duplicado"]))
                    elif rnd.random() < 0.008:
                        it = v.items[0]
                        medio = "banco" if any(p.medio.tipo == "banco" for p in v.pagos) and not any(p.medio.tipo == "efectivo" for p in v.pagos) else "efectivo"
                        ventas_svc.devolver(s, admin, v.id, [{"venta_item_id": it.id, "cantidad": min(1, it.cantidad), "danado": rnd.random() < 0.3}], medio,
                                            rnd.choice(["Producto en mal estado", "No era lo que buscaba", "Error de precio"]))
                    if not retiro_hecho and k > len(momentos) * 0.6:
                        retiro_hecho = True
                        c = caja_svc.calcular(s, turno)
                        if c["efectivo_esperado"] > 300000:
                            caja_svc.registrar_movimiento_caja(s, admin, turno, "retiro", (c["efectivo_esperado"] - base) // 2 // 10000 * 10000,
                                                               "Recogida de billetes a la caja fuerte")
                reloj[0] = datetime.combine(dia, time(horas[0][-1] + 1, 0, 30))
                c = caja_svc.calcular(s, turno)
                azar = rnd.random()
                dif = 0
                if cajero.usuario == "luis" and azar < 0.30:
                    dif = -rnd.choice([500, 1000, 2000, 3000, 5000, 10000])
                elif azar < 0.10:
                    dif = -rnd.choice([500, 1000, 2000])
                elif azar < 0.16:
                    dif = rnd.choice([500, 1000, 2000])
                dif_banco = -rnd.choice([0, 0, 0, 1500, 4800]) if rnd.random() < 0.08 else 0
                caja_svc.cerrar_turno(s, cajero, turno, efectivo_contado=c["efectivo_esperado"] + dif,
                                      banco_reportado=c["banco_esperado"] + dif_banco)
                s.commit()
            fijar(21, 45)
            inv.foto_inventario(s, dia)
            s.commit()

            # un conteo parcial real, 12 días antes de hoy
            if d == dias - 12 and dias >= 14:
                fijar(21, 50)
                cat = cats["Lácteos"]
                c = conteos_svc.crear(s, admin, nombre="Conteo de lácteos", tipo="parcial", alcance={"categoria_ids": [cat.id]})
                conteos_svc.iniciar(s, admin, c.id)
                for it in list(c.items):
                    p = s.get(m.Producto, it.producto_id)
                    r = rnd.random()
                    contado = p.stock_actual - (rnd.randint(1, 3) if r < 0.12 else 0) + (rnd.randint(1, 2) if 0.12 <= r < 0.17 else 0)
                    reloj[0] += timedelta(seconds=20)
                    conteos_svc.capturar(s, admin, c.id, producto_id=p.id, cantidad=max(0, contado))
                conteos_svc.cerrar_captura(s, admin, c.id)
                conteos_svc.aplicar(s, admin, c.id)
                s.commit()

        # ── hoy: la tienda amanece con todo cerrado y programaciones pendientes
        reloj[0] = datetime.now()
        core.reloj = datetime.now
        hoy = core.hoy()
        conteos_svc.guardar_programacion(s, {"nombre": "Conteo mensual total", "tipo": "total", "frecuencia": "mensual", "intervalo": 1,
                                             "proxima_fecha": (hoy + timedelta(days=2)).isoformat()})
        conteos_svc.guardar_programacion(s, {"nombre": "Conteo cíclico semanal (40 productos)", "tipo": "ciclico", "alcance": {"n": 40},
                                             "frecuencia": "semanal", "intervalo": 1, "proxima_fecha": (hoy - timedelta(days=1)).isoformat()})
        inv.foto_inventario(s, hoy)
        s.commit()
        respaldos.crear_respaldo(s, "diario")
        s.commit()
        n = s.scalar(select(func.count()).select_from(m.Venta))
        return {"productos": len(productos), "ventas": n, "dias": dias}
    finally:
        core.reloj = datetime.now
        s.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dias", type=int, default=30)
    ap.add_argument("--ventas-dia", type=int, default=90)
    ap.add_argument("--forzar", action="store_true", help="BORRA la base de datos actual antes de cargar la demo")
    a = ap.parse_args()
    ruta = config.ruta_db()
    if ruta.exists() and ruta.stat().st_size > 0:
        if not a.forzar:
            raise SystemExit(f"Ya existe una base de datos en {ruta}. Use --forzar para borrarla (¡se pierde todo!).")
        for sufijo in ("", "-wal", "-shm"):
            ruta.with_name(ruta.name + sufijo).unlink(missing_ok=True)
    db_mod.configurar()
    db_mod.inicializar()
    r = generar(a.dias, a.ventas_dia)
    print(f"Demo lista en {ruta}: {r['productos']} productos, {r['ventas']} ventas en {r['dias']} días.")
    print("Usuarios: admin / demo1234 (PIN 1234) · ana / ana1234 (PIN 4321) · luis / luis1234 (PIN 4321)")


if __name__ == "__main__":
    main()
