# PyInstaller build for Screenwriter.   uv run --group build pyinstaller packaging/screenwriter.spec
# Produces dist/Screenwriter/ (Windows, Linux) or dist/Screenwriter.app (macOS).
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).parent
VERSION = re.search(r'__version__ = "([^"]+)"', (ROOT / "screenwriter" / "__init__.py").read_text()).group(1)
ICON = str(ROOT / "screenwriter" / "resources" / "icon.png")  # converted to .icns/.ico by Pillow

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT)],
    datas=[
        (str(ROOT / "screenwriter" / "resources"), "screenwriter/resources"),
        (str(ROOT / "LICENSE"), "."),
    ] + collect_data_files("docx"),
    excludes=["tkinter", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtTest"],  # QtNetwork: Google sign-in
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Screenwriter",
    console=False,
    icon=ICON,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Screenwriter")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Screenwriter.app",
        icon=ICON,
        bundle_identifier="io.github.dntatme.screenwriter",
        version=VERSION,
        info_plist={
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
            "LSApplicationCategoryType": "public.app-category.productivity",
            "LSMinimumSystemVersion": "12.0",
        },
    )
