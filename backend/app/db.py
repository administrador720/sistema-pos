"""Motor SQLite: WAL, llaves foráneas activas, escrituras con BEGIN IMMEDIATE.

Las lecturas usan BEGIN normal (no se bloquean entre sí en modo WAL). Las escrituras piden
`execution_options={"escritura": True}` y toman el candado de escritura desde el inicio,
evitando los "database is locked" por promoción de lectura a escritura.
"""
import threading
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from . import config

engine = None
SessionLocal = None
bloqueo_motor = threading.RLock()  # se toma al reemplazar la base (restaurar respaldo)


def configurar(ruta: Path | str | None = None):
    """Crea el motor. Se puede llamar de nuevo (tests, restauración de respaldos)."""
    global engine, SessionLocal
    ruta = Path(ruta) if ruta else config.ruta_db()
    if engine is not None:
        engine.dispose()
    eng = create_engine(
        f"sqlite:///{ruta}",
        connect_args={"check_same_thread": False, "timeout": 15},
        pool_pre_ping=False,
    )

    @event.listens_for(eng, "connect")
    def _al_conectar(dbapi, _):
        dbapi.isolation_level = None  # nosotros emitimos BEGIN
        cur = dbapi.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=FULL")  # no perder ventas en un corte de luz
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=15000")
        cur.close()

    @event.listens_for(eng, "begin")
    def _al_comenzar(conn):
        if conn.get_execution_options().get("escritura"):
            conn.exec_driver_sql("BEGIN IMMEDIATE")
        else:
            conn.exec_driver_sql("BEGIN")

    engine = eng
    SessionLocal = sessionmaker(bind=eng, autoflush=False, expire_on_commit=False)
    return eng


def nueva_sesion(escritura: bool = False):
    s = SessionLocal()
    if escritura:
        s.connection(execution_options={"escritura": True})
    return s


def get_db():
    """Dependencia de FastAPI: sesión de solo lectura."""
    db = nueva_sesion()
    try:
        yield db
    finally:
        db.close()


def get_db_w():
    """Dependencia de FastAPI: sesión de escritura. El endpoint hace `db.commit()` explícito."""
    db = nueva_sesion(escritura=True)
    try:
        yield db
    finally:
        db.rollback()
        db.close()


# ───────────────────────────── Esquema y migraciones ─────────────────────────────
# Cada migración es una función (conexión) que se ejecuta una sola vez, en orden. Para cambiar el esquema
# después de instalar: agregar una función al final de MIGRACIONES; `create_all` solo crea tablas nuevas.
def _m1_indice_ultima_venta(con):
    con.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_venta_items_prod_venta ON venta_items (producto_id, venta_id)")


def _m2_productos_por_peso(con):
    """Productos por peso (kg) y botones de acceso rápido. Las cantidades ya aceptan decimales sin cambios."""
    cols = {f[1] for f in con.exec_driver_sql("PRAGMA table_info(productos)")}
    if "unidad" not in cols:
        con.exec_driver_sql("ALTER TABLE productos ADD COLUMN unidad VARCHAR(3) NOT NULL DEFAULT 'u'")
    if "rapido" not in cols:
        con.exec_driver_sql("ALTER TABLE productos ADD COLUMN rapido BOOLEAN NOT NULL DEFAULT 0")


MIGRACIONES: list = [_m1_indice_ultima_venta, _m2_productos_por_peso]


def inicializar():
    """Crea las tablas que falten y aplica las migraciones pendientes."""
    from . import models
    from sqlalchemy import text
    models.Base.metadata.create_all(engine)
    with engine.begin() as con:
        con.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS _version (id INTEGER PRIMARY KEY CHECK (id = 1), version INTEGER NOT NULL)")
        fila = con.execute(text("SELECT version FROM _version WHERE id = 1")).first()
        if fila is None:
            con.exec_driver_sql("INSERT INTO _version (id, version) VALUES (1, 0)")
        actual = fila[0] if fila else 0
        if actual > len(MIGRACIONES):
            raise RuntimeError(f"La base de datos es de una versión más nueva del programa (esquema {actual}; este programa "
                               f"conoce hasta el {len(MIGRACIONES)}). Instale la versión más reciente en vez de abrirla con esta.")
        for n, migracion in enumerate(MIGRACIONES, start=1):
            if n > actual:
                migracion(con)
                con.exec_driver_sql(f"UPDATE _version SET version = {n} WHERE id = 1")
