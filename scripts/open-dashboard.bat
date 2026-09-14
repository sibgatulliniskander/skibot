@echo off
rem Ouvre le dashboard : relance le serveur d'abord s'il ne repond pas.
cd /d "%~dp0.."
powershell -NoProfile -Command "try { Invoke-WebRequest -Uri 'http://127.0.0.1:5000' -UseBasicParsing -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }"
if errorlevel 1 (
  wscript.exe "%~dp0dashboard.vbs"
  timeout /t 4 /nobreak >nul
)
start "" http://127.0.0.1:5000/interne
