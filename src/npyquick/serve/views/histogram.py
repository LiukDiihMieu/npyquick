# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 LiukDiihMieu

"""Histogram view. Ported from views/histogram.py's HistogramCanvas/HistogramView.

The vmin/vmax clim markers are draggable vertical shapes, using the same
config.edits.shapePosition + self-relayout-echo pattern the Image view's
cross-section drag uses (see serve/views/image.py's docstring/history) — a
drag can independently move one endpoint of the "line" shape and tilt it since
Plotly doesn't constrain a shape to stay vertical, so every relayout pushes a
corrected, exactly-vertical position back, which doubles as the idempotency
check that stops the echo from re-triggering itself forever.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import plotly.graph_objects as go
from nicegui import ui

from npyquick.core import complexproj, limits
from npyquick.core.stats import ArrayStats, array_stats, is_real_numeric
from npyquick.serve.views._shared import POS_TOL, empty_plotly_figure, shape_touched, with_plotly_config

_BIN_OPTIONS = ["auto", "64", "128", "256", "512"]
_MARKER_COLOR = "tomato"


def _finite_sample(array: np.ndarray) -> tuple[np.ndarray, int, int]:
    """Return (finite_values, n_total, n_used). Ported from
    views/histogram.py:finite_sample — see that docstring for why sampling
    happens before the finite mask (memmap-safety) and why ravel(order="K")
    matters (core.limits.sampled_flat_view)."""
    sample, n_total, n_used = limits.sampled_flat_view(array, limits.HIST_MAX_SAMPLES)
    if np.issubdtype(array.dtype, np.inexact):
        finite = sample[np.isfinite(sample)]
    else:
        finite = sample
    return finite, n_total, n_used


class HistogramState:
    def __init__(self) -> None:
        self.n_bins: str | int = "auto"
        self.log: bool = False
        self.array: np.ndarray | None = None
        self.complex_sample: np.ndarray | None = None
        self.component: str = complexproj.DEFAULT_HIST
        self.finite: np.ndarray | None = None
        self.n_total: int = 0
        self.n_used: int = 0
        self.edges: np.ndarray | None = None
        self.counts: np.ndarray | None = None
        self.clim: tuple[float, float] | None = None


def _compute_histogram(finite: np.ndarray, n_bins: str | int) -> tuple[np.ndarray, np.ndarray]:
    try:
        counts, edges = np.histogram(finite, bins=n_bins)
    except ValueError:
        # Near-constant data (e.g. unit-magnitude phase data) has a range too
        # small to split into many finite-width bins; one bar is the honest
        # result. (Exactly-constant data is handled by numpy.)
        counts, edges = np.histogram(finite, bins=1)
    return counts, edges


def _clim_shapes(clim: tuple[float, float] | None) -> list[dict]:
    if clim is None:
        return []
    vmin, vmax = clim

    def vline(x: float) -> dict:
        return {
            "type": "line", "xref": "x", "yref": "paper",
            "x0": x, "x1": x, "y0": 0, "y1": 1,
            "line": {"color": _MARKER_COLOR, "width": 1.5, "dash": "dash"},
        }

    return [vline(vmin), vline(vmax)]


def _clim_annotations(clim: tuple[float, float] | None) -> list[dict]:
    if clim is None:
        return []
    vmin, vmax = clim

    def label(x: float, text: str) -> dict:
        return {
            "x": x, "y": 1, "yref": "paper", "yanchor": "top", "text": text,
            "showarrow": False, "font": {"color": _MARKER_COLOR, "size": 10},
        }

    return [label(vmin, "vmin"), label(vmax, "vmax")]


def _histogram_figure(state: HistogramState) -> dict:
    finite = state.finite
    if finite is None or finite.size == 0:
        fig = go.Figure()
        fig.add_annotation(
            text="No finite values", xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False, font={"color": "gray", "size": 14},
        )
        state.edges = state.counts = None
    else:
        counts, edges = _compute_histogram(finite, state.n_bins)
        state.edges, state.counts = edges, counts
        centers = (edges[:-1] + edges[1:]) / 2
        widths = np.diff(edges)
        customdata = np.stack([edges[:-1], edges[1:]], axis=-1)
        bar = go.Bar(
            x=centers, y=counts, width=widths, marker={"color": "steelblue"},
            customdata=customdata,
            hovertemplate="bin [%{customdata[0]:.4g}, %{customdata[1]:.4g})<br>count: %{y}<extra></extra>",
        )
        fig = go.Figure(data=[bar])
        fig.update_layout(shapes=_clim_shapes(state.clim), annotations=_clim_annotations(state.clim))

    fig.update_layout(
        xaxis_title="Value", yaxis_title="Count",
        # fixedrange: the y-axis is just bar counts — panning/zooming it only
        # ever hides the bars or leaves whitespace, never something useful.
        yaxis={"type": "log" if state.log else "linear", "fixedrange": True},
        dragmode="pan",
        showlegend=False,
        margin={"l": 50, "r": 20, "t": 20, "b": 40},
    )
    return with_plotly_config(fig)


class HistogramView:
    def __init__(self) -> None:
        self.state = HistogramState()
        self._on_clim_dragged: Callable[[float, float], None] = lambda vmin, vmax: None

        with ui.row().classes("items-center gap-2") as self.controls:
            self.bins_select = ui.select(_BIN_OPTIONS, value="auto", label="Bins")
            self.log_checkbox = ui.checkbox("Log scale")
            # min-width: same floating-label-clips-to-value-width issue as
            # the Image view's Colormap select — see that file's comment.
            self.component_select = ui.select(
                complexproj.component_names(), value=self.state.component, label="Component",
            ).classes("min-w-[8rem]")
            self.full_btn = ui.button("Full")
            self.robust_btn = ui.button("Robust").tooltip("Set x-range to p2–p98")
        self.controls.set_visibility(False)
        self.component_select.set_visibility(False)

        self.stats_label = ui.label()
        self.sample_label = ui.label().classes("text-amber-600")
        self.sample_label.set_visibility(False)
        self.anomaly_label = ui.label().classes("text-red-500")
        self.anomaly_label.set_visibility(False)

        self.hist_plot = ui.plotly(empty_plotly_figure()).classes("w-full").style("height: 350px")
        # Hidden until the first successful set_data — see the matching
        # comment in serve/views/image.py for why (no tabbed navigation yet,
        # so a visible-but-empty plot for an unsupported dtype/shape reads
        # as "stuck" rather than "not applicable").
        self.hist_plot.set_visibility(False)

        self.bins_select.on_value_change(self._apply_bins)
        self.log_checkbox.on_value_change(self._apply_log)
        self.component_select.on_value_change(self._apply_component)
        self.full_btn.on_click(self._xlim_full)
        self.robust_btn.on_click(self._xlim_robust)
        self.hist_plot.on("plotly_relayout", self._on_relayout)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def set_on_clim_dragged(self, cb: Callable[[float, float], None]) -> None:
        self._on_clim_dragged = cb

    def hide(self) -> None:
        """See ImageView.hide's docstring for why this exists and who calls it."""
        self.controls.set_visibility(False)
        self.component_select.set_visibility(False)
        self.hist_plot.set_visibility(False)
        self.stats_label.text = ""
        self.sample_label.set_visibility(False)
        self.anomaly_label.set_visibility(False)

    def set_data(self, array: np.ndarray, stats: ArrayStats | None = None) -> str | None:
        self.hide()
        is_complex = np.issubdtype(array.dtype, np.complexfloating)
        if not (is_real_numeric(array) or is_complex) or array.size == 0:
            return f"Histogram doesn't support dtype {array.dtype} (or an empty array)."

        state = self.state
        state.clim = None  # reset; the orchestrator re-syncs from the Image view
        state.array = array
        if is_complex:
            sample, state.n_total, state.n_used = limits.sampled_flat_view(array, limits.HIST_MAX_SAMPLES)
            state.complex_sample = sample
            self._apply_component_from_state()
        else:
            state.complex_sample = None
            finite, state.n_total, state.n_used = _finite_sample(array)
            state.finite = finite

        self.component_select.set_visibility(is_complex)
        self.controls.set_visibility(True)
        self.hist_plot.set_visibility(True)
        self._full_render()

        if stats is None:
            stats = array_stats(array)
        if stats is not None and stats.has_anomaly:
            self.anomaly_label.text = stats.anomaly_str()
            self.anomaly_label.set_visibility(True)
        else:
            self.anomaly_label.set_visibility(False)
        return None

    def update_clim_marker(self, vmin: float | None, vmax: float | None) -> None:
        """Live-sync the vmin/vmax markers from the Image view's clim."""
        self.state.clim = (vmin, vmax) if vmin is not None and vmax is not None else None
        self.hist_plot.figure = _histogram_figure(self.state)
        self.hist_plot.update()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _apply_component_from_state(self) -> None:
        state = self.state
        assert state.complex_sample is not None
        projected = complexproj.project(state.complex_sample, state.component)
        state.finite = projected[np.isfinite(projected)]

    def _full_render(self) -> None:
        self.hist_plot.figure = _histogram_figure(self.state)
        self.hist_plot.update()
        self._update_stats_label()

    def _update_stats_label(self) -> None:
        state = self.state
        finite = state.finite
        if finite is not None and finite.size > 0:
            fmin, fmax = float(finite.min()), float(finite.max())
            mean, std = float(np.mean(finite)), float(np.std(finite))
            p1, p50, p99 = (float(v) for v in np.percentile(finite, [1, 50, 99]))
            text = (
                f"min {fmin:.4g}  max {fmax:.4g}  mean {mean:.4g}  std {std:.4g}"
                f"  |  p1 {p1:.4g}  p50 {p50:.4g}  p99 {p99:.4g}"
            )
        else:
            text = "no finite values"
        self.stats_label.text = text

        sampled = state.n_used < state.n_total
        if sampled:
            self.sample_label.text = f"sampled {state.n_used:,} / {state.n_total:,}"
        self.sample_label.set_visibility(sampled)

    async def _apply_bins(self) -> None:
        self.state.n_bins = self.bins_select.value if self.bins_select.value == "auto" else int(self.bins_select.value)
        self._full_render()  # re-bins the cached sample; no re-sampling

    async def _apply_log(self) -> None:
        self.state.log = self.log_checkbox.value
        await self.hist_plot.run_plot_method(
            "relayout", {"yaxis.type": "log" if self.state.log else "linear"},
        )

    async def _apply_component(self) -> None:
        if self.state.complex_sample is None:
            return
        self.state.component = self.component_select.value
        self._apply_component_from_state()  # re-projects the cached sample; no re-sampling
        self._full_render()

    async def _xlim_full(self) -> None:
        if self.state.edges is None:
            return
        await self.hist_plot.run_plot_method(
            "relayout", {"xaxis.range[0]": float(self.state.edges[0]), "xaxis.range[1]": float(self.state.edges[-1])},
        )

    async def _xlim_robust(self) -> None:
        finite = self.state.finite
        if finite is None or finite.size < 2:
            return
        lo, hi = (float(v) for v in np.percentile(finite, [2, 98]))
        if lo == hi:
            delta = abs(lo) * 0.05 if lo != 0 else 0.5
            lo, hi = lo - delta, hi + delta
        await self.hist_plot.run_plot_method("relayout", {"xaxis.range[0]": lo, "xaxis.range[1]": hi})

    def _clim_from_shape_args(self, args: dict, shape_index: int) -> float | None:
        """Read shapes[shape_index] out of a relayout event and return the new
        clim value for this marker, or None if nothing about it actually needs
        correcting.

        x0/x1 are averaged (a plain translate keeps them equal; if the user
        grabbed just one endpoint and tilted the line, this is a reasonable
        compromise — the caller snaps it back vertical regardless). y0/y1 are
        checked too, even though they don't feed the returned value: Plotly
        doesn't constrain this shape to stay vertical, so a mostly-vertical
        drag can change y0/y1 while barely touching x0/x1 (or not touching it
        at all) — that must still trigger a correction, or the marker is left
        not spanning the plot's full height. Returns None only when the event
        doesn't touch this shape at all, or reports exactly the position we
        last pushed ourselves (the echo of our own corrective relayout below,
        not new user input)."""
        prefix = f"shapes[{shape_index}]"
        if not shape_touched(args, shape_index, "x0", "x1", "y0", "y1") or self.state.clim is None:
            return None
        old = self.state.clim[shape_index]
        x0 = args.get(f"{prefix}.x0", old)
        x1 = args.get(f"{prefix}.x1", old)
        y0 = args.get(f"{prefix}.y0", 0.0)
        y1 = args.get(f"{prefix}.y1", 1.0)
        new_x = (x0 + x1) / 2.0
        x_changed = abs(new_x - old) > POS_TOL
        y_drifted = abs(y0) > POS_TOL or abs(y1 - 1.0) > POS_TOL
        if not x_changed and not y_drifted:
            return None
        return new_x

    async def _on_relayout(self, event) -> None:
        args = event.args or {}
        if self.state.clim is None:
            return
        vmin, vmax = self.state.clim
        new_vmin = self._clim_from_shape_args(args, 0)
        new_vmax = self._clim_from_shape_args(args, 1)
        if new_vmin is None and new_vmax is None:
            return
        eps = ((self.state.edges[-1] - self.state.edges[0]) * 1e-6
               if self.state.edges is not None else np.finfo(float).eps)
        if new_vmin is not None:
            vmin = min(new_vmin, vmax - eps)
        if new_vmax is not None:
            vmax = max(new_vmax, vmin + eps)
        self.state.clim = (vmin, vmax)
        # Push the corrected position back: x snapped to the (clamped) clim
        # value, y0/y1 always reset to the full paper height regardless of
        # what the drag did to them — this is what stops a vertical drag from
        # leaving the marker not spanning the plot, since the y-axis itself
        # isn't a meaningful place for vmin/vmax to move to. This also doubles
        # as the idempotency check above once its own echo comes back, same
        # pattern as the Image view's cross-section mirroring.
        await self.hist_plot.run_plot_method(
            "relayout", {
                "shapes[0].x0": vmin, "shapes[0].x1": vmin, "shapes[0].y0": 0, "shapes[0].y1": 1,
                "shapes[1].x0": vmax, "shapes[1].x1": vmax, "shapes[1].y0": 0, "shapes[1].y1": 1,
                "annotations[0].x": vmin, "annotations[1].x": vmax,
            },
        )
        self._on_clim_dragged(vmin, vmax)
