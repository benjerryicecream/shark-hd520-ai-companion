@echo off
REM Start the HD520 companion in desktop mode from source (no build needed).
REM Opens the UI in the default browser with the API token already filled in.
cd /d %~dp0
py desktop.py
