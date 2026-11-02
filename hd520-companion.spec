# PyInstaller build spec for the HD520 companion desktop app.
#
# Onedir build, not onefile: the exe plus its supporting files live
# together in dist/HD520Companion/. Onedir was chosen after the
# onefile build failed to serve on the desktop (2026-11-02): there
# is no extraction step, and the bundled files are visible in the
# folder, so a missing file is obvious instead of silent.
#
# Build ON the Windows desktop: `py -m PyInstaller hd520-companion.spec`
# (or run build.bat). PyInstaller does not cross-compile, so this spec
# produces a Windows exe only when run on Windows.
#
# Data files mirror the source tree layout, because server.py and
# engine/core.py locate ui/index.html and tools_data.json relative
# to their own files.

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
    [],
    exclude_binaries=True,
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

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='HD520Companion',
)
