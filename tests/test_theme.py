from __future__ import annotations

import matplotlib as mpl
import numpy as np
from PySide6.QtCore import QEvent
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from npyquick.app import _apply_canvas_theme
from npyquick.views.base import CautionLabel, ErrorLabel

_WINDOW_TEXT = QPalette.ColorRole.WindowText


def _text_color(label) -> str:
    return label.palette().color(_WINDOW_TEXT).name()


def test_apply_canvas_theme_noop_when_not_dark(qapp):
    # Offscreen reports ColorScheme.Unknown, so the canvas must stay default.
    before = mpl.rcParams["figure.facecolor"]
    _apply_canvas_theme()
    assert mpl.rcParams["figure.facecolor"] == before


# ---------------------------------------------------------------------------
# Warning/anomaly labels: shared classes that re-resolve their WindowText
# palette color when a theme switch delivers a PaletteChange. Offscreen reports
# ColorScheme.Unknown and cannot flip it, so the dark side is exercised by
# patching the scheme check and delivering the event by hand.
# ---------------------------------------------------------------------------

def test_labels_resolve_to_light_colors_by_default(qapp):
    assert _text_color(ErrorLabel()) == "#b00020"
    assert _text_color(CautionLabel()) == "#b8860b"


def test_labels_recolor_on_palette_change_when_scheme_turns_dark(qapp, monkeypatch):
    error = ErrorLabel()
    caution = CautionLabel()
    assert _text_color(error) == "#b00020"
    monkeypatch.setattr("npyquick.views.base._is_dark_scheme", lambda: True)
    for label in (error, caution):
        QApplication.sendEvent(label, QEvent(QEvent.Type.PaletteChange))
    assert _text_color(error) == "#ff6b6b"
    assert _text_color(caution) == "#e5b567"


def test_all_views_use_the_shared_label_classes(qapp):
    # Guards against call sites drifting back to per-file hardcoded colors.
    from npyquick.views.histogram import HistogramView
    from npyquick.views.image import ImageView
    from npyquick.views.lineplot import LineplotView
    from npyquick.views.pixel_size_dialog import PixelSizeDialog
    from npyquick.views.table import RawTableView

    image = ImageView()
    hist = HistogramView()
    line = LineplotView()
    table = RawTableView()
    dialog = PixelSizeDialog("1", "px")

    assert isinstance(image._anomaly_label, ErrorLabel)
    assert isinstance(image._downsample_label, CautionLabel)
    assert isinstance(hist._anomaly_label, ErrorLabel)
    assert isinstance(hist._sample_label, CautionLabel)
    assert isinstance(line._anomaly_label, ErrorLabel)
    assert isinstance(line._sample_label, CautionLabel)
    assert isinstance(table._trunc_label, CautionLabel)
    assert isinstance(dialog._error_label, ErrorLabel)


def test_anomaly_label_shows_text_with_themed_color(qapp):
    from npyquick.views.histogram import HistogramView

    v = HistogramView()
    v.set_data(np.array([1.0, np.nan, 2.0], dtype=np.float32))
    assert not v._anomaly_label.isHidden()
    assert _text_color(v._anomaly_label) == "#b00020"
