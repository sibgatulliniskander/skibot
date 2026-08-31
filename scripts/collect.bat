@echo off
rem Lance la collecte + extraction skibot (utilise par la tache planifiee Windows)
cd /d "%~dp0.."
".venv\Scripts\skibot.exe" collect >> "data\collect.log" 2>&1
".venv\Scripts\skibot.exe" features >> "data\collect.log" 2>&1
