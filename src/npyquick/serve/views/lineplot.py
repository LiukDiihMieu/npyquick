# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 LiukDiihMieu

"""Line Plot view. Ported from views/lineplot.py's LineplotCanvas/LineplotView.

Scroll = zoom x only, Shift+scroll = zoom y only — Plotly's own scrollZoom
has no modifier-key-selectable axis, so this is a hand-rolled `wheel` DOM
handler (config.scrollZoom is left off to avoid it double-handling the same
event). dragmode="pan" gives plain click-drag panning like the desktop.

Uses go.Scatter (SVG), not go.Scattergl (WebGL): a user hit "WebGL is not
supported by your browser" even though a plain WebGL feature-detection page
said otherwise in the same browser — WebGL context creation can fail in a
given tab/session (GPU sandboxing, remote-desktop/VNC rendering without GPU
passthrough, an exhausted context limit, ...) independently of whether the
browser engine supports WebGL in general. SVG has no such dependency; the
tradeoff is slower rendering at the extreme end of LINEPLOT_MAX_POINTS, which
is an acceptable cost for "always renders" over "renders fast until it
silently doesn't."
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import plotly.graph_objects as go
from nicegui import ui

from npyquick.core import limits
from npyquick.core.stats import ArrayStats, array_stats, is_real_numeric
from npyquick.serve.views._shared import empty_plotly_figure


class LineplotState:
    def __init__(self) -> None:
        self.mode: str = "1d"  # "1d" | "xy"
        self.col_xy: bool = False  # True for (N, 2); False for (2, N) or 1D
        self.stride: int = 1
        self.x_disp: np.ndarray | None = None
        self.y_disp: np.ndarray | None = None
        self.n_total: int = 0
        self.n_used: int = 0
        self.log_x: bool = False
        self.log_y: bool = False


def _lineplot_figure(state: LineplotState) -> dict:
    assert state.x_disp is not None and state.y_disp is not None
    x_label = "x" if state.mode == "xy" else "index"
    hover_label = "x" if state.mode == "xy" else "idx"
    fig = go.Figure(data=[go.Scatter(
        # width=1.2 was a direct carry-over of the desktop's matplotlib
        # lw=1.2 — but matplotlib linewidths are in points, Plotly's are in
        # CSS pixels, and the two aren't equivalent, so the literal number
        # rendered visibly thinner here than on the desktop.
        x=state.x_disp, y=state.y_disp, mode="lines", line={"color": "steelblue", "width": 5},
        hovertemplate=f"{hover_label}=%{{x}}<br>val=%{{y}}<extra></extra>",
    )])
    fig.update_layout(
        xaxis={"title": x_label, "type": "log" if state.log_x else "linear"},
        yaxis={"title": "Value", "type": "log" if state.log_y else "linear"},
        dragmode="pan",
        showlegend=False,
        margin={"l": 50, "r": 20, "t": 20, "b": 40},
    )
    d = fig.to_plotly_json()
    # scrollZoom deliberately off: the shift-for-y-axis wheel handler wired in
    # LineplotView.__init__ replaces it entirely, so Plotly's own wheel-zoom
    # would otherwise double-handle the same event. responsive=False: see the
    # matching comment in serve/views/_shared.py's with_plotly_config — this
    # view is also hidden/shown via set_data()/hide(), so it's equally
    # exposed to NiceGUI's crash-prone auto-resize-on-any-DOM-change behavior.
    d["config"] = {"scrollZoom": False, "responsive": False}
    return d


class LineplotView:
    def __init__(self) -> None:
        self.state = LineplotState()

        with ui.row().classes("items-center gap-2") as self.controls:
            self.log_x_checkbox = ui.checkbox("Log X")
            self.log_y_checkbox = ui.checkbox("Log Y")
            self.reset_btn = ui.button("Reset")
        self.controls.set_visibility(False)

        self.stats_label = ui.label()
        self.sample_label = ui.label().classes("text-amber-600")
        self.sample_label.set_visibility(False)
        self.anomaly_label = ui.label().classes("text-red-500")
        self.anomaly_label.set_visibility(False)

        self.line_plot = ui.plotly(empty_plotly_figure()).classes("w-full").style("height: 400px")
        # Hidden until the first successful set_data — see the matching
        # comment in serve/views/image.py for why (no tabbed navigation yet,
        # so a visible-but-empty plot for an unsupported dtype/shape reads
        # as "stuck" rather than "not applicable").
        self.line_plot.set_visibility(False)

        self.log_x_checkbox.on_value_change(self._apply_log_x)
        self.log_y_checkbox.on_value_change(self._apply_log_y)
        self.reset_btn.on_click(self._reset_zoom)

        # Pure client-side: no Python round trip for a wheel zoom. getElement()
        # returns the Vue component instance for the plotly.js wrapper, which
        # exposes the mounted plot div as `.$el` and the loaded Plotly module
        # as `.Plotly` (see serve/views/image.py's docstring for the same
        # pattern used elsewhere in this app). p2l/l2p (pixel<->data) are the
        # axis object's own conversion methods, same ones used for screen-px
        # math throughout this app's test/verification tooling.
        self.line_plot.on(
            "wheel", None,
            js_handler=f"""(event) => {{
                event.preventDefault();
                const el = getElement("{self.line_plot.id}");
                const gd = el.$el;
                const rect = gd.getBoundingClientRect();
                const fl = gd._fullLayout;
                const xa = fl.xaxis, ya = fl.yaxis;
                const factor = event.deltaY < 0 ? 0.8 : 1.25;
                if (event.shiftKey) {{
                    const yc = ya.p2l(event.clientY - rect.top - ya._offset);
                    const yl = ya.range;
                    const newYl = [yc + (yl[0] - yc) * factor, yc + (yl[1] - yc) * factor];
                    el.Plotly.relayout(gd, {{"yaxis.range": newYl}});
                }} else {{
                    const xc = xa.p2l(event.clientX - rect.left - xa._offset);
                    const xl = xa.range;
                    const newXl = [xc + (xl[0] - xc) * factor, xc + (xl[1] - xc) * factor];
                    el.Plotly.relayout(gd, {{"xaxis.range": newXl}});
                }}
            }}""",
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def hide(self) -> None:
        """See ImageView.hide's docstring for why this exists and who calls it."""
        self.controls.set_visibility(False)
        self.line_plot.set_visibility(False)
        self.stats_label.text = ""
        self.sample_label.set_visibility(False)
        self.anomaly_label.set_visibility(False)

    def set_data(self, array: np.ndarray, stats: ArrayStats | None = None) -> str | None:
        self.hide()
        if not is_real_numeric(array):
            return f"Line Plot doesn't support dtype {array.dtype}."

        if array.ndim == 1:
            mode, col_xy, ok = "1d", False, array.size > 0
        elif array.ndim == 2 and array.shape[0] == 2:
            mode, col_xy, ok = "xy", False, array.shape[1] > 2  # (2, N) row-based x-y
        elif array.ndim == 2 and array.shape[1] == 2:
            mode, col_xy, ok = "xy", True, array.shape[0] > 2  # (N, 2) column-based x-y
        else:
            ok = False
        if not ok:
            return f"Line Plot doesn't support shape {array.shape} yet."

        state = self.state
        state.mode, state.col_xy = mode, col_xy
        n = array.shape[0] if col_xy else array.shape[-1]
        # Downsample before any astype so a memmap stays lazy — full-res is
        # never needed again since a strided sample's values are already
        # exact (not interpolated/averaged), matching the desktop's approach.
        stride = limits.downsample_stride(n, limits.LINEPLOT_MAX_POINTS)
        state.stride = stride
        state.n_total = n
        state.n_used = (n + stride - 1) // stride

        if mode == "xy":
            if col_xy:
                y_disp = np.asarray(array[::stride, 1], dtype=float)
                x_disp = np.asarray(array[::stride, 0], dtype=float)
            else:
                y_disp = np.asarray(array[1, ::stride], dtype=float)
                x_disp = np.asarray(array[0, ::stride], dtype=float)
        else:
            y_disp = np.asarray(array[::stride], dtype=float)
            x_disp = np.arange(0, n, stride, dtype=float)
        state.x_disp, state.y_disp = x_disp, y_disp

        # Auto-disable (and uncheck) log axes with no positive values, same as
        # the desktop — log scale can't show non-positive values at all.
        x_has_pos = bool(np.any(x_disp > 0))
        y_has_pos = bool(np.any(y_disp > 0))
        self.log_x_checkbox.set_enabled(x_has_pos)
        self.log_y_checkbox.set_enabled(y_has_pos)
        if not x_has_pos and state.log_x:
            state.log_x = False
            self.log_x_checkbox.value = False
        if not y_has_pos and state.log_y:
            state.log_y = False
            self.log_y_checkbox.value = False

        self.controls.set_visibility(True)
        self.line_plot.set_visibility(True)
        self.line_plot.figure = _lineplot_figure(state)
        self.line_plot.update()

        # Intentionally ignores full-array stats from the caller: this view
        # shows y-values-only stats, recomputed on the y column/row, not
        # whatever stats the caller computed over the whole loaded array.
        y_full = array if array.ndim == 1 else (array[:, 1] if col_xy else array[1])
        y_stats = array_stats(y_full)
        if y_stats is not None and y_stats.finite_min is not None:
            self.stats_label.text = f"min {y_stats.finite_min:.4g}  max {y_stats.finite_max:.4g}"
        else:
            self.stats_label.text = "no finite values"

        sampled = state.n_used < state.n_total
        if sampled:
            self.sample_label.text = f"sampled {state.n_used:,} / {state.n_total:,}"
        self.sample_label.set_visibility(sampled)

        has_anomaly = y_stats is not None and y_stats.has_anomaly
        self.anomaly_label.text = y_stats.anomaly_str() if has_anomaly else ""
        self.anomaly_label.set_visibility(has_anomaly)
        return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _apply_log_x(self) -> None:
        self.state.log_x = self.log_x_checkbox.value
        await self.line_plot.run_plot_method(
            "relayout", {"xaxis.type": "log" if self.state.log_x else "linear"},
        )

    async def _apply_log_y(self) -> None:
        self.state.log_y = self.log_y_checkbox.value
        await self.line_plot.run_plot_method(
            "relayout", {"yaxis.type": "log" if self.state.log_y else "linear"},
        )

    async def _reset_zoom(self) -> None:
        await self.line_plot.run_plot_method(
            "relayout", {"xaxis.autorange": True, "yaxis.autorange": True},
        )
