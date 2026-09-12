# PyInstaller build spec. Run from the repository root:
#     pyinstaller packaging/galley.spec
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
APP_NAME = "Galley"

# Qt ships far more than this app uses; excluding the unused parts keeps the
# download to a reasonable size.
EXCLUDES = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQml", "PySide6.Qt3DCore",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtCharts",
    "PySide6.QtDataVisualization", "PySide6.QtBluetooth", "PySide6.QtNfc",
    "PySide6.QtPositioning", "PySide6.QtSerialPort", "PySide6.QtSql", "PySide6.QtTest",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtOpenGL", "PySide6.QtPdf",
    "matplotlib", "numpy", "pandas", "scipy", "tkinter", "PIL", "pytest",
]

a = Analysis(
    [str(ROOT / "packaging" / "launch.py")],
    pathex=[str(ROOT)],
    hiddenimports=["galley.parsers.docx_parser"],
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name=APP_NAME if sys.platform == "darwin" else "Galley",
    console=False,
    icon=str(ROOT / "packaging" / ("icon.icns" if sys.platform == "darwin" else "icon.ico")),
)
coll = COLLECT(exe, a.binaries, a.datas, name="Galley")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=str(ROOT / "packaging" / "icon.icns"),
        bundle_identifier="org.galley.app",
        info_plist={
            "CFBundleName": APP_NAME,
            "CFBundleDisplayName": APP_NAME,
            "CFBundleShortVersionString": "0.5.2",
            "NSHighResolutionCapable": True,
            "CFBundleDocumentTypes": [{
                "CFBundleTypeName": "Word document",
                "CFBundleTypeRole": "Viewer",
                "LSItemContentTypes": ["org.openxmlformats.wordprocessingml.document"],
            }],
        },
    )
