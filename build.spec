# -*- mode: python ; coding: utf-8 -*-
"""
Спецификация PyInstaller для сборки CS2 Clone (Ursina + Panda3D + glTF) в один .exe файл.
Запуск сборки на Windows / Linux:
    pyinstaller --clean build.spec
"""

from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

project_root = Path(SPECPATH).resolve()

datas = [
    (str(project_root / "assets"), "assets"),
]
binaries = []
hiddenimports = [
    "ursina",
    "panda3d.core",
    "direct.actor.Actor",
    "gltf",
    "simplepbr",
    "pygame",
    "PIL",
    "numpy",
]

# Собираем встроенные меши (cube/quad/sphere), шейдеры, шрифты и рендер-плагины OpenGL/Audio
for pkg_name in ("ursina", "panda3d", "gltf", "simplepbr"):
    try:
        pkg_datas, pkg_bins, pkg_hidden = collect_all(pkg_name)
        datas.extend(pkg_datas)
        binaries.extend(pkg_bins)
        hiddenimports.extend(pkg_hidden)
    except Exception:
        pass

hiddenimports.extend(collect_submodules("src"))

a = Analysis(
    ["main.py"],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=list(dict.fromkeys(hiddenimports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy", "pytest"],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="cs2_clone",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Без чёрного консольного окна (--windowed)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
