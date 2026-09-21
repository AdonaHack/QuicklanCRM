import os
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "quickland_secret_key_2026_crm")

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
# Render guarda los Secret Files en /etc/secrets/
DEFAULT_CRED_PATH = "/etc/secrets/credentials.json" if os.path.exists("/etc/secrets/credentials.json") else "credentials.json"
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", DEFAULT_CRED_PATH)
DRIVE_FOLDER_ID = os.getenv("DRIVE_FOLDER_ID", "") # Carpeta de Drive donde se guardarán las fotos/audios

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def get_credentials():
    return Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)

def get_spreadsheet():
    creds = get_credentials()
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

# Lógica centralizada para subir archivos a Google Drive
def upload_file_to_drive(file_obj, filename, folder_id):
    try:
        creds = get_credentials()
        drive_service = build('drive', 'v3', credentials=creds)
        file_metadata = {'name': filename, 'parents': [folder_id]}
        
        # Leemos el archivo en memoria y lo subimos
        media = MediaIoBaseUpload(file_obj.stream, mimetype=file_obj.mimetype, resumable=True)
        uploaded_file = drive_service.files().create(
            body=file_metadata, media_body=media, fields='id, webViewLink'
        ).execute()
        
        # Otorga permisos de lectura pública (cualquiera con el link puede verlo)
        drive_service.permissions().create(
            fileId=uploaded_file.get('id'),
            body={'type': 'anyone', 'role': 'reader'}
        ).execute()
        
        return uploaded_file.get('webViewLink')
    except Exception as e:
        print(f"Error subiendo a Drive: {e}")
        return None

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "usuario" not in session:
            return redirect(url_for("login_view"))
        return f(*args, **kwargs)
    return decorated_function

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

# ================= RUTAS DE AUTENTICACIÓN Y VISTAS =================

@app.route("/login", methods=["GET", "POST"])
def login_view():
    if request.method == "GET":
        if "usuario" in session:
            rol = session.get("rol", "").upper()
            if rol == "VENTAS": return redirect(url_for("campo_view"))
            elif rol == "BACKOFFICE": return redirect(url_for("backoffice_view"))
            elif rol == "POSTVENTA": return redirect(url_for("postventa_view"))
            elif rol == "ADMIN": return redirect(url_for("admin_view"))
        return render_template("login.html")

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

@app.route("/")
def index():
    if "usuario" in session:
        rol = session.get("rol", "").upper()
        if rol == "VENTAS": return redirect(url_for("campo_view"))
        elif rol == "BACKOFFICE": return redirect(url_for("backoffice_view"))
        elif rol == "POSTVENTA": return redirect(url_for("postventa_view"))
        elif rol == "ADMIN": return redirect(url_for("admin_view"))
    return render_template("landing.html")

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
        # AHORA RECIBE FORMDATA Y ARCHIVOS
        datos = request.form
        archivos = request.files.getlist("documentos_venta")

        ahora = datetime.now()
        id_venta = f"V-{ahora.strftime('%y%m%d%H%M%S')}"
        fecha_registro = ahora.strftime("%Y-%m-%d %H:%M")

        asesor = session.get("usuario", "").strip().upper()
        precio_plan = float(datos.get("precio_plan") or 0)
        monto_comision = float(datos.get("monto_comision") or precio_plan)

        # Lógica de subida de múltiples archivos a Drive
        enlaces_drive = []
        if DRIVE_FOLDER_ID and archivos:
            for idx, archivo in enumerate(archivos):
                if archivo.filename:
                    ext = archivo.filename.split('.')[-1]
                    nuevo_nombre = f"{id_venta}_Doc_{idx+1}.{ext}"
                    link = upload_file_to_drive(archivo, nuevo_nombre, DRIVE_FOLDER_ID)
                    if link: enlaces_drive.append(link)
        
        # Combinamos los links con un salto de línea
        evidencia_str = "\n".join(enlaces_drive) if enlaces_drive else "N/A"

        nueva_fila = [
            id_venta,                                   
            fecha_registro,                             
            asesor,                                     
            datos.get("cliente_nombre", "").strip().title(), 
            datos.get("cliente_dni", "").strip(),       
            datos.get("cliente_telefono", "").strip(),  
            datos.get("direccion", "").strip(),         
            datos.get("plan_producto", "").strip(),     
            evidencia_str, # Columna de Evidencia con los links
            "PENDIENTE BO",                             
            "Pendiente",                                
            "",                                         
            "Pendiente",                                
            "",                                         
            "Pendiente",                                
            datos.get("observaciones", "").strip(),     
            fecha_registro,                             
            precio_plan,                                
            monto_comision,                             
            "Pendiente instalación",                    
            "",                                         
            "",                                         
            "",                                         
            "Pendiente"                                 
        ]

        sheet = get_ventas_sheet()
        sheet.append_row(nueva_fila)
        return jsonify({"status": "success", "id_venta": id_venta})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/ventas/<id_venta>", methods=["PATCH"])
@login_required
def api_actualizar_venta(id_venta):
    try:
        sheet = get_ventas_sheet()
        celda = sheet.find(id_venta)
        if not celda:
            return jsonify({"status": "error", "message": "Venta no encontrada"}), 404

        fila_num = celda.row
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M")
        rol = session.get("rol", "").upper()

        # Determinar si recibimos FormData (Audio) o JSON tradicional
        if request.content_type and "multipart/form-data" in request.content_type:
            datos = request.form.to_dict()
            audio_file = request.files.get("audio_contrato")
        else:
            datos = request.json or {}
            audio_file = None

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
                if datos["estado_instalacion"] == "Instalado":
                    sheet.update_cell(fila_num, 20, "Por liquidar")

            if "observaciones" in datos:
                sheet.update_cell(fila_num, 16, datos["observaciones"])

            # Guardar el audio en Drive y anexarlo a la columna EVIDENCIA_DRIVE (Columna 9)
            if audio_file and DRIVE_FOLDER_ID:
                nuevo_nombre = f"{id_venta}_Audio_Contrato.webm"
                link_audio = upload_file_to_drive(audio_file, nuevo_nombre, DRIVE_FOLDER_ID)
                if link_audio:
                    evidencia_actual = sheet.cell(fila_num, 9).value or ""
                    nueva_evidencia = f"{evidencia_actual}\nAUDIO: {link_audio}" if evidencia_actual and evidencia_actual != "N/A" else f"AUDIO: {link_audio}"
                    sheet.update_cell(fila_num, 9, nueva_evidencia)

        if rol in ["POSTVENTA", "ADMIN"]:
            if "numero_recibo" in datos: sheet.update_cell(fila_num, 22, datos["numero_recibo"])
            if "fecha_vencimiento_recibo" in datos: sheet.update_cell(fila_num, 23, datos["fecha_vencimiento_recibo"])
            if "estado_pago_cliente" in datos: sheet.update_cell(fila_num, 24, datos["estado_pago_cliente"])
            if "estado_comision" in datos: sheet.update_cell(fila_num, 20, datos["estado_comision"])
            if "fecha_pago_comision" in datos: sheet.update_cell(fila_num, 21, datos["fecha_pago_comision"])

        # Recalcular ESTADO_GENERAL
        est_inst = sheet.cell(fila_num, 15).value
        est_sub = sheet.cell(fila_num, 13).value
        est_bo = sheet.cell(fila_num, 11).value

        if est_inst == "Instalado": estado_general = "INSTALADO"
        elif est_inst == "Frustrado": estado_general = "INST. FRUSTRADA"
        elif est_sub == "Subido": estado_general = "SUBIDO / EN RUTA"
        elif est_bo == "Contactado": estado_general = "VALIDADO BO"
        elif est_bo == "Rechazado": estado_general = "RECHAZADO BO"
        else: estado_general = "PENDIENTE BO"

        sheet.update_cell(fila_num, 10, estado_general)
        sheet.update_cell(fila_num, 17, ahora)

        return jsonify({"status": "success", "estado_general": estado_general})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ================= API ENDPOINTS: USUARIOS =================

@app.route("/api/usuarios", methods=["GET"])
@login_required
@role_required(["ADMIN"])
def api_obtener_usuarios():
    try:
        u_sheet = get_usuarios_sheet()
        usuarios = u_sheet.get_all_records()
        for u in usuarios: u["PASSWORD"] = "••••••"
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
        if "password" in datos and datos["password"].strip(): u_sheet.update_cell(fila, 4, datos["password"].strip())
        if "rol" in datos: u_sheet.update_cell(fila, 5, datos["rol"].strip().upper())
        if "estado" in datos: u_sheet.update_cell(fila, 6, datos["estado"].strip())

        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)