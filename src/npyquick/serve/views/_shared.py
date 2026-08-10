# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 LiukDiihMieu

"""Small helpers shared between image.py and histogram.py. Kept out of
core/ deliberately — these are Plotly/NiceGUI wiring details (event-arg key
shapes, client config), not framework-agnostic array logic."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import plotly.graph_objects as go
from nicegui import ui
from nicegui.element import Element

# Endpoint-equality tolerance used by both views to distinguish genuine drag
# input from the echo of their own corrective relayout call — each pushes a
# "corrected" shape position back after a drag (image.py mirrors/clips
# endpoints, histogram.py resnaps a tilted vline), and that push itself fires
# another relayout event right back at the same handler. Without recognizing
# "this reported position already matches what we just set" as a no-op, that
# echo looks like new input and the correction re-fires forever.
POS_TOL = 1e-6


@contextmanager
def control_group(title: str) -> Iterator[Element]:
    """A small bordered cluster of controls with an uppercase caption above
    it — e.g. "Display" / "Range" — so a view's toolbar reads as a few
    labeled instrument groups (like a scientific tool's property inspector)
    instead of one long, visually undifferentiated row of selects/buttons.

    Yields the OUTER container (caption + bordered box together), not the
    inner box — callers that need to hide an entire group at once (e.g.
    ImageView hiding "Display"/"Range" outright in RGB mode, where every
    control inside would otherwise be individually hidden and leave an
    empty box) should call `.set_visibility()` on this returned element,
    not on the individual controls placed inside it."""
    with ui.column().classes("gap-1") as group:
        ui.label(title.upper()).classes(
            "text-[10px] tracking-wide text-gray-500 dark:text-gray-400 font-medium px-1"
        )
        with ui.row().classes(
            "items-center gap-2 rounded-borders border px-3 py-1.5 border-gray-300 dark:border-gray-600"
        ):
            yield group


def plotly_template(dark: bool) -> str:
    """Plotly's own built-in dark theme name, not a hand-rolled recolor —
    matches the user's explicit preference to lean on native theming (Quasar
    dark mode via ui.dark_mode, AG Grid's dark mode is already automatic via
    its own body-class observer) rather than manually recoloring traces/axes
    to match."""
    return "plotly_dark" if dark else "plotly"


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
    return {"data": [], "layout": {}, "config": {"responsive": False, "displaylogo": False}}


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
    auto-adjusting to a live BROWSER WINDOW resize on its own. That
    remaining gap is closed separately and deliberately, not by flipping
    this back on: app.py's window-resize listener calls the active view's
    resize() (which itself calls measure_viewport_height() below, then
    re-renders), reusing the same already-correct "rebuild from scratch"
    path instead of going through Plotly's own crash-prone auto-resize."""
    d = fig.to_plotly_json()
    d["config"] = {
        "edits": {"shapePosition": True}, "scrollZoom": True, "responsive": False,
        "displaylogo": False,  # hides the Plotly logomark in the modebar
    }
    return d


async def measure_viewport_height(element, *, min_height: int = 280, bottom_margin: int = 48) -> int:
    """Return how much of the browser window's height remains below
    `element`'s current top position (clamped to a floor). Measures live
    via the browser's own layout (getBoundingClientRect) rather than a
    precomputed per-view offset, since exactly how much sits above a given
    plot varies with which optional status/anomaly labels happen to be
    visible right now.

    The caller must do TWO things with the result, both confirmed
    necessary by direct measurement (dropping either one left the
    rendered SVG clipped inside its own container, or at its old size
    entirely):
    1. Store it on the view's state and bake it into the next figure's own
       `layout.height`, ALONGSIDE `layout.autosize = False` (see
       ImageView._axis_layout's comment for why autosize has to be off —
       left at its default True, Plotly's own internal `_fullLayout.height`
       correctly picks up an explicit height, but silently never applies it
       to the actual DOM/SVG at all).
    2. ALSO set it as the element's own CSS height directly (e.g.
       `self.hist_plot.style(f"height: {h}px")`) BEFORE re-rendering.
       Skipping this leaves the SVG rendered at the new height internally
       (confirmed via direct inspection of the mounted component's state)
       but still clipped inside the OLD, unchanged container box — the two
       need to move together, one doesn't imply the other.

    Called from each Plotly-based view's resize() — itself triggered on
    tab-activation (see app.py's refresh_views) and on a live
    browser-window resize (see app.py's window-resize listener). min_height
    is the floor below which this stops shrinking further — a genuinely
    too-short window just falls back to the page's own natural scrolling
    beyond that point, rather than squeezing the view down to something
    unusably small. bottom_margin's default (48, not a token amount) is
    NOT slack for the plot itself — it's covering fixed chrome that sits
    BELOW wherever the plot ends regardless of its height: Quasar's own
    `q-tab-panel` bottom padding (16px) + this app's own outer-column
    bottom padding (16px, see app.py's `p-4`) + the browser's default
    `<body>` margin (16px). Measuring from the plot's own top can't see
    any of that — it has to be reserved unconditionally instead."""
    return await ui.run_javascript(f"""
        const el = getHtmlElement({element.id});
        const top = el.getBoundingClientRect().top;
        return Math.max({min_height}, window.innerHeight - top - {bottom_margin});
    """)


async def fit_height_to_viewport(*elements, min_height: int = 280, bottom_margin: int = 16) -> None:
    """Pin each element's CSS height to the browser window's remaining
    vertical space below wherever it currently sits, so a view fills the
    visible viewport without the page needing to scroll. Same measurement
    as measure_viewport_height, applied directly as a style instead of
    being returned — safe for ag-Grid (used by TableView.resize()), which
    genuinely does track its own container's live CSS size via its own
    internal ResizeObserver. NOT used for Plotly elements — see
    measure_viewport_height's docstring for why that needs a different
    approach (baking the height into the figure itself)."""
    if not elements:
        return
    ids = ", ".join(str(el.id) for el in elements)
    await ui.run_javascript(f"""
        [{ids}].forEach((id) => {{
            const el = getHtmlElement(id);
            const top = el.getBoundingClientRect().top;
            const h = Math.max({min_height}, window.innerHeight - top - {bottom_margin});
            el.style.height = h + 'px';
        }});
    """)


def shape_touched(args: dict, shape_index: int, *fields: str) -> bool:
    """True if a relayout event's args mention any of shapes[shape_index]'s
    given fields (e.g. "x0", "y1") at all."""
    prefix = f"shapes[{shape_index}]"
    return any(f"{prefix}.{field}" in args for field in fields)
