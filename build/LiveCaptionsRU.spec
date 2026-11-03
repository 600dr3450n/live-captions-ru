# -*- mode: python ; coding: utf-8 -*-
# Paths are relative to the project root, which is the directory above build/.
# SPECPATH is provided by PyInstaller; nothing here refers to a specific machine.
import os

from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))

datas = [
    (os.path.join(ROOT, 'models', 't-one'), 'models/t-one'),
    (os.path.join(ROOT, 'app', 'fonts'), 'fonts'),
    (os.path.join(ROOT, 'app', 'icon.ico'), '.'),
    (os.path.join(ROOT, 'app', 'icon_off.ico'), '.'),
]
binaries = []
hiddenimports = []
tmp_ret = collect_all('onnxruntime')
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]


a = Analysis(
    [os.path.join(ROOT, 'app', 'main.py')],
    pathex=[os.path.join(ROOT, 'app')],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PIL', 'onnx', 'yaml', 'psutil', 'ml_dtypes'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='LiveCaptionsRU',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ROOT, 'assets', 'icon.ico'),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='LiveCaptionsRU',
)
