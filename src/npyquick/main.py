# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 LiukDiihMieu

from __future__ import annotations

import argparse
import sys
from importlib.metadata import version

from PySide6.QtWidgets import QApplication

from npyquick.app import MainWindow


def main() -> None:
    parser = argparse.ArgumentParser(
        description="npyquick — a fast, lightweight viewer for NumPy arrays (.npy / .npz)"
    )
    parser.add_argument(
        "-v", "--version", action="version", version=f"%(prog)s {version('npyquick')}"
    )
    parser.add_argument(
        "file", nargs="?", help="Path to a .npy or .npz file to open on launch"
    )
    args, qt_argv = parser.parse_known_args()

    app = QApplication([sys.argv[0]] + qt_argv)
    app.setApplicationName("npyquick")

    window = MainWindow()
    window.show()

    if args.file:
        window.load_file(args.file)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
