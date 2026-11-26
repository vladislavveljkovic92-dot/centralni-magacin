@echo off
title Magacin - Centralna Evidencija
cd /d "c:\Users\v.veljkovic\Desktop\magacin"

echo ===================================================
echo     POKRETANJE APLIKACIJE MAGACIN
echo     Baza: Supabase PostgreSQL (Live deljena baza)
echo ===================================================
echo.
echo [1/2] Pravim backup baze na ovaj racunar (cuva poslednjih 10)...
".venv\Scripts\python.exe" backup_database.py --keep 10
if errorlevel 1 (
    echo     PAZNJA: backup nije napravljen - program se svejedno pokrece.
)
echo.
echo [2/2] Lokalna adresa (ovaj racunar): http://localhost:8501
echo Mrezna adresa (drugi racunari na istoj mrezi): http://10.9.103.64:8501
echo.
echo Otvaram aplikaciju u vasem pretrazivacu...
echo Za zaustavljanje pritisnite Ctrl+C ili zatvorite ovaj prozor.
echo.

start "" http://localhost:8501
.venv\Scripts\python.exe -m streamlit run streamlit_app.py --server.address=0.0.0.0 --server.port=8501
pause
