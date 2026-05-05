@echo off
cd /d "%~dp0"
echo Instalando PyInstaller...
python -m pip install --upgrade pip
python -m pip install pyinstaller

echo Creando EXE...
python -m PyInstaller --onefile --name "IA Vidrios Autopartes Centro" launcher.py

echo.
echo LISTO.
echo Tu EXE queda en la carpeta: dist
echo Archivo: IA Vidrios Autopartes Centro.exe
echo.
pause
