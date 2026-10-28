@echo off
REM Start the HD520 companion REST server on localhost only.
cd /d %~dp0
py server.py
