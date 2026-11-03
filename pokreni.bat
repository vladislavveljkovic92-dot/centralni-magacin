@echo off
title Magacin - Centralna Evidencija
cd /d "%~dp0"

echo ===================================================
echo     POKRETANJE APLIKACIJE MAGACIN
echo     Baza: Supabase PostgreSQL (Live deljena baza)
echo ===================================================
echo.
echo Otvaram aplikaciju u vasem pretrazivacu...
echo Za zaustavljanje pritisnite Ctrl+C ili zatvorite ovaj prozor.
echo.

timeout /t 2 /nobreak >nul
start "" http://localhost:8501
.venv\Scripts\python.exe -m streamlit run streamlit_app.py --server.address=127.0.0.1 --server.port=8501
pause
