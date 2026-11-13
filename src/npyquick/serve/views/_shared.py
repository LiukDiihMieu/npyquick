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


def plotly_template_payload(dark: bool) -> dict:
    """Return Plotly's resolved built-in template for a layout-only update.

    Sending the template object through ``Plotly.relayout`` is only a few
    kilobytes and, unlike rebuilding a figure, cannot include its trace data.
    """
    return go.Layout(template=plotly_template(dark)).to_plotly_json()["template"]


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
    had actually finished). Turning it off leaves browser-window and tab
    activation sizing to the app's deliberate, visibility-aware
    ``resize_plotly_to_viewport`` path, which explicitly relayouts width and
    height without retransmitting trace data."""
    d = fig.to_plotly_json()
    d["config"] = {
        "edits": {"shapePosition": True}, "scrollZoom": True, "responsive": False,
        "displaylogo": False,  # hides the Plotly logomark in the modebar
    }
    return d


async def resize_plotly_to_viewport(
    element, *, min_height: int = 280, bottom_margin: int = 48,
) -> int:
    """Resize an existing, visible Plotly figure entirely in the browser.

    This sends no trace data: it waits for NiceGUI's asynchronously
    loaded Plotly component to be initialized and displayed, then updates the
    existing plot's explicit width and height with a small relayout. The width
    must be supplied directly: with this app's ``responsive=False`` config,
    Plotly.Plots.resize() left ``_fullLayout.width`` stuck at its initial value
    even though the HTML container itself had already resized (confirmed in a
    real browser). The bounded readiness wait is important for tab activation,
    where the Python value change can arrive just before Quasar has made the
    target panel visible.

    Returns the applied height so the caller can keep its Python state in sync
    for the next genuine data render.
    """
    return int(await ui.run_javascript(f"""
        return await new Promise((resolve, reject) => {{
            const deadline = performance.now() + 2000;
            const attempt = () => {{
                const comp = getElement("{element.id}");
                const gd = comp?.$el;
                const displayed = gd?.isConnected && gd.getClientRects().length > 0
                    && gd.getBoundingClientRect().width > 0;
                if (comp?.Plotly && gd?._fullLayout && displayed) {{
                    const rect = gd.getBoundingClientRect();
                    const width = Math.round(rect.width);
                    const top = rect.top;
                    const height = Math.max(
                        {min_height}, window.innerHeight - top - {bottom_margin},
                    );
                    gd.style.height = height + 'px';
                    Promise.resolve(comp.Plotly.relayout(gd, {{width, height}}))
                        .then(() => resolve(height))
                        .catch((error) => reject(error));
                    return;
                }}
                if (performance.now() >= deadline) {{
                    reject(new Error(
                        'Plotly element {element.id} did not become visible and ready within 2 seconds',
                    ));
                    return;
                }}
                setTimeout(attempt, 20);
            }};
            attempt();
        }});
    """, timeout=3.0))


async def fit_height_to_viewport(*elements, min_height: int = 280, bottom_margin: int = 16) -> None:
    """Pin each element's CSS height to the browser window's remaining
    vertical space below wherever it currently sits, so a view fills the
    visible viewport without the page needing to scroll. This direct CSS
    resize is for non-Plotly elements; Plotly also needs the explicit relayout
    performed by ``resize_plotly_to_viewport``."""
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
