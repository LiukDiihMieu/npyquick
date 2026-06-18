"""Tests for core/complexproj.py — the complex → real projection seam."""
from __future__ import annotations

import numpy as np

from npyquick.core import complexproj


def test_real_imag_are_zero_copy_views():
    arr = np.array([1 + 2j, 3 - 4j], dtype=np.complex128)
    real = complexproj.project(arr, "Real")
    imag = complexproj.project(arr, "Imag")
    assert np.shares_memory(real, arr), "Real projection must stay a view"
    assert np.shares_memory(imag, arr), "Imag projection must stay a view"
    np.testing.assert_array_equal(real, [1.0, 3.0])
    np.testing.assert_array_equal(imag, [2.0, -4.0])


def test_magnitude_and_phase_values():
    arr = np.array([1 + 1j], dtype=np.complex128)
    assert complexproj.project(arr, "Magnitude")[0] == np.sqrt(2.0)
    assert complexproj.project(arr, "Phase")[0] == np.pi / 4


def test_phase_wraps_to_pi_interval():
    arr = np.array([-1 + 0j, 1j, -1j], dtype=np.complex128)
    phase = complexproj.project(arr, "Phase")
    assert np.all(phase > -np.pi - 1e-9) and np.all(phase <= np.pi + 1e-9)
    assert phase[0] == np.pi          # angle of -1
    assert phase[1] == np.pi / 2      # angle of +i
    assert phase[2] == -np.pi / 2     # angle of -i


def test_component_names_order():
    assert complexproj.component_names() == ["Real", "Imag", "Magnitude", "Phase"]


def test_image_pairs_mapping():
    assert complexproj.IMAGE_PAIRS["Real / Imag"] == ("Real", "Imag")
    assert complexproj.IMAGE_PAIRS["Abs / Angle"] == ("Magnitude", "Phase")
    assert complexproj.DEFAULT_PAIR in complexproj.IMAGE_PAIRS
    assert complexproj.DEFAULT_HIST in complexproj.COMPONENTS
