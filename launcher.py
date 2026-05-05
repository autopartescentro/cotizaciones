import os
import subprocess
import sys
import time
import webbrowser

APP_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(APP_DIR)

url = "http://localhost:8501"

cmd = ["python", "-m", "streamlit", "run", "app.py", "--server.address", "0.0.0.0"]
try:
    proc = subprocess.Popen(cmd, cwd=APP_DIR)
    time.sleep(3)
    webbrowser.open(url)
    proc.wait()
except FileNotFoundError:
    input("No se encontró Python. Instalá Python y probá de nuevo. Presioná Enter para cerrar...")
except Exception as e:
    input(f"Error al iniciar la app: {e}\nPresioná Enter para cerrar...")
