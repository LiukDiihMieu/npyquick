from __future__ import annotations

import argparse
import sys

from PySide6.QtWidgets import QApplication

from npyquick.viewer import MainWindow


def main() -> None:
    parser = argparse.ArgumentParser(description="npyquick — quick 2D grayscale .npy viewer")
    parser.add_argument("file", nargs="?", help="Path to a .npy file to open on launch")
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
