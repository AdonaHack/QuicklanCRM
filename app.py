import os
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
# Llave secreta para manejar sesiones seguras
app.secret_key = os.getenv("SECRET_KEY", "quickland_secret_key_2026_crm")

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "credentials.json")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def get_spreadsheet():
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID)

def get_ventas_sheet():
    sh = get_spreadsheet()
    try:
        return sh.worksheet("QuicklandCRM_Ventas")
    except Exception:
        return sh.sheet1

def get_usuarios_sheet():
    sh = get_spreadsheet()
    return sh.worksheet("Usuarios")

# Decorador para proteger rutas con Login
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "usuario" not in session:
            return redirect(url_for("login_view"))
        return f(*args, **kwargs)
    return decorated_function

# Decorador para restringir roles
def role_required(roles_permitidos):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if "usuario" not in session:
                return redirect(url_for("login_view"))
            rol_actual = session.get("rol", "").upper()
            if rol_actual not in [r.upper() for r in roles_permitidos] and rol_actual != "ADMIN":
                return "Acceso no autorizado para tu rol", 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ================= RUTAS DE AUTENTICACIÓN =================

@app.route("/login", methods=["GET", "POST"])
def login_view():
    if request.method == "GET":
        if "usuario" in session:
            rol = session.get("rol", "").upper()
            if rol == "VENTAS":
                return redirect(url_for("campo_view"))
            elif rol == "BACKOFFICE":
                return redirect(url_for("backoffice_view"))
            elif rol == "POSTVENTA":
                return redirect(url_for("postventa_view"))
            elif rol == "ADMIN":
                return redirect(url_for("admin_view"))
        return render_template("login.html")

    # POST Login
    datos = request.json or {}
    user_input = datos.get("usuario", "").strip()
    pass_input = datos.get("password", "").strip()

    try:
        u_sheet = get_usuarios_sheet()
        usuarios = u_sheet.get_all_records()

        usuario_encontrado = None
        for u in usuarios:
            if str(u.get("USUARIO", "")).strip().lower() == user_input.lower() and str(u.get("PASSWORD", "")).strip() == pass_input:
                if str(u.get("ESTADO", "")).strip().lower() == "activo":
                    usuario_encontrado = u
                    break
                else:
                    return jsonify({"status": "error", "message": "Tu usuario se encuentra inactivo."}), 403

        if usuario_encontrado:
            session["usuario"] = usuario_encontrado.get("USUARIO")
            session["nombre"] = usuario_encontrado.get("NOMBRE_COMPLETO")
            session["rol"] = usuario_encontrado.get("ROL")
            
            rol = session["rol"].upper()
            redirect_url = "/campo" if rol == "VENTAS" else f"/{rol.lower()}"
            return jsonify({"status": "success", "redirect": redirect_url, "rol": rol})
        else:
            return jsonify({"status": "error", "message": "Usuario o contraseña incorrectos."}), 401
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_view"))

# ================= RUTAS DE VISTAS POR ROL =================

@app.route("/")
@login_required
def index():
    rol = session.get("rol", "").upper()
    if rol == "VENTAS":
        return redirect(url_for("campo_view"))
    elif rol == "BACKOFFICE":
        return redirect(url_for("backoffice_view"))
    elif rol == "POSTVENTA":
        return redirect(url_for("postventa_view"))
    elif rol == "ADMIN":
        return redirect(url_for("admin_view"))
    return redirect(url_for("login_view"))

@app.route("/campo")
@login_required
@role_required(["VENTAS", "ADMIN"])
def campo_view():
    return render_template("campo.html", usuario=session.get("usuario"), nombre=session.get("nombre"), rol=session.get("rol"))

@app.route("/backoffice")
@login_required
@role_required(["BACKOFFICE", "ADMIN"])
def backoffice_view():
    return render_template("backoffice.html", usuario=session.get("usuario"), nombre=session.get("nombre"), rol=session.get("rol"))

@app.route("/postventa")
@login_required
@role_required(["POSTVENTA", "ADMIN"])
def postventa_view():
    return render_template("postventa.html", usuario=session.get("usuario"), nombre=session.get("nombre"), rol=session.get("rol"))

@app.route("/admin")
@login_required
@role_required(["ADMIN"])
def admin_view():
    return render_template("admin.html", usuario=session.get("usuario"), nombre=session.get("nombre"), rol=session.get("rol"))

# ================= API ENDPOINTS: VENTAS =================

@app.route("/api/ventas", methods=["GET"])
@login_required
def api_obtener_ventas():
    try:
        sheet = get_ventas_sheet()
        registros = sheet.get_all_records()
        rol = session.get("rol", "").upper()
        usuario = session.get("usuario", "").strip().upper()

        # Si el usuario es de VENTAS, filtrar SOLO sus propias ventas
        if rol == "VENTAS":
            ventas_filtradas = [
                v for v in registros
                if str(v.get("ASESOR_CAMPO", "")).strip().upper() == usuario or
                   str(v.get("ASESOR_CAMPO", "")).strip().upper() == session.get("nombre", "").strip().upper()
            ]
            return jsonify({"status": "success", "data": ventas_filtradas, "rol": rol})
        
        return jsonify({"status": "success", "data": registros, "rol": rol})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/ventas", methods=["POST"])
@login_required
@role_required(["VENTAS", "ADMIN"])
def api_registrar_venta():
    try:
        datos = request.json or {}
        sheet = get_ventas_sheet()

        ahora = datetime.now()
        id_venta = f"V-{ahora.strftime('%y%m%d%H%M%S')}"
        fecha_registro = ahora.strftime("%Y-%m-%d %H:%M")

        asesor = session.get("usuario", "").strip().upper()
        precio_plan = float(datos.get("precio_plan") or 0)
        # Comisión estimada por defecto: 100% del plan o valor enviado
        monto_comision = float(datos.get("monto_comision") or precio_plan)

        # Fila con las 24 columnas
        nueva_fila = [
            id_venta,                                   # A: ID_VENTA
            fecha_registro,                             # B: FECHA_REGISTRO
            asesor,                                     # C: ASESOR_CAMPO
            datos.get("cliente_nombre", "").strip().title(), # D: CLIENTE_NOMBRE
            datos.get("cliente_dni", "").strip(),       # E: CLIENTE_DNI
            datos.get("cliente_telefono", "").strip(),  # F: CLIENTE_TELEFONO
            datos.get("direccion", "").strip(),         # G: DIRECCION
            datos.get("plan_producto", "").strip(),     # H: PLAN_PRODUCTO
            datos.get("evidencia_drive", "").strip() or "N/A", # I: EVIDENCIA_DRIVE
            "PENDIENTE BO",                             # J: ESTADO_GENERAL
            "Pendiente",                                # K: ESTADO_BO
            "",                                         # L: FECHA_CONTACTO_BO
            "Pendiente",                                # M: ESTADO_SUBIDA
            "",                                         # N: FECHA_INSTALACION
            "Pendiente",                                # O: ESTADO_INSTALACION
            datos.get("observaciones", "").strip(),     # P: OBSERVACIONES
            fecha_registro,                             # Q: ULTIMA_ACTUALIZACION
            precio_plan,                                # R: PRECIO_PLAN
            monto_comision,                             # S: MONTO_COMISION
            "Pendiente instalación",                    # T: ESTADO_COMISION
            "",                                         # U: FECHA_PAGO_COMISION
            "",                                         # V: NUMERO_RECIBO_CLIENTE
            "",                                         # W: FECHA_VENCIMIENTO_RECIBO
            "Pendiente"                                 # X: ESTADO_PAGO_CLIENTE
        ]

        sheet.append_row(nueva_fila)
        return jsonify({"status": "success", "id_venta": id_venta})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/ventas/<id_venta>", methods=["PATCH"])
@login_required
def api_actualizar_venta(id_venta):
    try:
        datos = request.json or {}
        sheet = get_ventas_sheet()

        celda = sheet.find(id_venta)
        if not celda:
            return jsonify({"status": "error", "message": "Venta no encontrada"}), 404

        fila_num = celda.row
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M")
        rol = session.get("rol", "").upper()

        # Actualizaciones permitidas para BACK OFFICE y ADMIN
        if rol in ["BACKOFFICE", "ADMIN"]:
            if "estado_bo" in datos:
                sheet.update_cell(fila_num, 11, datos["estado_bo"])
                if datos["estado_bo"] == "Contactado":
                    sheet.update_cell(fila_num, 12, ahora)

            if "estado_subida" in datos:
                sheet.update_cell(fila_num, 13, datos["estado_subida"])

            if "fecha_instalacion" in datos:
                sheet.update_cell(fila_num, 14, datos["fecha_instalacion"])

            if "estado_instalacion" in datos:
                sheet.update_cell(fila_num, 15, datos["estado_instalacion"])
                # LÓGICA DE NEGOCIO: Si ya está instalado, cuenta como exitosa y pasa comisión a 'Por liquidar'
                if datos["estado_instalacion"] == "Instalado":
                    sheet.update_cell(fila_num, 20, "Por liquidar")

            if "observaciones" in datos:
                sheet.update_cell(fila_num, 16, datos["observaciones"])

        # Actualizaciones permitidas para POST-VENTA y ADMIN
        if rol in ["POSTVENTA", "ADMIN"]:
            if "numero_recibo" in datos:
                sheet.update_cell(fila_num, 22, datos["numero_recibo"])

            if "fecha_vencimiento_recibo" in datos:
                sheet.update_cell(fila_num, 23, datos["fecha_vencimiento_recibo"])

            if "estado_pago_cliente" in datos:
                sheet.update_cell(fila_num, 24, datos["estado_pago_cliente"])

            # LÓGICA DE COMISIÓN DE POST-VENTA
            if "estado_comision" in datos:
                sheet.update_cell(fila_num, 20, datos["estado_comision"])

            if "fecha_pago_comision" in datos:
                sheet.update_cell(fila_num, 21, datos["fecha_pago_comision"])

        # Recalcular ESTADO_GENERAL
        est_inst = sheet.cell(fila_num, 15).value
        est_sub = sheet.cell(fila_num, 13).value
        est_bo = sheet.cell(fila_num, 11).value

        if est_inst == "Instalado":
            estado_general = "INSTALADO"
        elif est_inst == "Frustrado":
            estado_general = "INST. FRUSTRADA"
        elif est_sub == "Subido":
            estado_general = "SUBIDO / EN RUTA"
        elif est_bo == "Contactado":
            estado_general = "VALIDADO BO"
        elif est_bo == "Rechazado":
            estado_general = "RECHAZADO BO"
        else:
            estado_general = "PENDIENTE BO"

        sheet.update_cell(fila_num, 10, estado_general)
        sheet.update_cell(fila_num, 17, ahora)

        return jsonify({"status": "success", "estado_general": estado_general})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ================= API ENDPOINTS: USUARIOS (ADMIN) =================

@app.route("/api/usuarios", methods=["GET"])
@login_required
@role_required(["ADMIN"])
def api_obtener_usuarios():
    try:
        u_sheet = get_usuarios_sheet()
        usuarios = u_sheet.get_all_records()
        # Ocultar contraseñas en la respuesta
        for u in usuarios:
            u["PASSWORD"] = "••••••"
        return jsonify({"status": "success", "data": usuarios})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/usuarios", methods=["POST"])
@login_required
@role_required(["ADMIN"])
def api_crear_usuario():
    try:
        datos = request.json or {}
        u_sheet = get_usuarios_sheet()
        usuarios = u_sheet.get_all_records()

        nuevo_user = datos.get("usuario", "").strip()
        for u in usuarios:
            if str(u.get("USUARIO", "")).strip().lower() == nuevo_user.lower():
                return jsonify({"status": "error", "message": "El nombre de usuario ya existe."}), 400

        nuevo_id = f"U-{len(usuarios) + 1:03d}"
        nueva_fila = [
            nuevo_id,
            datos.get("nombre_completo", "").strip(),
            nuevo_user,
            datos.get("password", "").strip(),
            datos.get("rol", "VENTAS").strip().upper(),
            datos.get("estado", "Activo").strip()
        ]
        u_sheet.append_row(nueva_fila)
        return jsonify({"status": "success", "id_usuario": nuevo_id})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/usuarios/<usuario>", methods=["PATCH"])
@login_required
@role_required(["ADMIN"])
def api_modificar_usuario(usuario):
    try:
        datos = request.json or {}
        u_sheet = get_usuarios_sheet()
        celda = u_sheet.find(usuario)
        if not celda:
            return jsonify({"status": "error", "message": "Usuario no encontrado"}), 404

        fila = celda.row
        # Columnas: ID(1), NOMBRE(2), USUARIO(3), PASSWORD(4), ROL(5), ESTADO(6)
        if "password" in datos and datos["password"].strip():
            u_sheet.update_cell(fila, 4, datos["password"].strip())
        if "rol" in datos:
            u_sheet.update_cell(fila, 5, datos["rol"].strip().upper())
        if "estado" in datos:
            u_sheet.update_cell(fila, 6, datos["estado"].strip())

        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)