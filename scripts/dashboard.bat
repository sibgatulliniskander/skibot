@echo off
rem Lance le dashboard skibot (utilise au demarrage de session Windows)
cd /d "%~dp0.."
".venv\Scripts\skibot.exe" dashboard >> "data\dashboard.log" 2>&1
