# Double-click to open Galley (needs Python with PySide6 and python-docx installed).
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from galley.gui.app import main

sys.exit(main())
