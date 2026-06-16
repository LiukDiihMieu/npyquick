"""Version resolution must not crash when running from a source checkout.

Regression for #14: __version__ / --version used importlib.metadata.version()
directly, which raises PackageNotFoundError when no installed distribution
metadata is present (e.g. PYTHONPATH=src with no install).
"""
from __future__ import annotations

from importlib.metadata import PackageNotFoundError

import npyquick


def test_version_is_nonempty_string():
    assert isinstance(npyquick.__version__, str)
    assert npyquick.__version__


def test_resolve_version_falls_back_to_unknown(monkeypatch):
    def _raise(_name):
        raise PackageNotFoundError("npyquick")

    monkeypatch.setattr(npyquick, "version", _raise)
    assert npyquick._resolve_version() == "unknown"


def test_resolve_version_returns_metadata(monkeypatch):
    monkeypatch.setattr(npyquick, "version", lambda _name: "9.9.9")
    assert npyquick._resolve_version() == "9.9.9"
