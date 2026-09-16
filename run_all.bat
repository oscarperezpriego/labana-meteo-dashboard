@echo off
REM Se ejecuta desde el Programador de tareas de Windows cada 30 min.
REM Sincroniza los datos del logger, regenera el dashboard y lo publica en GitHub Pages.

cd /d %~dp0
call venv\Scripts\activate.bat

python src\sync_campbell.py >> data\sync.log 2>&1
python src\build_dashboard.py >> data\sync.log 2>&1

git add docs
git commit -m "Actualizar dashboard %date% %time%" >> data\sync.log 2>&1
git push >> data\sync.log 2>&1
