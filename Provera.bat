@echo off
chcp 65001 >nul
title Provera sistema magacin
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0provera.ps1"
echo.
echo Gotovo. Pritisni bilo koji taster da zatvoris prozor.
pause >nul
