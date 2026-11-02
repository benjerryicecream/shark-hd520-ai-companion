@echo off
REM Build the HD520 companion standalone Windows exe.
REM Run this ONCE on the Windows desktop, from this folder.
REM Requires Python 3.11+ on that machine. Produces dist\HD520Companion.exe.
REM Note: this script avoids parentheses inside IF blocks on purpose.
REM cmd treats a closing paren in a message line as the end of the block,
REM which broke an earlier version of this file.
cd /d %~dp0
py -m PyInstaller --version >nul 2>&1
if not errorlevel 1 goto have_pyinstaller
echo Installing PyInstaller, the build tool only. It is not part of the app.
py -m pip install pyinstaller
if errorlevel 1 goto pip_failed
:have_pyinstaller
py -m PyInstaller hd520-companion.spec
if errorlevel 1 goto build_failed
echo.
echo Built: dist\HD520Companion\HD520Companion.exe
echo Double-click dist\HD520Companion\HD520Companion.exe to run.
echo Keep the whole dist\HD520Companion folder together. The exe needs
echo the files beside it. First launch may show a Windows SmartScreen
echo warning because the exe is unsigned. Choose More info, then Run anyway.
pause
goto :eof
:pip_failed
echo Failed to install PyInstaller. Check Python and network, then retry.
pause
exit /b 1
:build_failed
echo Build failed. See the output above.
pause
exit /b 1
