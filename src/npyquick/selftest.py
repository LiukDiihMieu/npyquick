# SPDX-License-Identifier: GPL-3.0-or-later
"""``npyquick --self-test``: check that this installation actually works.

The unit tests run against the source tree, so they cannot see a broken
package: a resource left out of the bundle, a missing Qt plugin, a matplotlib
backend that was not collected (issue #33). This runs inside whatever was
installed (the AppImage, the Snap, the Windows .exe, a pip install) and drives
the real code: build the main window, load files, export every plot in every
format. The packaging CI runs it after each build, and a user can run it when
reporting a problem.

It shows no window and puts the user's settings back as they were.
"""

from __future__ import annotations

import platform
import sys
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import matplotlib
import numpy as np
import PySide6
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from . import __version__
from .app import MainWindow
from .views.base import ExportableMixin

EXPORT_FORMATS = ("png", "svg", "pdf")


class CheckFailed(Exception):
    """A check found something wrong; the message says what."""


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise CheckFailed(message)


# ----------------------------------------------------------------------
# Checks. They run in order and share one window, like a user session;
# each raises on failure.
# ----------------------------------------------------------------------

def check_window_icon(window: MainWindow, workdir: Path) -> None:
    sizes = {size.width() for size in QApplication.windowIcon().availableSizes()}
    missing = {16, 256} - sizes
    _expect(not missing, f"window icon lacks sizes {sorted(missing)}; it has {sorted(sizes)}")


def check_load_npy(window: MainWindow, workdir: Path) -> None:
    path = workdir / "image.npy"
    np.save(path, _sample_image())
    _expect(window.load_file(str(path)), "load_file() reported failure")
    _expect(window._has_data(), "no array is loaded after load_file()")


def check_export_formats(window: MainWindow, workdir: Path) -> None:
    canvases = [w for w in window.findChildren(QWidget) if isinstance(w, ExportableMixin)]
    _expect(bool(canvases), "the window has no exportable plot")
    for index, canvas in enumerate(canvases):
        for fmt in EXPORT_FORMATS:
            target = workdir / f"plot{index}.{fmt}"
            canvas.figure.savefig(target, format=fmt)
            _expect(target.stat().st_size > 0, f"exporting {canvas.panel_name} as {fmt} wrote an empty file")


def check_load_npz(window: MainWindow, workdir: Path) -> None:
    path = workdir / "archive.npz"
    np.savez(path, image=_sample_image(), signal=np.sin(np.linspace(0, 6, 200)))
    _expect(window.load_file(str(path)), "load_file() reported failure")

    # Pick a member the way a user does: through the dropdown.
    index = window._array_combo.findData("signal")
    _expect(index >= 0, "member 'signal' is missing from the array picker")
    window._array_combo.activated.emit(index)
    _expect(window._model.selected_key == "signal", "picking a member did not load it")

    shown = window._views[window._tabs.currentIndex()].VIEW_ID
    _expect(shown == "lineplot", f"a 1-D member opened in the '{shown}' view, not the line plot")


CHECKS: list[tuple[str, Callable[[MainWindow, Path], None]]] = [
    ("window icon", check_window_icon),
    ("load a .npy file", check_load_npy),
    ("export plots as " + ", ".join(EXPORT_FORMATS), check_export_formats),
    ("load a .npz archive and pick a member", check_load_npz),
]


def _sample_image() -> np.ndarray:
    y, x = np.mgrid[0:48, 0:64]
    return np.hypot(x - 32, y - 24).astype(np.float32)


# ----------------------------------------------------------------------
# Keeping the run harmless and unattended
# ----------------------------------------------------------------------

@contextmanager
def _settings_restored() -> Iterator[None]:
    """Put the user's settings back afterwards.

    Loading a file records it under Open Recent and as the last-used folder;
    the temporary files this run opens must not linger there.
    """
    store = QSettings("npyquick", "npyquick")
    saved = {key: store.value(key) for key in store.allKeys()}
    try:
        yield
    finally:
        store.clear()
        for key, value in saved.items():
            store.setValue(key, value)


@contextmanager
def _dialogs_become_failures() -> Iterator[None]:
    """Turn an error dialog into a failed check.

    The application reports load and export errors in a modal dialog. With no
    one there to dismiss it the run would hang, so raise its text instead.
    """
    def fail(parent, title, text, *args, **kwargs):
        raise CheckFailed(f"{title}: {text}")

    originals = QMessageBox.warning, QMessageBox.critical
    QMessageBox.warning = QMessageBox.critical = fail
    try:
        yield
    finally:
        QMessageBox.warning, QMessageBox.critical = originals


# ----------------------------------------------------------------------

def _environment() -> str:
    packaged = "yes" if getattr(sys, "frozen", False) else "no"
    return (
        f"npyquick {__version__} self-test\n"
        f"  Python {platform.python_version()}, PySide6 {PySide6.__version__}, "
        f"numpy {np.__version__}, matplotlib {matplotlib.__version__}\n"
        f"  {platform.platform()}, Qt platform: {QApplication.platformName()}, packaged: {packaged}"
    )


def run(report_path: str = "") -> int:
    """Run every check; return 0 if all passed, 1 otherwise.

    The report goes to stdout, and to ``report_path`` when given. The Windows
    build has no console, so there the file is the only way to read it.
    Needs an existing QApplication.
    """
    lines = [_environment()]
    failures = 0

    with tempfile.TemporaryDirectory(prefix="npyquick-selftest-", ignore_cleanup_errors=True) as tmp, \
            _settings_restored(), _dialogs_become_failures():
        window = MainWindow()
        for name, check in CHECKS:
            try:
                check(window, Path(tmp))
            except Exception as exc:
                failures += 1
                lines.append(f"  FAIL  {name}: {type(exc).__name__}: {exc}")
            else:
                lines.append(f"  ok    {name}")
        window.close()

    passed = len(CHECKS) - failures
    lines.append(f"Result: {passed} passed, {failures} failed")

    report = "\n".join(lines) + "\n"
    print(report, end="")
    if report_path:
        Path(report_path).write_text(report, encoding="utf-8")
    return 1 if failures else 0
