import os
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

# Cargar las variables del archivo .env
load_dotenv()

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "credentials.json")

# Permisos para acceder a Sheets y Drive
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def probar_conexion():
    print("Conectando con Google Sheets...")
    try:
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
        client = gspread.authorize(creds)
        
        # Abrir la hoja por su ID
        sheet = client.open_by_key(SPREADSHEET_ID).sheet1
        
        # Leer la fila 1 (los encabezados que creaste)
        encabezados = sheet.row_values(1)
        
        print("\n ¡Conexión 100% exitosa!")
        print(f" Columnas detectadas ({len(encabezados)}):")
        for i, col in enumerate(encabezados, start=1):
            print(f"  {i}. {col}")
            
    except Exception as e:
        print(f"\n Error al conectar: {e}")

if __name__ == "__main__":
    probar_conexion()