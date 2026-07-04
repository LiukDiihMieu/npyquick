"""Tests for the drop-target overlay shown while a valid drag hovers."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent
from PySide6.QtWidgets import QApplication


def _mime_for(*paths: str) -> QMimeData:
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
    return mime


def _drag_enter(window, mime: QMimeData) -> None:
    ev = QDragEnterEvent(
        QPoint(50, 50), Qt.DropAction.CopyAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(window, ev)


def test_overlay_hidden_at_startup(main_window):
    assert main_window._drop_overlay.isHidden()


def test_valid_drag_shows_overlay(main_window, write_npy):
    path = write_npy(np.zeros((4, 4), dtype=np.float32))
    _drag_enter(main_window, _mime_for(path))
    assert not main_window._drop_overlay.isHidden()


def test_drag_leave_hides_overlay(main_window, write_npy):
    path = write_npy(np.zeros((4, 4), dtype=np.float32))
    _drag_enter(main_window, _mime_for(path))
    QApplication.sendEvent(main_window, QDragLeaveEvent())
    assert main_window._drop_overlay.isHidden()


def test_invalid_drag_keeps_overlay_hidden(main_window, tmp_path):
    txt = tmp_path / "notes.txt"
    txt.write_text("not an array")
    _drag_enter(main_window, _mime_for(str(txt)))
    assert main_window._drop_overlay.isHidden()


def test_drop_hides_overlay_and_loads(main_window, write_npy):
    path = write_npy(np.zeros((4, 4), dtype=np.float32))
    mime = _mime_for(path)
    _drag_enter(main_window, mime)
    drop = QDropEvent(
        QPointF(50, 50), Qt.DropAction.CopyAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(main_window, drop)
    assert main_window._drop_overlay.isHidden()
    assert main_window._has_data()


def test_overlay_tracks_container_resize(main_window, write_npy):
    path = write_npy(np.zeros((4, 4), dtype=np.float32))
    _drag_enter(main_window, _mime_for(path))
    container = main_window.centralWidget()
    main_window.resize(900, 500)
    QApplication.processEvents()
    assert main_window._drop_overlay.size() == container.size()
