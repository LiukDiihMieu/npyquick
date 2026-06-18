from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QApplication


# Redirect QStandardPaths (and therefore QSettings) into Qt's test sandbox
# before anything constructs a QSettings instance. closeEvent saves geometry,
# load_file saves last_dir, and export_figure saves last_export_dir — every
# test using `main_window` or load_file would otherwise rewrite the developer's
# persistent ~/.config/npyquick configuration. The redirect sends those writes
# to ~/.qttest/config/npyquick/ instead, leaving the real config untouched.
# Called at module load (before any fixture runs) so it applies to every test.
QStandardPaths.setTestModeEnabled(True)


@pytest.fixture(scope="session", autouse=True)
def qapp():
    app = QApplication.instance() or QApplication([sys.argv[0]])
    yield app


@pytest.fixture
def main_window():
    """A fresh MainWindow, shown (focus-based tests require an active window)
    and closed at teardown."""
    from npyquick.app import MainWindow
    w = MainWindow()
    w.show()
    yield w
    w.close()


@pytest.fixture
def write_npy(tmp_path):
    """Factory that writes a .npy into tmp_path and returns its absolute path."""
    def _write(array, name: str = "test.npy") -> str:
        p = tmp_path / name
        np.save(str(p), array)
        return str(p)
    return _write


@pytest.fixture
def write_npz(tmp_path):
    """Factory that writes a .npz into tmp_path and returns its absolute path."""
    def _write(name: str = "test.npz", **arrays) -> str:
        p = tmp_path / name
        np.savez(str(p), **arrays)
        return str(p)
    return _write
