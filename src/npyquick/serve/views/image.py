# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 LiukDiihMieu

"""Image view: grayscale, RGB, and complex dual-panel, with a linked
cross-section profile. Ported from views/image.py's ImageCanvas/ImageView.

Interaction notes (see the git history of this file for how these were
found): the cross-section line is dragged via Plotly's config.edits.shapePosition
(not shapes[].editable — that requires a separate activating click first), and
every plotly_click on the image plot must have its `data` field stripped
before it's forwarded to the server, or a click leaks the entire trace's raw
array back over the websocket.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import plotly.graph_objects as go
from nicegui import ui
from plotly.subplots import make_subplots

from npyquick.core import complexproj, limits, profile
from npyquick.core.pixel_expr import format_unit
from npyquick.core.stats import ArrayStats, array_stats, is_real_numeric
from npyquick.serve import colormaps
from npyquick.serve.views._shared import (
    POS_TOL,
    control_group,
    empty_plotly_figure,
    measure_viewport_height,
    plotly_template,
    shape_touched,
    with_plotly_config,
)

Point = tuple[float, float]
Clim = tuple[float | None, float | None]

_MARKER_COLORS = ["cyan", "magenta"]
_LINE_COLOR = "yellow"

# core.limits.IMAGE_MAX_PIXELS (4096x4096) is sized for the desktop's local
# matplotlib rendering, not for shipping the downsampled array to a browser as
# JSON over a websocket — a 4096x4096 grid (16.7M numbers) took ~38s to load a
# single page and pegged the server at 100% CPU during a real test against a
# 12000x12000 array. Serve gets its own, much smaller budget instead of
# touching the shared constant (which the desktop app still relies on as-is).
_SERVE_IMAGE_MAX_PIXELS = 2048 * 2048


class ImageState:
    def __init__(self) -> None:
        self.mode: str = "none"  # "gray" | "rgb" | "complex"
        # endpoints are stored in PHYSICAL (pixel_size-scaled) coordinates,
        # matching the desktop's ImageCanvas — see ImageView.set_pixel_size.
        self.endpoints: tuple[Point, Point] = ((0.0, 0.0), (0.0, 0.0))
        self.pixel_size: float = 1.0
        self.unit: str = "None"
        self.colormap_base: str = "gray"
        self.colormap_reverse: bool = False
        self.pair: str = complexproj.DEFAULT_PAIR
        self.active_panel: int = 0  # 0 or 1; only meaningful in complex mode
        self.dark: bool = False
        # Fallback until the first resize() measures the real viewport (see
        # measure_viewport_height's docstring for why this is baked into the
        # figure's own layout.height rather than fought over via CSS).
        # Measured independently, not shared: image_row's flex layout only
        # keeps image_plot/profile_plot at the same vertical position when
        # there's enough WIDTH for the 62:38 side-by-side split to actually
        # fit; on a narrow enough window they wrap onto separate lines
        # instead (Quasar's row wraps by default), and profile_plot's real
        # top position — and therefore how much viewport height is left
        # for it — is then nothing like image_plot's.
        self.plot_height: int = 650
        self.profile_height: int = 400

        # Populated by ImageView.set_data, per mode:
        self.array: np.ndarray | None = None  # full-res array, for pair switches
        self.display: np.ndarray | None = None  # gray/rgb
        self.display_a: np.ndarray | None = None  # complex panel A
        self.display_b: np.ndarray | None = None  # complex panel B
        self.rgb_is_uint8: bool = False
        self.clim: Clim = (None, None)  # gray
        self.clim_a: Clim = (None, None)  # complex panel A
        self.clim_b: Clim = (None, None)  # complex panel B
        self.downsample_str: str | None = None
        self.norm_str: str | None = None


def _default_clim(display: np.ndarray) -> Clim:
    stats = array_stats(display)
    if stats is None or stats.finite_min is None:
        return None, None
    return stats.finite_min, stats.finite_max


def _colormap_scale(state: ImageState) -> str | list:
    return colormaps.colorscale_for(state.colormap_base)


def _marker_trace(endpoints: tuple[Point, Point]) -> go.Scatter:
    (x0, y0), (x1, y1) = endpoints
    return go.Scatter(
        x=[x0, x1], y=[y0, y1], mode="markers",
        marker={"size": 12, "color": _MARKER_COLORS, "line": {"color": "black", "width": 1}},
        hoverinfo="skip", showlegend=False,
    )


def _line_shape(endpoints: tuple[Point, Point], xref: str = "x", yref: str = "y") -> dict:
    (x0, y0), (x1, y1) = endpoints
    return {
        "type": "line", "xref": xref, "yref": yref,
        "x0": x0, "y0": y0, "x1": x1, "y1": y1,
        "line": {"color": _LINE_COLOR, "width": 2},
    }


def _axis_layout(unit: str, height: int) -> dict:
    return {
        # scaleanchor+constrain=domain: square pixels, letterboxed rather than
        # stretched or range-blown-out when the container doesn't match the
        # data's aspect ratio.
        "xaxis": {"constrain": "domain", "title": unit},
        "yaxis": {"autorange": "reversed", "scaleanchor": "x", "constrain": "domain", "title": unit},
        "dragmode": "pan",  # plain click-drag pans; dragging the shape itself
                             # still edits it regardless of dragmode (separate
                             # interaction target in Plotly).
        "margin": {"l": 20, "r": 20, "t": 20, "b": 20},
        "showlegend": False,
        # See measure_viewport_height's docstring (_shared.py) for why this
        # is an explicit figure property rather than a CSS/container size.
        "height": height,
    }


def _gray_figure(state: ImageState) -> dict:
    assert state.display is not None
    vmin, vmax = state.clim
    ps = state.pixel_size
    unit = format_unit(state.unit)
    heat = go.Heatmap(
        z=state.display, colorscale=_colormap_scale(state), reversescale=state.colormap_reverse,
        zmin=vmin, zmax=vmax, dx=ps, dy=ps,
        hovertemplate=f"x=%{{x}}{unit}<br>y=%{{y}}{unit}<br>value=%{{z}}<extra></extra>",
    )
    fig = go.Figure(data=[heat, _marker_trace(state.endpoints)])
    fig.update_layout(
        **_axis_layout(unit, state.plot_height), shapes=[_line_shape(state.endpoints)],
        template=plotly_template(state.dark),
    )
    return with_plotly_config(fig)


def _rgb_figure(state: ImageState) -> dict:
    assert state.display is not None
    z = state.display if state.rgb_is_uint8 else np.clip(np.round(state.display * 255), 0, 255).astype(np.uint8)
    ps = state.pixel_size
    unit = format_unit(state.unit)
    # go.Image supports dx/dy/x0/y0 (added for georeferenced-image use cases)
    # just like go.Heatmap, so the same physical-scaling trick applies here.
    img = go.Image(
        z=z, dx=ps, dy=ps,
        hovertemplate=f"x=%{{x}}{unit}<br>y=%{{y}}{unit}<br>R=%{{z[0]}} G=%{{z[1]}} B=%{{z[2]}}<extra></extra>",
    )
    fig = go.Figure(data=[img, _marker_trace(state.endpoints)])
    fig.update_layout(
        **_axis_layout(unit, state.plot_height), shapes=[_line_shape(state.endpoints)],
        template=plotly_template(state.dark),
    )
    return with_plotly_config(fig)


def _complex_figure(state: ImageState) -> dict:
    assert state.display_a is not None and state.display_b is not None
    a_name, b_name = complexproj.IMAGE_PAIRS[state.pair]
    ps = state.pixel_size
    unit = format_unit(state.unit)
    fig = make_subplots(rows=1, cols=2, horizontal_spacing=0.08, subplot_titles=(a_name, b_name))
    scale = _colormap_scale(state)
    vmin_a, vmax_a = state.clim_a
    vmin_b, vmax_b = state.clim_b
    # Plotly positions every trace's colorbar at the same default spot — with
    # two heatmaps in a 1x2 subplot grid, that stacked both colorbars on top
    # of each other at the far right. x values below match make_subplots'
    # own column domains (0, 0.46) and (0.54, 1.0) for horizontal_spacing=0.08.
    fig.add_trace(go.Heatmap(
        z=state.display_a, colorscale=scale, reversescale=state.colormap_reverse,
        zmin=vmin_a, zmax=vmax_a, dx=ps, dy=ps,
        colorbar={"x": 0.46, "len": 0.9, "thickness": 15},
        hovertemplate=f"x=%{{x}}{unit}<br>y=%{{y}}{unit}<br>{a_name}=%{{z}}<extra></extra>",
    ), row=1, col=1)
    fig.add_trace(go.Heatmap(
        z=state.display_b, colorscale=scale, reversescale=state.colormap_reverse,
        zmin=vmin_b, zmax=vmax_b, dx=ps, dy=ps,
        colorbar={"x": 1.02, "len": 0.9, "thickness": 15},
        hovertemplate=f"x=%{{x}}{unit}<br>y=%{{y}}{unit}<br>{b_name}=%{{z}}<extra></extra>",
    ), row=1, col=2)
    # Trace order fixed at [heat_a=0, heat_b=1, marker_a=2, marker_b=3] —
    # the relayout/colormap/clim handlers below index into this by position.
    fig.add_trace(_marker_trace(state.endpoints), row=1, col=1)
    fig.add_trace(_marker_trace(state.endpoints), row=1, col=2)

    fig.update_xaxes(constrain="domain", title=unit, row=1, col=1)
    fig.update_yaxes(autorange="reversed", scaleanchor="x", constrain="domain", title=unit, row=1, col=1)
    # matches ties panel B's axes to panel A's, giving linked pan/zoom natively
    # (simpler than the desktop's manual get_view/set_view mirror hooks).
    fig.update_xaxes(constrain="domain", matches="x", title=unit, row=1, col=2)
    fig.update_yaxes(autorange="reversed", scaleanchor="x2", constrain="domain", matches="y", title=unit, row=1, col=2)

    fig.update_layout(
        dragmode="pan",
        margin={"l": 20, "r": 20, "t": 30, "b": 20},
        showlegend=False,
        template=plotly_template(state.dark),
        height=state.plot_height,  # see _axis_layout's comment
        shapes=[
            _line_shape(state.endpoints, xref="x", yref="y"),
            _line_shape(state.endpoints, xref="x2", yref="y2"),
        ],
    )
    return with_plotly_config(fig)


def _image_figure(state: ImageState) -> dict:
    if state.mode == "rgb":
        return _rgb_figure(state)
    if state.mode == "complex":
        return _complex_figure(state)
    return _gray_figure(state)


def _active_display(state: ImageState) -> np.ndarray:
    if state.mode == "complex":
        return state.display_a if state.active_panel == 0 else state.display_b
    assert state.display is not None
    return state.display


def _profile_figure(
    distances: np.ndarray, values: np.ndarray, ylabel: str, unit: str, dark: bool, height: int,
) -> dict:
    # compute_profile returns (N,) for grayscale/complex-component data but
    # (C, N) for RGB — go.Scatter silently accepts a 2D `y` without error and
    # renders garbage, so this must split it into per-channel traces instead
    # of forwarding it as-is (ported from views/image.py:ProfileCanvas.set_profile).
    if values.ndim == 2:
        colors, labels = ["red", "green", "blue"], ["R", "G", "B"]
        traces = [
            go.Scatter(x=distances, y=values[i], mode="lines", name=labels[i],
                       line={"color": colors[i], "width": 5})
            for i in range(values.shape[0])
        ]
        fig = go.Figure(data=traces)
    else:
        fig = go.Figure(data=[go.Scatter(
            x=distances, y=values, mode="lines", showlegend=False, line={"width": 5},
        )])
    u = format_unit(unit)
    x_title = f"Distance ({u})" if u else "Distance"
    fig.update_layout(
        xaxis_title=x_title, yaxis_title=ylabel,
        margin={"l": 40, "r": 20, "t": 20, "b": 40},
        template=plotly_template(dark),
        height=height,  # see _axis_layout's comment above
    )
    # Not with_plotly_config(): that config is for the draggable-shape plots
    # (Image/Histogram) and carries edits.shapePosition, which this plot has
    # no use for (no shapes here). Same minimal config lineplot.py builds
    # inline for the same reason — responsive off (see with_plotly_config's
    # docstring for why every plot in this app needs that), logo off to
    # match every other plot.
    d = fig.to_plotly_json()
    d["config"] = {"responsive": False, "displaylogo": False}
    return d


class ImageView:
    def __init__(self) -> None:
        self.state = ImageState()
        self._on_clim_change: Callable[[float | None, float | None], None] = lambda vmin, vmax: None
        self._on_active_panel_change: Callable[[], None] = lambda: None

        # No card/title wrapper: this view now lives in its own ui.tab_panel
        # (app.py), which already supplies that visual identity via the tab
        # bar — an unsupported shape/dtype now DISABLES that tab instead of
        # needing this view to hide itself (see app.py's refresh_views).
        # Two labeled instrument groups ("Display"/"Range") rather than one
        # flat row — see _shared.control_group's docstring. Both groups
        # (not just the individual controls inside them) get hidden
        # outright in RGB mode (see _sync_controls): RGB is shown as raw
        # R/G/B values, so neither a colormap nor a value range applies,
        # and a bordered box with nothing visible inside it would just be
        # empty dead space.
        with ui.row().classes("items-start gap-4") as self.controls:
            with control_group("Display") as self._display_group:
                # min-width: ui.select otherwise sizes to the current VALUE's
                # text ("Gray"), not the (longer) floating LABEL above it,
                # which clips the label to "Col...".
                self.colormap_select = ui.select(
                    {name: label for name, label in colormaps.COLORMAPS}, value=self.state.colormap_base,
                    label="Colormap",
                ).classes("min-w-[9rem]").props("dense")
                self.reverse_checkbox = ui.checkbox("Reverse").props("dense")
                self.pair_select = ui.select(
                    list(complexproj.IMAGE_PAIRS), value=self.state.pair, label="Pair",
                ).props("dense")
                # Names which component's vmin/vmax the edit boxes show/apply
                # to in complex mode (e.g. "Real") — otherwise it's only
                # inferable from which panel you last clicked.
                self.clim_prefix_label = ui.label().classes("text-sm text-gray-500")
            with control_group("Range") as self._range_group:
                self.vmin_input = ui.number("vmin", format="%.4g").props("dense")
                self.vmax_input = ui.number("vmax", format="%.4g").props("dense")
                self.apply_btn = ui.button("Apply").props("dense")
                self.reset_btn = ui.button("Reset").props("dense")
        self.clim_prefix_label.set_visibility(False)

        with ui.row().classes("items-center gap-3") as self.status_row:
            self.downsample_label = ui.label().classes("text-amber-600 text-sm")
            self.norm_label = ui.label().classes("text-sm text-gray-500")
            self.anomaly_label = ui.label().classes("text-red-500 text-sm")
        self.status_row.set_visibility(False)

        # Side by side, like the desktop's image/profile QSplitter (default
        # sizes [780, 480], ~62:38 — matched here via flex-[62]/flex-[38])
        # rather than stacked, which wasted a lot of vertical scrolling on a
        # typical wide browser window. min-w-0 on both: a flex item's default
        # min-width is its CONTENT's min-content size, not 0 — and if Plotly
        # ever renders its SVG at a size wider than the item's flex-basis
        # share (observed: right when this view becomes visible as the
        # startup file-picker dialog closes, Plotly can measure the
        # container mid-close-transition and lock in a near-full-row SVG
        # width for BOTH plots), the browser refuses to shrink either flex
        # item back down to its 62/38 share and wraps them onto separate
        # lines instead — a classic flexbox gotcha, independent of whatever
        # caused the oversized initial measurement in the first place.
        # min-w-0 removes that content-based floor entirely, so flex-grow
        # always wins regardless of what Plotly happened to render at.
        with ui.row().classes("w-full items-start gap-2") as self.image_row:
            self.image_plot = ui.plotly(empty_plotly_figure()).classes("flex-[62] min-w-0").style("height: 650px")
            self.profile_plot = ui.plotly(empty_plotly_figure()).classes("flex-[38] min-w-0").style("height: 650px")

        self.image_plot.on("plotly_relayout", self._on_relayout)
        # Plotly attaches a `data` field to every click point that references
        # the WHOLE trace's raw input (its full z matrix for a Heatmap) — a
        # multi-MB field for anything but a tiny array. NiceGUI's own event
        # forwarding strips fullData/xaxis/yaxis (needed to avoid circular-
        # reference JSON errors) but not `data`, so it survives untouched and
        # gets emitted back to the server, tripping the client's own outgoing
        # message-size guard (confirmed via a headless-browser repro: a click
        # after a drag produced a 3.2 MB points[0].data field). _on_click only
        # ever reads curveNumber, so stripping data here costs nothing.
        self.image_plot.on(
            "plotly_click", self._on_click,
            js_handler="""(...args) => {
                const ev = args[0];
                if (ev && ev.points) {
                    ev.points = ev.points.map((p) => ({...p, data: undefined}));
                }
                emit(...args);
            }""",
        )
        self.colormap_select.on_value_change(self._apply_colormap)
        self.reverse_checkbox.on_value_change(self._apply_colormap)
        self.pair_select.on_value_change(self._apply_pair)
        self.apply_btn.on_click(self._apply_clim)
        self.reset_btn.on_click(self._reset_clim)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def set_on_clim_change(self, cb: Callable[[float | None, float | None], None]) -> None:
        self._on_clim_change = cb

    def set_on_active_panel_change(self, cb: Callable[[], None]) -> None:
        self._on_active_panel_change = cb

    def get_clim(self) -> Clim:
        if self.state.mode == "rgb":
            return None, None
        if self.state.mode == "complex":
            return self.state.clim_a if self.state.active_panel == 0 else self.state.clim_b
        return self.state.clim

    def active_display(self) -> np.ndarray:
        return _active_display(self.state)

    def set_pixel_size(self, ps: float, unit: str) -> None:
        """Apply a physical pixel size/unit, same idea as the desktop's
        ImageCanvas.set_pixel_size. state.endpoints are stored in already-
        scaled physical coordinates (not raw pixel indices), so a pixel-size
        CHANGE must rescale them by the ratio to keep pointing at the same
        underlying pixel — otherwise the cross-section would silently jump to
        a different location on the array the moment the unit changes."""
        state = self.state
        if ps == state.pixel_size and unit == state.unit:
            return
        ratio = ps / state.pixel_size
        state.pixel_size = ps
        state.unit = unit
        if state.array is None:
            return
        (x0, y0), (x1, y1) = state.endpoints
        state.endpoints = ((x0 * ratio, y0 * ratio), (x1 * ratio, y1 * ratio))
        self._full_render()

    async def resize(self) -> None:
        """Measure the current viewport, store it, then re-render from
        scratch and force every axis to actually recompute its range.

        The measure_viewport_height() calls are unrelated to the tab-switch
        staleness issue described below — they're what makes this view's
        plots fill the browser window's available height (down to a
        sensible floor) instead of sitting at a fixed pixel height, so a
        typical window doesn't need to scroll to see the whole plot. See
        that function's docstring (_shared.py) for why the result has to be
        applied BOTH ways — stored on state and baked into the next
        figure's own layout.height, AND set directly as the plot element's
        own CSS height — dropping either one leaves the SVG either clipped
        inside its old-sized container or not resized at all. image_plot
        and profile_plot are measured SEPARATELY (not one height reused for
        both): image_row's 62:38 side-by-side split only holds while
        there's enough WIDTH for it — on a narrow enough window the two
        wrap onto separate lines instead (Quasar's row wraps by default),
        putting profile_plot at a completely different vertical position
        with a different amount of viewport left below it.

        The rest of this docstring covers a separate, harder-to-see issue:
        needed when this view's TAB becomes active:
        with Quasar's tab panels, an already-mounted-but-currently-INACTIVE
        panel's ui.plotly element is still a live Vue/Plotly instance under
        the hood, and set_data()'s .update() call runs (updating the
        figure's DATA) regardless of whether that panel happens to be the
        visible one at that moment — the app orchestrator calls set_data()
        on all views unconditionally, then decides which tab to switch to
        afterward. If a plot's `react()` (Plotly's own update path for an
        already-existing instance) runs while its container is hidden/
        zero-size, Plotly can bake in wrong internal sizing that persists
        even once the container becomes visible again — observed concretely
        as the complex mode's Real/Imag subplots rendering at badly wrong
        proportions after switching INTO the Image tab from a different one.

        Two things were tried and DIDN'T fix it, worth remembering:
        `run_plot_method("relayout", {"autosize": True})` — the autosize
        flag only toggles Plotly's own responsive-resize BEHAVIOR going
        forward, it doesn't force an immediate re-measurement. Calling the
        real `Plotly.Plots.resize()` via a raw run_javascript snippet (since
        that nested path isn't reachable through run_plot_method's flat
        `Plotly[name]` lookup) — actively made it WORSE (new "Cannot read
        properties of undefined" and "Maximum call stack size exceeded"
        console errors), likely because it raced the client's own Plotly
        module still finishing its (re)mount and/or recursed into our own
        plotly_relayout handler.

        What DOES fix the SIZING: just calling _full_render() again — the
        exact same call a genuinely fresh, always-correctly-rendered load
        already goes through (confirmed: loading this same array directly as
        the startup file, so its tab is the only one ever activated, never
        reproduces this bug at all). But that alone left one thing still
        stale: the axis RANGE — Plotly's react() deliberately preserves an
        axis's current range across an update (it can't tell "wrong range
        baked in while hidden" apart from "the user deliberately zoomed",
        and assumes the latter), so the panel that was previously
        mismeasured kept its bad range even after the resend fixed its
        overall proportions. Forcing autorange back on for every axis this
        view's CURRENT mode actually has is what resets it.

        Only the axes that exist for the current mode are included below —
        confirmed via a real browser's console that relaying out a
        NONEXISTENT axis (e.g. xaxis2/yaxis2 while in plain gray/RGB mode,
        which never builds a second subplot at all) is not silently
        ignored: it throws "Cannot read properties of undefined (reading
        '_inputDomain')" inside Plotly's own relayout handler, which rejects
        the promise run_plot_method is awaiting — leaving the Python-side
        call with no successful response ever coming, surfacing later as a
        JavaScript-did-not-respond timeout with no obvious connection to the
        real cause."""
        if self.state.array is not None:
            self.state.plot_height = await measure_viewport_height(self.image_plot)
            self.state.profile_height = await measure_viewport_height(self.profile_plot)
            self.image_plot.style(f"height: {self.state.plot_height}px")
            self.profile_plot.style(f"height: {self.state.profile_height}px")
            self._full_render()
            relayout = {"xaxis.autorange": True, "yaxis.autorange": "reversed"}
            if self.state.mode == "complex":
                relayout.update({"xaxis2.autorange": True, "yaxis2.autorange": "reversed"})
            await self.image_plot.run_plot_method("relayout", relayout)

    def set_dark(self, is_dark: bool) -> None:
        """Switch Plotly's own built-in dark template (see
        serve/views/_shared.py's plotly_template) — Quasar's dark mode
        already recolors this view's card/controls on its own; only the
        Plotly figures need an explicit nudge since Plotly doesn't watch for
        that itself."""
        self.state.dark = is_dark
        if self.state.array is not None:
            self._full_render()

    def set_data(self, array: np.ndarray, stats: ArrayStats | None = None) -> str | None:
        """Prepare `array` (already loaded by the caller) for display. Returns
        an error message, or None on success."""
        self.status_row.set_visibility(False)
        state = self.state
        is_complex = np.issubdtype(array.dtype, np.complexfloating)
        is_rgb = array.ndim == 3 and array.shape[2] == 3 and is_real_numeric(array)
        is_gray = array.ndim == 2 and (is_real_numeric(array) or is_complex)
        if not is_rgb and not is_gray:
            return f"Image view doesn't support shape {array.shape} dtype {array.dtype} yet."

        state.array = array
        # Downsample by spatial pixel count before any dtype cast/projection,
        # same idea as the desktop ImageCanvas.load (a memmap is never fully
        # read into RAM just to render a preview) but with serve's own,
        # much tighter budget — see _SERVE_IMAGE_MAX_PIXELS above.
        h, w = array.shape[:2]
        stride = limits.stride_for(h * w, _SERVE_IMAGE_MAX_PIXELS)
        strided = array[::stride, ::stride]
        dh, dw = strided.shape[:2]
        ps = state.pixel_size  # persists across loads, like the desktop's transform
        state.endpoints = ((dw * 0.1 * ps, dh * 0.5 * ps), (dw * 0.9 * ps, dh * 0.5 * ps))
        state.active_panel = 0
        state.downsample_str = (
            f"downsampled {h}×{w} → {dh}×{dw}  (1/{stride})" if stride > 1 else None
        )
        state.norm_str = None

        if is_complex:
            state.mode = "complex"
            self._project_complex_pair(strided)
        elif is_rgb:
            state.mode = "rgb"
            rgb = strided[:, :, :3]
            if rgb.dtype == np.uint8:
                # Ported from views/image.py:_prepare_rgb — uint8 renders as-is.
                state.display = np.asarray(rgb)
                state.rgb_is_uint8 = True
                state.norm_str = "uint8 [0, 255] — as-is"
            else:
                d = rgb.astype(np.float32)
                if np.issubdtype(array.dtype, np.integer):
                    maxval = np.iinfo(array.dtype).max
                    d = d / maxval
                    state.norm_str = f"{array.dtype} ÷ {maxval}"
                else:
                    lo, hi = float(d.min()), float(d.max())
                    if lo >= 0.0 and hi <= 1.0:
                        state.norm_str = f"float [{lo:.3g}, {hi:.3g}] — as-is"
                    else:
                        span = hi - lo
                        d = (d - lo) / span if span > 0 else np.zeros_like(d)
                        state.norm_str = f"float [{lo:.3g}, {hi:.3g}] → [0, 1]  (global min-max)"
                state.display = np.clip(d, 0.0, 1.0)
                state.rgb_is_uint8 = False
        else:
            state.mode = "gray"
            state.display = np.asarray(strided)
            state.clim = _default_clim(state.display)

        self._full_render()
        self._update_status_labels(array, stats)
        return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _update_status_labels(self, array: np.ndarray, stats: ArrayStats | None) -> None:
        state = self.state
        self.downsample_label.text = state.downsample_str or ""
        self.downsample_label.set_visibility(bool(state.downsample_str))
        self.norm_label.text = f"norm: {state.norm_str}" if state.norm_str else ""
        self.norm_label.set_visibility(bool(state.norm_str))
        if stats is None:
            stats = array_stats(array)
        has_anomaly = stats is not None and stats.has_anomaly
        self.anomaly_label.text = stats.anomaly_str() if has_anomaly else ""
        self.anomaly_label.set_visibility(has_anomaly)
        self.status_row.set_visibility(bool(state.downsample_str or state.norm_str or has_anomaly))

    def _project_complex_pair(self, strided: np.ndarray) -> None:
        state = self.state
        a, b = complexproj.IMAGE_PAIRS[state.pair]
        # project() computes (Abs/Angle copy, Real/Imag view) — applied here,
        # after striding, per complexproj's memory-safety rule.
        state.display_a = np.asarray(complexproj.project(strided, a))
        state.display_b = np.asarray(complexproj.project(strided, b))
        state.clim_a = (-np.pi, np.pi) if a == "Angle" else _default_clim(state.display_a)
        state.clim_b = (-np.pi, np.pi) if b == "Angle" else _default_clim(state.display_b)

    def _sync_controls(self) -> None:
        state = self.state
        self.pair_select.set_visibility(state.mode == "complex")
        self.clim_prefix_label.set_visibility(state.mode == "complex")
        if state.mode == "complex":
            a, b = complexproj.IMAGE_PAIRS[state.pair]
            self.clim_prefix_label.text = a if state.active_panel == 0 else b
        # RGB is displayed as-is (actual R/G/B pixel values, not a scalar
        # mapped through a colorscale) — colormap/reverse/vmin/vmax all have
        # nothing to act on in that mode, same as the desktop's ImageView
        # disabling its own clim controls for RGB. Hides the whole "Display"/
        # "Range" GROUP, not just the individual controls inside it — both
        # groups are empty in RGB mode (Pair/clim_prefix_label are already
        # separately hidden outside complex mode), and an empty bordered box
        # would just be dead space.
        self._display_group.set_visibility(state.mode != "rgb")
        self._range_group.set_visibility(state.mode != "rgb")
        vmin, vmax = self.get_clim()
        self.vmin_input.value = vmin
        self.vmax_input.value = vmax

    def _render_profile(self) -> None:
        state = self.state
        display = _active_display(state)
        ps = state.pixel_size
        # state.endpoints are physical coordinates; compute_profile needs
        # pixel indices into `display`, and the returned distances need
        # scaling back up for display — same split desktop's
        # ImageCanvas._refresh_profile / ProfileCanvas.set_profile make.
        (x0, y0), (x1, y1) = state.endpoints
        p0_px = np.array([x0 / ps, y0 / ps])
        p1_px = np.array([x1 / ps, y1 / ps])
        distances, values = profile.compute_profile(display, p0_px, p1_px)
        distances = distances * ps
        if state.mode == "complex":
            ylabel = complexproj.IMAGE_PAIRS[state.pair][state.active_panel]
        else:
            ylabel = "Intensity"
        self.profile_plot.figure = _profile_figure(
            distances, values, ylabel, state.unit, state.dark, state.profile_height,
        )
        self.profile_plot.update()

    def _full_render(self) -> None:
        self.image_plot.figure = _image_figure(self.state)
        self.image_plot.update()
        self._sync_controls()
        self._render_profile()

    async def _sync_markers(self) -> None:
        (x0, y0), (x1, y1) = self.state.endpoints
        marker_indices = [2, 3] if self.state.mode == "complex" else [1]
        xs = [[x0, x1]] * len(marker_indices)
        ys = [[y0, y1]] * len(marker_indices)
        await self.image_plot.run_plot_method("restyle", {"x": xs, "y": ys}, marker_indices)

    def _apply_endpoints_from_args(self, args: dict, shape_index: int) -> bool:
        """Read shapes[shape_index].{x0,y0,x1,y1} out of a relayout event,
        falling back to the current value for any key the event omits (a
        drag only reports the coordinates that actually moved). Returns
        False if this event doesn't touch our shape at all, OR if the
        resulting position is unchanged from state.endpoints — the latter
        is what happens when this event is the echo of our OWN mirroring
        relayout call below, not new user input (see _on_relayout)."""
        state = self.state
        prefix = f"shapes[{shape_index}]"
        if not shape_touched(args, shape_index, "x0", "y0", "x1", "y1"):
            return False
        (old_x0, old_y0), (old_x1, old_y1) = state.endpoints
        x0 = args.get(f"{prefix}.x0", old_x0)
        y0 = args.get(f"{prefix}.y0", old_y0)
        x1 = args.get(f"{prefix}.x1", old_x1)
        y1 = args.get(f"{prefix}.y1", old_y1)
        display = state.display_a if state.mode == "complex" else state.display
        assert display is not None
        dh, dw = display.shape[:2]
        ps = state.pixel_size
        max_x, max_y = (dw - 1) * ps, (dh - 1) * ps
        new_p0 = (float(np.clip(x0, 0, max_x)), float(np.clip(y0, 0, max_y)))
        new_p1 = (float(np.clip(x1, 0, max_x)), float(np.clip(y1, 0, max_y)))
        if (abs(new_p0[0] - old_x0) < POS_TOL and abs(new_p0[1] - old_y0) < POS_TOL
                and abs(new_p1[0] - old_x1) < POS_TOL and abs(new_p1[1] - old_y1) < POS_TOL):
            return False
        state.endpoints = (new_p0, new_p1)
        return True

    async def _on_relayout(self, event) -> None:
        args = event.args or {}
        # In complex mode there are two independently-editable shapes (one
        # per subplot); either one moving must mirror onto the other, same
        # as the desktop's _on_endpoints_dragged swap-copy between panels.
        # CRITICAL: calling run_plot_method("relayout", ...) below to push
        # that mirror is itself a real Plotly relayout — it fires another
        # plotly_relayout event right back at this handler. Without the
        # unchanged-position check in _apply_endpoints_from_args, that echo
        # looks like new input, gets mirrored again, and so on forever
        # (reproduced: a single drag produced a runaway climbing count of
        # relayout events with the mirrored shape never settling). Pushing
        # only the OTHER shape (not re-pushing the one the user actually
        # dragged) plus that unchanged-position check is what breaks the
        # cycle: the echo's reported position always matches state exactly,
        # so the second call returns False and nothing re-fires.
        moved_shape = 0 if self._apply_endpoints_from_args(args, 0) else (
            1 if self.state.mode == "complex" and self._apply_endpoints_from_args(args, 1) else None
        )
        if moved_shape is None:
            return
        if self.state.mode == "complex":
            other = 1 - moved_shape
            (x0, y0), (x1, y1) = self.state.endpoints
            await self.image_plot.run_plot_method(
                "relayout", {f"shapes[{other}].x0": x0, f"shapes[{other}].y0": y0,
                             f"shapes[{other}].x1": x1, f"shapes[{other}].y1": y1},
            )
        await self._sync_markers()
        self._render_profile()

    async def _on_click(self, event) -> None:
        if self.state.mode != "complex":
            return
        points = (event.args or {}).get("points") or []
        if not points:
            return
        curve = points[0].get("curveNumber")
        if curve is None:
            return
        panel = 0 if curve in (0, 2) else 1
        if panel == self.state.active_panel:
            return
        self.state.active_panel = panel
        self._sync_controls()
        self._render_profile()
        self._on_active_panel_change()

    async def _apply_colormap(self) -> None:
        state = self.state
        state.colormap_base = self.colormap_select.value
        state.colormap_reverse = self.reverse_checkbox.value
        scale = _colormap_scale(state)
        indices = [0, 1] if state.mode == "complex" else [0]
        await self.image_plot.run_plot_method(
            "restyle",
            {"colorscale": [scale] * len(indices), "reversescale": [state.colormap_reverse] * len(indices)},
            indices,
        )

    async def _apply_pair(self) -> None:
        state = self.state
        if self.pair_select.value == state.pair:
            return
        state.pair = self.pair_select.value
        assert state.array is not None
        h, w = state.array.shape[:2]
        stride = limits.stride_for(h * w, _SERVE_IMAGE_MAX_PIXELS)
        strided = state.array[::stride, ::stride]
        self._project_complex_pair(strided)
        self._full_render()
        self._on_clim_change(*self.get_clim())

    async def _apply_clim(self) -> None:
        # ui.number already gives float | None — no manual parsing needed.
        state = self.state
        vmin = self.vmin_input.value
        vmax = self.vmax_input.value
        if state.mode == "complex":
            if state.active_panel == 0:
                state.clim_a = (vmin, vmax)
            else:
                state.clim_b = (vmin, vmax)
            trace_index = state.active_panel
        else:
            state.clim = (vmin, vmax)
            trace_index = 0
        await self.image_plot.run_plot_method("restyle", {"zmin": [vmin], "zmax": [vmax]}, [trace_index])
        self._on_clim_change(*self.get_clim())

    async def _reset_clim(self) -> None:
        state = self.state
        if state.mode == "complex":
            a, b = complexproj.IMAGE_PAIRS[state.pair]
            comp = a if state.active_panel == 0 else b
            display = _active_display(state)
            new_clim = (-np.pi, np.pi) if comp == "Angle" else _default_clim(display)
            if state.active_panel == 0:
                state.clim_a = new_clim
            else:
                state.clim_b = new_clim
            trace_index = state.active_panel
        else:
            assert state.display is not None
            new_clim = _default_clim(state.display)
            state.clim = new_clim
            trace_index = 0
        vmin, vmax = new_clim
        self._sync_controls()
        await self.image_plot.run_plot_method("restyle", {"zmin": [vmin], "zmax": [vmax]}, [trace_index])
        self._on_clim_change(*self.get_clim())

    def set_clim_from_histogram(self, vmin: float, vmax: float) -> None:
        """Apply a clim dragged on the Histogram's marker lines — silent sink,
        no _on_clim_change callback (the histogram's own markers are already
        in the right place; echoing back would just re-trigger itself)."""
        state = self.state
        if state.mode == "rgb":
            return
        if state.mode == "complex":
            if state.active_panel == 0:
                state.clim_a = (vmin, vmax)
            else:
                state.clim_b = (vmin, vmax)
            trace_index = state.active_panel
        else:
            state.clim = (vmin, vmax)
            trace_index = 0
        self.vmin_input.value = vmin
        self.vmax_input.value = vmax
        self.image_plot.run_plot_method("restyle", {"zmin": [vmin], "zmax": [vmax]}, [trace_index])
