# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class PixelTransform:
    """Bundles pixel size and physical unit; provides coord conversions.

    Image data is indexed in pixel coordinates (integers 0..h-1, 0..w-1).
    Display happens in physical coordinates (pixel × pixel_size). A
    transform with pixel_size=1.0 makes physical and pixel coords identical.
    """
    pixel_size: float = 1.0
    unit: str = "None"

    def extent(self, h: int, w: int) -> list[float]:
        """Return matplotlib imshow extent in physical coords."""
        ps = self.pixel_size
        return [-0.5 * ps, (w - 0.5) * ps, (h - 0.5) * ps, -0.5 * ps]

    def to_pixel(self, physical):
        """Convert physical coord(s) to pixel coord(s)."""
        return np.asarray(physical) / self.pixel_size

    def to_physical(self, pixel):
        """Convert pixel coord(s) to physical coord(s)."""
        return np.asarray(pixel) * self.pixel_size

    def clamp_x_physical(self, x: float, w: int) -> float:
        """Clamp physical x to [-0.5*ps, (w-0.5)*ps]."""
        ps = self.pixel_size
        return float(np.clip(x, -0.5 * ps, (w - 0.5) * ps))

    def clamp_y_physical(self, y: float, h: int) -> float:
        """Clamp physical y to [-0.5*ps, (h-0.5)*ps]."""
        ps = self.pixel_size
        return float(np.clip(y, -0.5 * ps, (h - 0.5) * ps))

    def format_unit(self) -> str:
        """Return unit for display ('' if 'None')."""
        return "" if self.unit == "None" else self.unit
