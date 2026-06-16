# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 LiukDiihMieu

from importlib.metadata import PackageNotFoundError, version


def _resolve_version() -> str:
    # Running from a source checkout without installed metadata must not crash:
    # fall back to "unknown" when the distribution isn't installed.
    try:
        return version("npyquick")
    except PackageNotFoundError:
        return "unknown"


__version__ = _resolve_version()
