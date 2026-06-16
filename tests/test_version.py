"""Version is a single source of truth and works from a source checkout.

Regression for #14: __version__ / --version used to read installed package
metadata, which raised PackageNotFoundError when running from a source tree
with no installed distribution. The version is now a literal in
npyquick/__init__.py (hatchling reads it at build time), so importing from a
checkout never touches package metadata.
"""
from __future__ import annotations

import re

import npyquick


def test_version_is_semver_like_string():
    assert isinstance(npyquick.__version__, str)
    assert re.fullmatch(r"\d+\.\d+\.\d+\S*", npyquick.__version__), npyquick.__version__


def test_version_independent_of_installed_metadata(monkeypatch):
    # Even with no installed metadata, __version__ is the in-source literal.
    import importlib.metadata as im

    def _raise(_name):
        raise im.PackageNotFoundError("npyquick")

    monkeypatch.setattr(im, "version", _raise)
    import importlib
    mod = importlib.reload(npyquick)
    assert mod.__version__ and "unknown" not in mod.__version__
