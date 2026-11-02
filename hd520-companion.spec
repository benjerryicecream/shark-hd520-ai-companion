# PyInstaller build spec for the HD520 companion desktop app.
#
# Build ON the Windows desktop: `py -m PyInstaller hd520-companion.spec`
# (or run build.bat). PyInstaller does not cross-compile, so this spec
# produces a Windows exe only when run on Windows.
#
# Output: dist/HD520Companion.exe, one file, no console window.
#
# Data files mirror the source tree layout, because server.py and
# engine/core.py locate ui/index.html and tools_data.json relative
# to their own files, which under onefile resolve inside the
# extraction dir. Python sources need no datas entry: PyInstaller
# collects them as modules automatically.

a = Analysis(
    ['desktop.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('ui/index.html', 'ui'),
        ('engine/tools_data.json', 'engine'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='HD520Companion',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
