# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 LiukDiihMieu

"""Small helpers shared between image.py and histogram.py. Kept out of
core/ deliberately — these are Plotly/NiceGUI wiring details (event-arg key
shapes, client config), not framework-agnostic array logic."""

from __future__ import annotations

import plotly.graph_objects as go

# Endpoint-equality tolerance used by both views to distinguish genuine drag
# input from the echo of their own corrective relayout call — each pushes a
# "corrected" shape position back after a drag (image.py mirrors/clips
# endpoints, histogram.py resnaps a tilted vline), and that push itself fires
# another relayout event right back at the same handler. Without recognizing
# "this reported position already matches what we just set" as a no-op, that
# echo looks like new input and the correction re-fires forever.
POS_TOL = 1e-6

def empty_plotly_figure() -> dict:
    """A fresh placeholder dict for a ui.plotly element with no data yet
    (real data only arrives later via set_data()), starting out hidden (see
    each view's hide()). Returns a new dict every call rather than a shared
    constant — several call sites each hand their own instance straight to a
    different ui.plotly element, and nothing should assume it's safe to share
    or mutate the same dict object across them.

    The config matters here, not just data/layout: without an explicit
    config, NiceGUI's ResizeObserver has nothing to check responsive against
    (config is simply absent) and calls Plotly.Plots.resize() on its very
    first observation — which fires immediately upon mounting, while still
    inside a display:none ancestor — throwing "Resize must be passed a
    displayed plot div element" before set_data() ever runs. See
    with_plotly_config's docstring for the general responsive=False
    rationale; this is the same fix applied to the placeholder that a real
    figure later replaces."""
    return {"data": [], "layout": {}, "config": {"responsive": False}}


def with_plotly_config(fig: go.Figure) -> dict:
    """Convert a go.Figure to the dict form ui.plotly needs, with the config
    every draggable-shape plot in this app requires: config.edits.shapePosition
    (not shapes[].editable) is what makes a shape draggable in one continuous
    mousedown-move-up gesture, and scrollZoom is off by default in Plotly.

    responsive=False: NiceGUI's own ui.plotly wrapper (elements/plotly/plotly.js)
    unconditionally attaches a ResizeObserver to every plot's div and calls
    Plotly.Plots.resize() on ANY size change, unless this is explicitly False.
    That collides with this app's hide()/set_visibility() view-switching: a
    resize firing while the div is mid-transition (display:none) throws
    "Resize must be passed a displayed plot div element" in the browser
    console and can leave the plot's internal size wrong afterwards (observed
    as the Image/Profile side-by-side split rendering at the wrong ratio, or
    even wrapping onto two lines on a narrow window, well after any hide/show
    had actually finished). Every place that changes what's plotted already
    goes through _full_render()/set_data(), which rebuilds the whole figure
    via Plotly.newPlot/react and sizes itself correctly from the container's
    CURRENT size at that moment — so turning off the separate, crash-prone
    auto-resize-on-any-DOM-change path costs nothing except no longer
    auto-adjusting to a live BROWSER WINDOW resize between reloads, which is
    a much smaller and rarer gap than the bug it replaces."""
    d = fig.to_plotly_json()
    d["config"] = {"edits": {"shapePosition": True}, "scrollZoom": True, "responsive": False}
    return d


def shape_touched(args: dict, shape_index: int, *fields: str) -> bool:
    """True if a relayout event's args mention any of shapes[shape_index]'s
    given fields (e.g. "x0", "y1") at all."""
    prefix = f"shapes[{shape_index}]"
    return any(f"{prefix}.{field}" in args for field in fields)
