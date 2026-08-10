# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 LiukDiihMieu

"""matplotlib colormap -> Plotly colorscale, for visual parity with the
desktop app's View > Colormap menu (see app.py's inline `colormaps` list and
`_effective_colormap`/`_colormap_icon`).

Always sample matplotlib directly rather than reaching for a same-named
Plotly built-in colorscale: there's no official bridge between the two
libraries (`plotly.colors` has no matplotlib-import helper), and in practice
trying to use Plotly's own named colorscales as stand-ins turned out to be
version-fragile in two silent (no-exception) ways — an unrecognized name
just renders Plotly's unrelated default colorscale instead of raising, and
even a recognized name isn't guaranteed to run in the same low-to-high
direction as matplotlib's colormap of the same name (Plotly's "Greys" runs
white-to-black, the opposite of matplotlib's "gray"). Sampling matplotlib
directly sidesteps both failure modes and needs no re-verification against
whatever Plotly.js version happens to be bundled.

Reversal is still a plain `reversescale` boolean on the trace, not a second
re-sampled array — that one's a normal, well-documented Plotly trace
property with no name-lookup involved, so it doesn't carry the same risk.
"""

from __future__ import annotations

from matplotlib import colormaps as mpl_colormaps

# Same (name, label) list and order as the desktop app's Colormap menu.
COLORMAPS = [
    ("gray", "Gray"),
    ("viridis", "Viridis"),
    ("plasma", "Plasma"),
    ("inferno", "Inferno"),
    ("magma", "Magma"),
    ("cividis", "Cividis"),
    ("twilight", "Twilight (cyclic)"),
    ("hot", "Hot"),
    ("coolwarm", "Coolwarm"),
    ("RdBu", "RdBu (diverging)"),
    ("turbo", "Turbo"),
]

# Stops sampled per colorscale: enough to track nonlinear/multi-hue maps like
# turbo or RdBu closely — Plotly linearly interpolates between whatever stops
# it's given, matplotlib's own curve does not.
_N_STOPS = 32


def colorscale_for(base: str) -> list[list]:
    """Sample a matplotlib colormap into a Plotly colorscale."""
    cmap = mpl_colormaps[base]
    positions = [i / (_N_STOPS - 1) for i in range(_N_STOPS)]
    rgba = cmap(positions, bytes=True)
    return [[pos, f"rgb({r},{g},{b})"] for pos, (r, g, b, _a) in zip(positions, rgba)]
