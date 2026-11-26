@echo off
chcp 65001 >nul
title Instalacija magacina
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instaliraj.ps1"
echo.
echo Gotovo. Pritisni bilo koji taster da zatvoris prozor.
pause >nul
