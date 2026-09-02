import os
from datetime import datetime
from flask import Flask, render_template, request, jsonify
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "credentials.json")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def get_sheet():
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID).sheet1

# ================= RUTAS DE VISTAS =================

@app.route("/")
def index():
    # Por defecto abre la vista de campo (móvil)
    return render_template("campo.html")

@app.route("/backoffice")
def backoffice_view():
    return render_template("backoffice.html")

# ================= API ENDPOINTS =================

@app.route("/api/ventas", methods=["GET"])
def obtener_ventas():
    try:
        sheet = get_sheet()
        registros = sheet.get_all_records()
        return jsonify({"status": "success", "data": registros})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/ventas", methods=["POST"])
def registrar_venta():
    try:
        datos = request.json
        sheet = get_sheet()
        
        # Generar ID único basado en timestamp
        ahora = datetime.now()
        id_venta = f"V-{ahora.strftime('%y%m%d%H%M%S')}"
        fecha_registro = ahora.strftime("%Y-%m-%d %H:%M")
        
        nueva_fila = [
            id_venta,
            fecha_registro,
            datos.get("asesor_campo", "").strip().upper(),
            datos.get("cliente_nombre", "").strip().title(),
            datos.get("cliente_dni", "").strip(),
            datos.get("cliente_telefono", "").strip(),
            datos.get("direccion", "").strip(),
            datos.get("plan_producto", "").strip(),
            datos.get("evidencia_drive", "").strip() or "N/A",
            "PENDIENTE BO",          # ESTADO_GENERAL inicial
            "Pendiente",             # ESTADO_BO inicial
            "",                      # FECHA_CONTACTO_BO
            "Pendiente",             # ESTADO_SUBIDA inicial
            "",                      # FECHA_INSTALACION
            "Pendiente",             # ESTADO_INSTALACION inicial
            datos.get("observaciones", "").strip(),
            fecha_registro           # ULTIMA_ACTUALIZACION
        ]
        
        sheet.append_row(nueva_fila)
        return jsonify({"status": "success", "id_venta": id_venta})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/ventas/<id_venta>", methods=["PATCH"])
def actualizar_estado(id_venta):
    try:
        datos = request.json
        sheet = get_sheet()
        
        # Buscar la fila correspondiente al ID_VENTA
        celda = sheet.find(id_venta)
        if not celda:
            return jsonify({"status": "error", "message": "Venta no encontrada"}), 404
        
        fila_num = celda.row
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # Mapeo de columnas según encabezados:
        # J=10 (ESTADO_GENERAL), K=11 (ESTADO_BO), L=12 (FECHA_CONTACTO_BO),
        # M=13 (ESTADO_SUBIDA), N=14 (FECHA_INSTALACION), O=15 (ESTADO_INSTALACION),
        # P=16 (OBSERVACIONES), Q=17 (ULTIMA_ACTUALIZACION)
        
        if "estado_bo" in datos:
            sheet.update_cell(fila_num, 11, datos["estado_bo"])
            if datos["estado_bo"] == "Contactado":
                sheet.update_cell(fila_num, 12, ahora)
                
        if "estado_subida" in datos:
            sheet.update_cell(fila_num, 13, datos["estado_subida"])
            
        if "estado_instalacion" in datos:
            sheet.update_cell(fila_num, 15, datos["estado_instalacion"])
            
        if "fecha_instalacion" in datos:
            sheet.update_cell(fila_num, 14, datos["fecha_instalacion"])
            
        if "observaciones" in datos:
            sheet.update_cell(fila_num, 16, datos["observaciones"])
            
        # Calcular Estado General Automático
        est_inst = datos.get("estado_instalacion") or sheet.cell(fila_num, 15).value
        est_sub = datos.get("estado_subida") or sheet.cell(fila_num, 13).value
        est_bo = datos.get("estado_bo") or sheet.cell(fila_num, 11).value
        
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

if __name__ == "__main__":
    # Host 0.0.0.0 permite acceder desde el celular si están en la misma red Wi-Fi
    app.run(host="0.0.0.0", port=5000, debug=True)