# SPDX-License-Identifier: GPL-3.0-or-later

"""Complex-array → real-component projection, the single seam every complex
consumer routes through.

Memory-safety rule (the reason this lives in one place): np.real / np.imag
return zero-copy VIEWS, but np.abs / np.angle COMPUTE a full copy. Callers MUST
stride/sample the COMPLEX array first and project the small result — never
project a whole array — or a large complex memmap fully materializes in RAM,
defeating the stride/sample budgets the views rely on.
"""

from __future__ import annotations

import numpy as np

# Insertion order defines the order components appear in selectors.
COMPONENTS = {
    "Real": np.real,        # view
    "Imag": np.imag,        # view
    "Magnitude": np.abs,    # computes
    "Phase": np.angle,      # computes; radians, wrapped (-pi, pi]
}

# Default single component for the histogram's component selector.
DEFAULT_HIST = "Magnitude"

# Pairs the image view can show side by side; value is (panel_a, panel_b).
IMAGE_PAIRS = {
    "Real / Imag": ("Real", "Imag"),
    "Abs / Angle": ("Magnitude", "Phase"),
}
DEFAULT_PAIR = "Real / Imag"


def component_names() -> list[str]:
    return list(COMPONENTS)


def project(array: np.ndarray, component: str) -> np.ndarray:
    """Return the named real component of a complex array.

    Apply this AFTER striding/sampling — see the module docstring.
    """
    return COMPONENTS[component](array)
