"""Test setup shared by the whole suite.

The GUI tests create a Qt application. On a machine with no display — a CI
runner, or a terminal over SSH — Qt aborts unless it is told to render
offscreen, so that is set here rather than being left to whoever runs pytest.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
