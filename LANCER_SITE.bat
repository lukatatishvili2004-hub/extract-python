@echo off
cd /d "%~dp0"
echo === PaieScan - lancement ===
python --version
if errorlevel 1 (
  echo Python non detecte. Installer Python avant de continuer.
  pause
  exit /b 1
)
echo Installation des dependances...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo Echec de l installation. Consulter le message ci-dessus.
  pause
  exit /b 1
)
echo Site disponible sur http://localhost:8501
python -m streamlit run app.py --server.address 127.0.0.1
pause
