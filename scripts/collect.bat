@echo off
rem Lance la collecte skibot (utilisé par la tâche planifiée Windows)
cd /d "%~dp0.."
".venv\Scripts\skibot.exe" collect >> "data\collect.log" 2>&1
