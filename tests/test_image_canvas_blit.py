import io
from unittest.mock import Mock

import numpy as np
import pytest
from matplotlib.backend_bases import MouseEvent
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication

from npyquick.views.image import ImageCanvas, ImageView


def mouse(canvas, name, xy):
    x, y = canvas._ax.transData.transform(xy)
    canvas.callbacks.process(name, MouseEvent(name, canvas, x, y, button=1))


def assert_matches_full_render(canvas):
    # Saving includes the line and both markers in an ordinary full rendering.
    pixels = canvas.buffer_rgba().tobytes()
    out = io.BytesIO()
    canvas.figure.savefig(out, format="raw", dpi=canvas.figure.dpi)
    assert pixels == out.getvalue()


@pytest.mark.parametrize("complex_image", [False, True])
def test_endpoint_blit_matches_full_render_and_updates_profile(complex_image, qapp, monkeypatch):
    view = ImageView()
    data = np.arange(1024).reshape(32, 32)
    view.set_data(data + 2j * data if complex_image else data)
    view.resize(1000, 650)
    view.show()
    qapp.processEvents()
    view.set_on_canvas_selected(lambda _: None)
    panels = [view._canvas, view._canvas_b] if complex_image else [view._canvas]
    source = panels[-1]
    mouse(source, "button_press_event", source.get_endpoints()[0])
    mouse(source, "motion_notify_event", (5, 6))
    qapp.processEvents()
    for c in panels:
        monkeypatch.setattr(c, "blit", Mock(wraps=c.blit))
        monkeypatch.setattr(c, "draw", Mock(wraps=c.draw))

    for xy in ((12, 20), (17, 9)):
        mouse(source, "motion_notify_event", xy)
        qapp.processEvents()
    for c in panels:
        assert c.blit.call_count == 2
        c.draw.assert_not_called()
        np.testing.assert_array_equal(c.get_endpoints(), source.get_endpoints())
        assert_matches_full_render(c)
    np.testing.assert_array_equal(view._profile._lines[0].get_ydata(), source.profile_data()[1])

    mouse(source, "button_release_event", (17, 9))
    qapp.processEvents()
    for c in panels:
        assert c._drag_background is None
        assert not c._cs_line.get_animated()
        c.draw.assert_called()
    view.close()


@pytest.mark.parametrize("change", ["resize", "zoom", "clim"])
def test_background_rebuilt_after_view_changes_during_drag(change, qapp, monkeypatch):
    c = ImageCanvas()
    c.load(np.arange(1024).reshape(32, 32))
    mouse(c, "button_press_event", c.get_endpoints()[0])
    mouse(c, "motion_notify_event", (7, 10))
    qapp.processEvents()
    monkeypatch.setattr(c, "blit", Mock(wraps=c.blit))

    if change == "resize":
        c.figure.set_size_inches(7, 5)
    elif change == "zoom":
        c.set_view((2, 25), (25, 2))
    else:
        c.set_clim(100, 800)
    mouse(c, "motion_notify_event", (9, 12))
    c.blit.assert_not_called()  # A full redraw is still pending.
    qapp.processEvents()
    mouse(c, "motion_notify_event", (15, 20))
    c.blit.assert_called_once()
    assert_matches_full_render(c)
    QApplication.sendEvent(c, QEvent(QEvent.Type.WindowDeactivate))
    qapp.processEvents()
    assert c._drag_background is None
    assert not c._cs_line.get_animated()


def test_endpoint_drag_without_blit_support(qapp, monkeypatch):
    monkeypatch.setattr(ImageCanvas, "supports_blit", False)
    c = ImageCanvas()
    c.load(np.zeros((32, 32)))
    monkeypatch.setattr(c, "blit", Mock())
    mouse(c, "button_press_event", c.get_endpoints()[0])
    for xy in ((7, 10), (15, 20)):
        mouse(c, "motion_notify_event", xy)
        qapp.processEvents()
    c.blit.assert_not_called()
    assert not c._cs_line.get_animated()
    assert_matches_full_render(c)
