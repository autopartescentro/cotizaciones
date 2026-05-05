@echo off
set "APPDIR=%~dp0"
set "TARGET=%APPDIR%iniciar_app.bat"
set "SHORTCUT=%USERPROFILE%\Desktop\IA Vidrios Autopartes Centro.lnk"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -COM WScript.Shell).CreateShortcut('%SHORTCUT%'); $s.TargetPath='%TARGET%'; $s.WorkingDirectory='%APPDIR%'; $s.IconLocation='shell32.dll,137'; $s.Save()"
echo Icono creado en el escritorio.
pause
