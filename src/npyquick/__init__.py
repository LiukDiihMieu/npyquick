# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 LiukDiihMieu

# Single source of truth for the version. The build backend (hatchling) reads
# this literal via [tool.hatch.version] in pyproject.toml, so the source tree
# and the built distribution always report the same version — and importing
# from a checkout never depends on installed package metadata.
__version__ = "0.1.4"
