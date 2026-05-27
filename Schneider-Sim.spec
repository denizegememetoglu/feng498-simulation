# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the Schneider-Sim launcher (M7).
#
# Build:   pyinstaller Schneider-Sim.spec
# Run:     dist/Schneider-Sim/Schneider-Sim
#
# Directory mode (NOT onefile) so the bundled assets (web/, output/, config/,
# Reports/) stay readable on disk. This keeps the bundle audit-friendly for
# the thesis defense and avoids cold-start extraction stalls.
from PyInstaller.utils.hooks import collect_data_files

DATAS = [
    ("web", "web"),
    ("config", "config"),
    # Bundle a snapshot of derived outputs so the first launch shows real KPIs
    # without requiring a Python pipeline rerun.
    ("output", "output"),
    # Keep V&V reports accessible from inside the bundle (read-only).
    ("Reports", "Reports"),
]

HIDDEN = [
    "webview",
    "webview.platforms.gtk",
    "webview.platforms.qt",
    "webview.platforms.cocoa",
]

a = Analysis(
    ["src/launcher.py"],
    pathex=["."],
    binaries=[],
    datas=DATAS,
    hiddenimports=HIDDEN,
    hookspath=[],
    excludes=["matplotlib.tests", "scipy.tests", "numpy.tests"],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz, a.scripts,
    [],
    exclude_binaries=True,
    name="Schneider-Sim",
    console=False,
    icon=None,
)

coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=False, name="Schneider-Sim",
)
