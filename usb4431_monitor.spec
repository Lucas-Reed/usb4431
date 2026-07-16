# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules, copy_metadata


hiddenimports = collect_submodules("nidaqmx")
nidaqmx_metadata = copy_metadata("nidaqmx") + copy_metadata("nitypes")

a = Analysis(
    ["run_usb4431.py"],
    pathex=["src"],
    binaries=[],
    datas=[("src/usb4431_monitor/web", "usb4431_monitor/web"), *nidaqmx_metadata],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="USB4431-LongDrift",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="USB4431-LongDrift",
)
