@echo off
REM Build the HD520 companion standalone Windows exe.
REM Run this ONCE on the Windows desktop, from this folder.
REM Requires Python 3.11+ on that machine. Produces dist\HD520Companion.exe.
cd /d %~dp0
py -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
  echo Installing PyInstaller (build tool only, not part of the app)...
  py -m pip install pyinstaller
  if errorlevel 1 (
    echo Failed to install PyInstaller. Check Python and network, then retry.
    exit /b 1
  )
)
py -m PyInstaller hd520-companion.spec
if errorlevel 1 (
  echo Build failed. See the output above.
  exit /b 1
)
echo.
echo Built: dist\HD520Companion.exe
echo Double-click it to run. First launch may show a Windows SmartScreen
echo warning because the exe is unsigned: choose More info, then Run anyway.
