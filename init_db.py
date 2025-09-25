import sqlite3

def init_db():
    conn = sqlite3.connect("pos.db")
    c = conn.cursor()

    # ===========================
    # TERCEROS (Clientes / Proveedores)
    # ===========================
    c.execute("""
    CREATE TABLE IF NOT EXISTS terceros (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombres TEXT NOT NULL,
        apellidos TEXT,
        telefono TEXT,
        correo TEXT,
        direccion TEXT,
        tipo TEXT NOT NULL CHECK(tipo IN ('Cliente', 'Proveedor'))
    )
    """)

    # ===========================
    # INVENTARIO
    # ===========================
    c.execute("""
    CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        descripcion TEXT,
        costo REAL NOT NULL,
        precio REAL NOT NULL,
        stock REAL NOT NULL DEFAULT 0,
        unidad TEXT DEFAULT 'UND'
    )
    """)

    # ===========================
    # FACTURACIÓN (VENTAS)
    # ===========================
    c.execute("""
    CREATE TABLE IF NOT EXISTS facturas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tercero_id INTEGER,
        numero INTEGER NOT NULL,
        fecha TEXT NOT NULL,
        total REAL NOT NULL,
        FOREIGN KEY (tercero_id) REFERENCES terceros(id)
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS detalle_factura (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        factura_id INTEGER NOT NULL,
        producto_id INTEGER NOT NULL,
        cantidad REAL NOT NULL,
        precio REAL NOT NULL,
        total REAL NOT NULL,
        FOREIGN KEY (factura_id) REFERENCES facturas(id),
        FOREIGN KEY (producto_id) REFERENCES productos(id)
    )
    """)

    # ===========================
    # COMPRAS
    # ===========================
    c.execute("""
    CREATE TABLE IF NOT EXISTS compras (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tercero_id INTEGER,
        numero TEXT,
        fecha TEXT NOT NULL,
        total REAL NOT NULL,
        forma_pago TEXT CHECK(forma_pago IN ('contado','credito')) NOT NULL,
        pagada INTEGER DEFAULT 0,
        FOREIGN KEY (tercero_id) REFERENCES terceros(id)
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS detalle_compra (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        compra_id INTEGER NOT NULL,
        producto_id INTEGER NOT NULL,
        cantidad REAL NOT NULL,
        costo REAL NOT NULL,
        total REAL NOT NULL,
        FOREIGN KEY (compra_id) REFERENCES compras(id),
        FOREIGN KEY (producto_id) REFERENCES productos(id)
    )
    """)

    # ===========================
    # GASTOS / INGRESOS
    # ===========================
    c.execute("""
    CREATE TABLE IF NOT EXISTS gastos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        descripcion TEXT NOT NULL,
        monto REAL NOT NULL,
        fecha TEXT NOT NULL,
        tipo TEXT CHECK(tipo IN ('gasto','ingreso')) NOT NULL
    )
    """)

    # ===========================
    # CONTABILIDAD
    # ===========================
    c.execute("""
    CREATE TABLE IF NOT EXISTS puc (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo TEXT NOT NULL UNIQUE,
        nombre TEXT NOT NULL,
        tipo TEXT CHECK(tipo IN ('activo','pasivo','patrimonio','ingreso','gasto')) NOT NULL
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS movimientos_contables (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT NOT NULL,
        cuenta_id INTEGER NOT NULL,
        descripcion TEXT,
        debito REAL DEFAULT 0,
        credito REAL DEFAULT 0,
        modulo TEXT,
        referencia_id INTEGER,
        FOREIGN KEY (cuenta_id) REFERENCES puc(id)
    )
    """)

    conn.commit()
    conn.close()
    print("✅ Base de datos inicializada en pos.db con la tabla 'terceros'.")

if __name__ == "__main__":
    init_db()
