# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for a windowed, one-folder build of edb-layout-viewer.
# Build with: packaging\build_exe.ps1

from PyInstaller.utils.hooks import collect_all, copy_metadata

# ansys packages read their own dist metadata at import time.
PACKAGES = (
    "edb_layout_viewer",
    "layout_viewer_core",
    "pyedb",
    "ansys.edb.core",
    "ansys.api.edb",
    "ansys.tools.common",
)
METADATA = ("ansys-edb-core", "ansys-tools-common", "pyedb")

datas, binaries, hiddenimports = [], [], []
for distribution in METADATA:
    datas += copy_metadata(distribution)
for package in PACKAGES:
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

a = Analysis(
    ["launcher.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "IPython", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="edb-layout-viewer",
    console=False,
    upx=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="edb-layout-viewer",
    upx=False,
)
