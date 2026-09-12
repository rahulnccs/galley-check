"""Entry point used by PyInstaller for the bundled desktop app."""
import multiprocessing
import sys

from galley.gui.app import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
