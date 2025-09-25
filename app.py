from flask import Flask, render_template, redirect, url_for, request, session, jsonify
import sqlite3
from datetime import datetime, timedelta
from collections import defaultdict

app = Flask(__name__)
app.secret_key = "clave_secreta_super_segura"

# ===== CONEXIÓN DB =====
def get_db_connection():
    conn = sqlite3.connect("pos.db")
    conn.row_factory = sqlite3.Row
    return conn


# ===== LOGIN =====
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form["usuario"]
        clave = request.form["clave"]

        if usuario == "admin" and clave == "1234":
            session["user"] = usuario
            return redirect(url_for("facturacion"))
        else:
            return render_template("login.html", error="Usuario o clave incorrectos")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ===== FACTURACIÓN =====
@app.route("/facturacion")
def facturacion():
    if "user" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cur = conn.cursor()

    clientes = cur.execute("""
        SELECT id, nombres || ' ' || IFNULL(apellidos,'') as nombre
        FROM terceros WHERE tipo='Cliente'
    """).fetchall()

    productos = cur.execute("SELECT id, nombre, stock, costo, precio FROM productos").fetchall()

    cur.execute("SELECT MAX(numero) FROM facturas")
    last_num = cur.fetchone()[0] or 0
    factura_num = last_num + 1

    conn.close()

    return render_template(
        "facturacion.html",
        user=session["user"],
        clientes=clientes,
        productos=productos,
        factura_num=factura_num,
        fecha=datetime.now().strftime("%Y-%m-%d")
    )


@app.route("/facturacion/save", methods=["POST"])
def facturacion_save():
    if "user" not in session:
        return redirect(url_for("login"))

    data = request.get_json()
    try:
        tercero_id = data.get("cliente_id")
        factura_num = data.get("factura_num")
        fecha = data.get("fecha") or datetime.now().strftime("%Y-%m-%d")
        lineas = data.get("lines", [])
        total = sum(l["total"] for l in lineas)

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO facturas (tercero_id, numero, fecha, total)
            VALUES (?, ?, ?, ?)
        """, (tercero_id, factura_num, fecha, total))
        factura_id = cur.lastrowid

        for l in lineas:
            # Aquí se inserta el precio del producto en el momento de la venta
            cur.execute("""
                INSERT INTO detalle_factura (factura_id, producto_id, cantidad, precio, total)
                VALUES (?, ?, ?, ?, ?)
            """, (factura_id, l["producto_id"], l["cantidad"], l["precio"], l["total"]))

            # El stock se reduce
            cur.execute("""
                UPDATE productos SET stock = stock - ? WHERE id = ?
            """, (l["cantidad"], l["producto_id"]))

        conn.commit()
        conn.close()

        return jsonify({"success": True, "factura_num": factura_num})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# ===== COMPRAS =====
@app.route("/compras")
def compras():
    if "user" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cur = conn.cursor()

    proveedores = cur.execute("""
        SELECT id, nombres || ' ' || IFNULL(apellidos,'') as nombre
        FROM terceros WHERE tipo='Proveedor'
    """).fetchall()

    # Se obtienen los productos y sus costos
    productos = cur.execute("SELECT id, nombre, stock, costo FROM productos").fetchall()

    cur.execute("SELECT MAX(id) FROM compras")
    last_num = cur.fetchone()[0] or 0
    compra_num = last_num + 1

    conn.close()

    return render_template(
        "compras.html",
        user=session["user"],
        proveedores=proveedores,
        productos=productos,
        compra_num=compra_num,
        fecha=datetime.now().strftime("%Y-%m-%d")
    )


@app.route("/compras/save", methods=["POST"])
def compras_save():
    if "user" not in session:
        return jsonify({"success": False, "error": "No autorizado"})

    data = request.get_json()
    try:
        tercero_id = data.get("proveedor_id")
        numero = data.get("numero")
        fecha = data.get("fecha") or datetime.now().strftime("%Y-%m-%d")
        forma_pago = data.get("forma_pago")
        lineas = data.get("lines", [])
        total = sum(l["total"] for l in lineas)

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO compras (tercero_id, numero, fecha, total, forma_pago, pagada)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (tercero_id, numero, fecha, total, forma_pago, 0))
        compra_id = cur.lastrowid

        for l in lineas:
            producto_id = l["producto_id"]
            cantidad_comprada = l["cantidad"]
            costo_compra = l["costo"]

            # 1. Obtener el stock y el costo actuales del producto
            cur.execute("SELECT stock, costo FROM productos WHERE id = ?", (producto_id,))
            producto_db = cur.fetchone()
            stock_anterior = producto_db["stock"]
            costo_anterior = producto_db["costo"]

            # 2. Calcular el nuevo costo promedio ponderado
            nuevo_stock = stock_anterior + cantidad_comprada
            if nuevo_stock > 0:
                nuevo_costo = ((stock_anterior * costo_anterior) + (cantidad_comprada * costo_compra)) / nuevo_stock
            else:
                nuevo_costo = 0

            # 3. Insertar el detalle de la compra
            cur.execute("""
                INSERT INTO detalle_compra (compra_id, producto_id, cantidad, costo, total)
                VALUES (?, ?, ?, ?, ?)
            """, (compra_id, producto_id, cantidad_comprada, costo_compra, l["total"]))

            # 4. Actualizar el inventario con el nuevo stock y el costo promedio
            cur.execute("""
                UPDATE productos SET stock = ?, costo = ? WHERE id = ?
            """, (nuevo_stock, nuevo_costo, producto_id))

        conn.commit()
        conn.close()

        return jsonify({"success": True, "compra_num": numero})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# ===== INVENTARIO =====
@app.route("/inventario")
def inventario():
    if "user" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cur = conn.cursor()
    # Se obtienen las 4 columnas del inventario: nombre, stock, costo y precio
    productos_raw = cur.execute("SELECT id, nombre, stock, costo, precio FROM productos").fetchall()
    conn.close()

    # Convertir a diccionarios para el template
    productos = []
    for p in productos_raw:
        productos.append({
            'id': p[0],
            'nombre': p[1],
            'stock': p[2],
            'costo': p[3],
            'precio': p[4]
        })

    return render_template("inventario.html", user=session["user"], productos=productos)


@app.route("/add_producto", methods=["POST"])
def add_producto():
    if "user" not in session:
        return jsonify({"success": False, "error": "No autorizado"})
    
    data = request.get_json()
    try:
        nombre = data.get("nombre", "").strip()
        stock = int(data.get("stock", 0))
        costo = float(data.get("costo", 0))
        precio = float(data.get("precio", 0))
        
        if not nombre:
            return jsonify({"success": False, "error": "Nombre requerido"})
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO productos (nombre, stock, costo, precio) 
            VALUES (?, ?, ?, ?)
        """, (nombre, stock, costo, precio))
        conn.commit()
        nuevo_id = cur.lastrowid
        conn.close()
        
        return jsonify({
            "success": True, 
            "id": nuevo_id,
            "mensaje": f"Producto '{nombre}' agregado correctamente"
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/update_producto/<int:producto_id>", methods=["PUT"])
def update_producto(producto_id):
    if "user" not in session:
        return jsonify({"success": False, "error": "No autorizado"})
    
    data = request.get_json()
    try:
        nombre = data.get("nombre", "").strip()
        stock = int(data.get("stock", 0))
        costo = float(data.get("costo", 0))
        precio = float(data.get("precio", 0))
        
        if not nombre:
            return jsonify({"success": False, "error": "Nombre requerido"})
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE productos SET nombre=?, stock=?, costo=?, precio=? 
            WHERE id=?
        """, (nombre, stock, costo, precio, producto_id))
        conn.commit()
        conn.close()
        
        return jsonify({
            "success": True,
            "mensaje": "Producto actualizado correctamente"
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/delete_producto/<int:producto_id>", methods=["DELETE"])
def delete_producto(producto_id):
    if "user" not in session:
        return jsonify({"success": False, "error": "No autorizado"})
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM productos WHERE id=?", (producto_id,))
        conn.commit()
        conn.close()
        
        return jsonify({
            "success": True,
            "mensaje": "Producto eliminado correctamente"
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# ===== AGREGAR NUEVO TERCERO =====
@app.route("/tercero/add", methods=["POST"])
def add_tercero():
    if "user" not in session:
        return redirect(url_for("login"))

    data = request.get_json()
    try:
        nombres = data.get("nombres")
        apellidos = data.get("apellidos")
        telefono = data.get("telefono")
        correo = data.get("correo")
        direccion = data.get("direccion")
        tipo = data.get("tipo")

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO terceros (nombres, apellidos, telefono, correo, direccion, tipo)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (nombres, apellidos, telefono, correo, direccion, tipo))
        conn.commit()
        tercero_id = cur.lastrowid
        conn.close()

        return jsonify({"success": True, "id": tercero_id, "nombre": f"{nombres} {apellidos}"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# ===== OTROS MÓDULOS =====
@app.route("/gastos")
def gastos():
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template("gastos.html", user=session["user"])


# ===== RESÚMENES Y REPORTES =====
@app.route("/resumenes")
def resumenes():
    if "user" not in session:
        return redirect(url_for("login"))
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Obtener fechas para los selectores
    today = datetime.now().strftime("%Y-%m-%d")
    first_day_month = datetime.now().replace(day=1).strftime("%Y-%m-%d")
    
    conn.close()
    return render_template("resumenes.html", 
                         user=session["user"],
                         fecha_inicio=first_day_month,
                         fecha_fin=today)

@app.route("/api/resumen/ventas", methods=["POST"])
def api_resumen_ventas():
    if "user" not in session:
        return jsonify({"success": False, "error": "No autorizado"})
    
    data = request.get_json()
    fecha_inicio = data.get("fecha_inicio")
    fecha_fin = data.get("fecha_fin")
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Resumen de ventas por día
        ventas_diarias = cur.execute("""
            SELECT DATE(fecha) as dia, 
                   COUNT(*) as num_facturas, 
                   SUM(total) as total_ventas
            FROM facturas 
            WHERE fecha BETWEEN ? AND ?
            GROUP BY DATE(fecha)
            ORDER BY dia
        """, (fecha_inicio, fecha_fin)).fetchall()
        
        # Total del período
        total_periodo = cur.execute("""
            SELECT COUNT(*) as facturas, 
                   SUM(total) as total,
                   AVG(total) as promedio
            FROM facturas 
            WHERE fecha BETWEEN ? AND ?
        """, (fecha_inicio, fecha_fin)).fetchone()
        
        # Producto más vendido
        producto_top = cur.execute("""
            SELECT p.nombre, 
                   SUM(df.cantidad) as cantidad_vendida,
                   SUM(df.total) as ingresos_producto
            FROM detalle_factura df
            JOIN productos p ON df.producto_id = p.id
            JOIN facturas f ON df.factura_id = f.id
            WHERE f.fecha BETWEEN ? AND ?
            GROUP BY p.id, p.nombre
            ORDER BY cantidad_vendida DESC
            LIMIT 1
        """, (fecha_inicio, fecha_fin)).fetchone()
        
        # Top 5 productos más vendidos
        top_productos = cur.execute("""
            SELECT p.nombre, 
                   SUM(df.cantidad) as cantidad_vendida,
                   SUM(df.total) as ingresos_producto,
                   COUNT(DISTINCT f.id) as facturas_aparece
            FROM detalle_factura df
            JOIN productos p ON df.producto_id = p.id
            JOIN facturas f ON df.factura_id = f.id
            WHERE f.fecha BETWEEN ? AND ?
            GROUP BY p.id, p.nombre
            ORDER BY cantidad_vendida DESC
            LIMIT 5
        """, (fecha_inicio, fecha_fin)).fetchall()
        
        # Cliente que más compra
        cliente_top = cur.execute("""
            SELECT t.nombres || ' ' || IFNULL(t.apellidos,'') as cliente,
                   COUNT(*) as num_compras,
                   SUM(f.total) as total_comprado
            FROM facturas f
            JOIN terceros t ON f.tercero_id = t.id
            WHERE f.fecha BETWEEN ? AND ?
            GROUP BY t.id, cliente
            ORDER BY total_comprado DESC
            LIMIT 1
        """, (fecha_inicio, fecha_fin)).fetchone()
        
        conn.close()
        
        return jsonify({
            "success": True,
            "ventas_diarias": [dict(row) for row in ventas_diarias],
            "total_periodo": dict(total_periodo) if total_periodo else {},
            "producto_top": dict(producto_top) if producto_top else {},
            "top_productos": [dict(row) for row in top_productos],
            "cliente_top": dict(cliente_top) if cliente_top else {}
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/resumen/compras", methods=["POST"])
def api_resumen_compras():
    if "user" not in session:
        return jsonify({"success": False, "error": "No autorizado"})
    
    data = request.get_json()
    fecha_inicio = data.get("fecha_inicio")
    fecha_fin = data.get("fecha_fin")
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Resumen de compras por día
        compras_diarias = cur.execute("""
            SELECT DATE(fecha) as dia, 
                   COUNT(*) as num_compras, 
                   SUM(total) as total_compras
            FROM compras 
            WHERE fecha BETWEEN ? AND ?
            GROUP BY DATE(fecha)
            ORDER BY dia
        """, (fecha_inicio, fecha_fin)).fetchall()
        
        # Total del período
        total_compras = cur.execute("""
            SELECT COUNT(*) as compras, 
                   SUM(total) as total,
                   AVG(total) as promedio,
                   SUM(CASE WHEN pagada = 1 THEN total ELSE 0 END) as pagadas,
                   SUM(CASE WHEN pagada = 0 THEN total ELSE 0 END) as pendientes
            FROM compras 
            WHERE fecha BETWEEN ? AND ?
        """, (fecha_inicio, fecha_fin)).fetchone()
        
        # Proveedor principal
        proveedor_top = cur.execute("""
            SELECT t.nombres || ' ' || IFNULL(t.apellidos,'') as proveedor,
                   COUNT(*) as num_compras,
                   SUM(c.total) as total_comprado
            FROM compras c
            JOIN terceros t ON c.tercero_id = t.id
            WHERE c.fecha BETWEEN ? AND ?
            GROUP BY t.id, proveedor
            ORDER BY total_comprado DESC
            LIMIT 1
        """, (fecha_inicio, fecha_fin)).fetchone()
        
        # Productos más comprados
        productos_comprados = cur.execute("""
            SELECT p.nombre, 
                   SUM(dc.cantidad) as cantidad_comprada,
                   SUM(dc.total) as total_invertido,
                   COUNT(DISTINCT c.id) as compras_aparece
            FROM detalle_compra dc
            JOIN productos p ON dc.producto_id = p.id
            JOIN compras c ON dc.compra_id = c.id
            WHERE c.fecha BETWEEN ? AND ?
            GROUP BY p.id, p.nombre
            ORDER BY cantidad_comprada DESC
            LIMIT 5
        """, (fecha_inicio, fecha_fin)).fetchall()
        
        conn.close()
        
        return jsonify({
            "success": True,
            "compras_diarias": [dict(row) for row in compras_diarias],
            "total_compras": dict(total_compras) if total_compras else {},
            "proveedor_top": dict(proveedor_top) if proveedor_top else {},
            "productos_comprados": [dict(row) for row in productos_comprados]
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/facturas/lista", methods=["POST"])
def api_facturas_lista():
    if "user" not in session:
        return jsonify({"success": False, "error": "No autorizado"})
    
    data = request.get_json()
    fecha_inicio = data.get("fecha_inicio")
    fecha_fin = data.get("fecha_fin")
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        facturas = cur.execute("""
            SELECT f.id, f.numero, f.fecha, f.total,
                   t.nombres || ' ' || IFNULL(t.apellidos,'') as cliente
            FROM facturas f
            LEFT JOIN terceros t ON f.tercero_id = t.id
            WHERE f.fecha BETWEEN ? AND ?
            ORDER BY f.fecha DESC, f.numero DESC
        """, (fecha_inicio, fecha_fin)).fetchall()
        
        conn.close()
        
        return jsonify({
            "success": True,
            "facturas": [dict(row) for row in facturas]
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/compras/lista", methods=["POST"])
def api_compras_lista():
    if "user" not in session:
        return jsonify({"success": False, "error": "No autorizado"})
    
    data = request.get_json()
    fecha_inicio = data.get("fecha_inicio")
    fecha_fin = data.get("fecha_fin")
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        compras = cur.execute("""
            SELECT c.id, c.numero, c.fecha, c.total, c.forma_pago, c.pagada,
                   t.nombres || ' ' || IFNULL(t.apellidos,'') as proveedor
            FROM compras c
            LEFT JOIN terceros t ON c.tercero_id = t.id
            WHERE c.fecha BETWEEN ? AND ?
            ORDER BY c.fecha DESC, c.numero DESC
        """, (fecha_inicio, fecha_fin)).fetchall()
        
        conn.close()
        
        return jsonify({
            "success": True,
            "compras": [dict(row) for row in compras]
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/factura/<int:factura_id>")
def api_factura_detalle(factura_id):
    if "user" not in session:
        return jsonify({"success": False, "error": "No autorizado"})
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Datos de la factura
        factura = cur.execute("""
            SELECT f.*, t.nombres || ' ' || IFNULL(t.apellidos,'') as cliente,
                   t.telefono, t.direccion
            FROM facturas f
            LEFT JOIN terceros t ON f.tercero_id = t.id
            WHERE f.id = ?
        """, (factura_id,)).fetchone()
        
        if not factura:
            return jsonify({"success": False, "error": "Factura no encontrada"})
        
        # Detalle de la factura
        detalle = cur.execute("""
            SELECT df.cantidad, df.precio, df.total, p.nombre as producto
            FROM detalle_factura df
            JOIN productos p ON df.producto_id = p.id
            WHERE df.factura_id = ?
        """, (factura_id,)).fetchall()
        
        conn.close()
        
        return jsonify({
            "success": True,
            "factura": dict(factura),
            "detalle": [dict(row) for row in detalle]
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/compra/<int:compra_id>")
def api_compra_detalle(compra_id):
    if "user" not in session:
        return jsonify({"success": False, "error": "No autorizado"})
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Datos de la compra
        compra = cur.execute("""
            SELECT c.*, t.nombres || ' ' || IFNULL(t.apellidos,'') as proveedor,
                   t.telefono, t.direccion
            FROM compras c
            LEFT JOIN terceros t ON c.tercero_id = t.id
            WHERE c.id = ?
        """, (compra_id,)).fetchone()
        
        if not compra:
            return jsonify({"success": False, "error": "Compra no encontrada"})
        
        # Detalle de la compra
        detalle = cur.execute("""
            SELECT dc.cantidad, dc.costo, dc.total, p.nombre as producto
            FROM detalle_compra dc
            JOIN productos p ON dc.producto_id = p.id
            WHERE dc.compra_id = ?
        """, (compra_id,)).fetchall()
        
        conn.close()
        
        return jsonify({
            "success": True,
            "compra": dict(compra),
            "detalle": [dict(row) for row in detalle]
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# ===== INICIO =====
@app.route("/")
def index():
    return redirect(url_for("login"))


if __name__ == "__main__":
   app.run(host="0.0.0.0", port=5000, debug=True)