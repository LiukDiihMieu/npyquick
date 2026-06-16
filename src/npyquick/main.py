# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 LiukDiihMieu

from __future__ import annotations

import argparse
import sys

from PySide6.QtWidgets import QApplication

from npyquick import __version__
from npyquick.app import MainWindow


def main() -> None:
    parser = argparse.ArgumentParser(
        description="npyquick — a fast, lightweight viewer for NumPy arrays (.npy / .npz)"
    )
    parser.add_argument(
        "-v", "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--install-desktop", action="store_true",
        help="Register npyquick as a .npy / .npz file handler (Linux only)",
    )
    parser.add_argument(
        "--uninstall-desktop", action="store_true",
        help="Remove the .npy / .npz desktop integration (Linux only)",
    )
    parser.add_argument(
        "file", nargs="?", help="Path to a .npy or .npz file to open on launch"
    )
    args, qt_argv = parser.parse_known_args()

    if args.install_desktop or args.uninstall_desktop:
        if sys.platform != "linux":
            print("Desktop integration is only supported on Linux.", file=sys.stderr)
            sys.exit(1)
        from npyquick.desktop import install, uninstall
        print(uninstall() if args.uninstall_desktop else install())
        sys.exit(0)

    app = QApplication([sys.argv[0]] + qt_argv)
    app.setApplicationName("npyquick")
    # Pair the window with our desktop file so compositors show the right
    # taskbar/dock icon. Must match the installed <id>.desktop basename.
    app.setDesktopFileName("io.github.liukdiihmieu.npyquick")

    window = MainWindow()
    window.show()

    if args.file:
        window.load_file(args.file)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
