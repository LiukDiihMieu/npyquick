"""MainWindow wiring for complex arrays: tab enabling + the tab-contextual
component selector in the top bar."""
from __future__ import annotations

import numpy as np

from npyquick.core import complexproj


def _enabled(mw):
    return {v.VIEW_ID for i, v in enumerate(mw._views) if mw._tabs.isTabEnabled(i)}


def _tab_index(mw, view_id):
    return next(i for i, v in enumerate(mw._views) if v.VIEW_ID == view_id)


def _complex2d(h=8, w=8):
    re = np.linspace(-1, 1, h * w).reshape(h, w)
    im = np.linspace(0, 2, h * w).reshape(h, w)
    return (re + 1j * im).astype(np.complex128)


def test_complex_2d_enables_image_histogram_table(main_window, write_npy):
    main_window.load_file(write_npy(_complex2d()))
    en = _enabled(main_window)
    assert {"image", "histogram", "table"} <= en
    assert "lineplot" not in en
    assert main_window._stack.currentWidget() is main_window._image_view


def test_component_combo_is_tab_contextual(main_window, write_npy):
    main_window.load_file(write_npy(_complex2d()))
    # Image tab → pair options.
    assert main_window._component_combo.isVisible()
    pairs = [main_window._component_combo.itemText(i)
             for i in range(main_window._component_combo.count())]
    assert pairs == list(complexproj.IMAGE_PAIRS)

    # Switch to Histogram tab → four single components.
    main_window._tabs.setCurrentIndex(_tab_index(main_window, "histogram"))
    comps = [main_window._component_combo.itemText(i)
             for i in range(main_window._component_combo.count())]
    assert comps == complexproj.component_names()


def test_real_array_hides_component_selector(main_window, write_npy):
    main_window.load_file(write_npy(np.zeros((8, 8), dtype=np.float32)))
    assert not main_window._component_combo.isVisible()
    assert main_window._array_bar.isHidden()


def test_selecting_pair_reprojects_image_panels(main_window, write_npy):
    main_window.load_file(write_npy(_complex2d()))
    assert main_window._stack.currentWidget() is main_window._image_view
    assert (main_window._image_view._comp_a, main_window._image_view._comp_b) == ("Real", "Imag")

    idx = list(complexproj.IMAGE_PAIRS).index("Abs / Angle")
    main_window._on_component_selected(idx)  # mirrors the activated signal
    assert main_window._image_pair == "Abs / Angle"
    assert (main_window._image_view._comp_a, main_window._image_view._comp_b) == ("Abs", "Angle")


def test_complex_1d_table_and_histogram_only(main_window, write_npy):
    arr = np.array([1 + 2j, 3 + 4j, 5 + 6j, 7 + 8j], dtype=np.complex128)
    main_window.load_file(write_npy(arr))
    en = _enabled(main_window)
    assert "histogram" in en and "table" in en
    assert "image" not in en and "lineplot" not in en


def test_histogram_component_persists_across_files(main_window, write_npy):
    main_window.load_file(write_npy(_complex2d()))
    main_window._tabs.setCurrentIndex(_tab_index(main_window, "histogram"))
    main_window._on_component_selected(complexproj.component_names().index("Angle"))
    assert main_window._hist_component == "Angle"
    assert main_window._histogram_view._component == "Angle"
