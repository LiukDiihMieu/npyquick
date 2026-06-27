"""export_figure must save the format the user picked, not just whatever the
save dialog put in the path.

We don't rely on setDefaultSuffix / filterSelected to append the extension:
filterSelected doesn't fire in every environment (e.g. the save dialog under
Snap), so the re-synced suffix went stale and picking SVG/PDF still saved a .png
(issue #33). Instead the format is resolved from the reliable selectedNameFilter
and we append the extension ourselves. These tests drive the post-dialog
resolution by faking the dialog's result and asserting the path/format handed to
savefig.
"""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QFileDialog, QMessageBox

from npyquick.views.histogram import HistogramCanvas


@pytest.fixture
def canvas():
    c = HistogramCanvas()
    yield c
    c.deleteLater()


def _drive_export(canvas, monkeypatch, *, returned_path, selected_filter):
    """Run export_figure with the save dialog stubbed to a fixed outcome and
    return (path, kwargs) passed to figure.savefig."""
    monkeypatch.setattr(QFileDialog, "exec", lambda self: 1)
    monkeypatch.setattr(QFileDialog, "selectedFiles", lambda self: [returned_path])
    monkeypatch.setattr(QFileDialog, "selectedNameFilter", lambda self: selected_filter)

    captured = {}

    def fake_savefig(path, **kwargs):
        captured["path"] = path
        captured["kwargs"] = kwargs

    monkeypatch.setattr(canvas.figure, "savefig", fake_savefig)
    canvas.export_figure()
    return captured["path"], captured["kwargs"]


@pytest.mark.parametrize("filt,ext", [
    ("PNG (*.png)", "png"),
    ("SVG (*.svg)", "svg"),
    ("PDF (*.pdf)", "pdf"),
])
def test_extensionless_path_gets_filter_format(canvas, monkeypatch, tmp_path, filt, ext):
    # Dialog returned a name with no suffix (no setDefaultSuffix): append the
    # chosen filter's extension and save in that format.
    base = str(tmp_path / "Histogram")
    path, kwargs = _drive_export(canvas, monkeypatch, returned_path=base, selected_filter=filt)
    assert path == f"{base}.{ext}"
    assert kwargs["format"] == ext


@pytest.mark.parametrize("ext", ["png", "svg", "pdf"])
def test_native_suffix_preserved(canvas, monkeypatch, tmp_path, ext):
    # Native dialog already appended the suffix: keep the path, format follows it.
    p = str(tmp_path / f"Histogram.{ext}")
    path, kwargs = _drive_export(canvas, monkeypatch, returned_path=p, selected_filter="PNG (*.png)")
    assert path == p
    assert kwargs["format"] == ext


def test_typed_extension_wins_over_filter(canvas, monkeypatch, tmp_path):
    # A user-typed recognized extension is respected over the selected filter.
    p = str(tmp_path / "Histogram.pdf")
    path, kwargs = _drive_export(canvas, monkeypatch, returned_path=p, selected_filter="PNG (*.png)")
    assert path == p
    assert kwargs["format"] == "pdf"


def test_unreported_filter_falls_back_to_default(canvas, monkeypatch, tmp_path):
    # Some environments report no selected filter (''). With no typed extension,
    # fall back to the first/default filter (PNG) rather than emitting format=None.
    base = str(tmp_path / "Histogram")
    path, kwargs = _drive_export(canvas, monkeypatch, returned_path=base, selected_filter="")
    assert path == f"{base}.png"
    assert kwargs["format"] == "png"


def test_export_save_failure_warns_and_does_not_raise(canvas, monkeypatch, tmp_path):
    """A savefig error (full disk, no permission) must surface a dialog instead
    of escaping the Qt slot or silently 'succeeding'."""
    monkeypatch.setattr(QFileDialog, "exec", lambda self: 1)
    monkeypatch.setattr(
        QFileDialog, "selectedFiles", lambda self: [str(tmp_path / "Histogram.png")]
    )
    monkeypatch.setattr(QFileDialog, "selectedNameFilter", lambda self: "PNG (*.png)")

    def boom(*a, **k):
        raise OSError("No space left on device")

    monkeypatch.setattr(canvas.figure, "savefig", boom)

    seen = []
    monkeypatch.setattr(
        QMessageBox, "critical", lambda *a, **k: seen.append(a[2]) or QMessageBox.StandardButton.Ok
    )

    canvas.export_figure()  # must not raise
    assert any("No space left" in msg for msg in seen)


def test_copy_failure_warns_and_does_not_raise(canvas, monkeypatch):
    """A render error during copy must surface a dialog, not abort the slot."""
    def boom(*a, **k):
        raise RuntimeError("render exploded")

    monkeypatch.setattr(canvas.figure, "savefig", boom)

    seen = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *a, **k: seen.append(a[2]) or QMessageBox.StandardButton.Ok
    )

    canvas.copy_to_clipboard()  # must not raise
    assert any("render exploded" in msg for msg in seen)
