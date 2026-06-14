# SPDX-License-Identifier: GPL-3.0-or-later
"""PyInstaller entry point: defer to the installed npyquick CLI."""
from npyquick.main import main

if __name__ == "__main__":
    main()
