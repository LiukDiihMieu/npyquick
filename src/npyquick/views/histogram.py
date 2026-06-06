# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from ..core import limits
from ..core.stats import ArrayStats, array_stats, is_real_numeric
from .base import BaseView, ExportableMixin

_BIN_OPTIONS = ["auto", "64", "128", "256", "512"]


def finite_sample(array: np.ndarray) -> tuple[np.ndarray, int, int]:
    """Return (finite_values, n_total, n_used) for histogram and statistics.

    Subsampling is driven by element count against HIST_MAX_SAMPLES (a compute
    budget independent of the byte-based I/O threshold), applied before the
    finite mask so a memmap is never fully read. downsample_stride returns 1
    when within budget. n_used is the sample size before masking.
    """
    flat = array.reshape(-1)
    n_total = flat.size
    stride = limits.downsample_stride(n_total, limits.HIST_MAX_SAMPLES)
    sample = np.asarray(flat[::stride])
    n_used = sample.size
    if np.issubdtype(array.dtype, np.inexact):
        finite = sample[np.isfinite(sample)]
    else:
        finite = sample
    return finite, n_total, n_used


class HistogramCanvas(ExportableMixin, FigureCanvas):
    panel_name = "Histogram"
    def __init__(self) -> None:
        self._fig = Figure(constrained_layout=True)
        super().__init__(self._fig)
        self._ax = self._fig.add_subplot(111)
        self._on_status: callable = lambda _: None
        self._idle_status: str = ""
        self._n_bins: int | str = "auto"
        self._log: bool = False
        self._array: np.ndarray | None = None
        self._finite: np.ndarray | None = None
        self._n_total: int = 0
        self._n_used: int = 0
        self._edges: np.ndarray | None = None
        self._counts: np.ndarray | None = None
        self._clim: tuple[float, float] | None = None
        self._vline_lo = None
        self._vline_hi = None
        self._vtext_lo = None
        self._vtext_hi = None

        self.mpl_connect("button_press_event", self._on_press)
        self.mpl_connect("motion_notify_event", self._on_motion)
        self.mpl_connect("axes_leave_event", self._on_axes_leave)
        self.mpl_connect("scroll_event", self._on_scroll)

    def set_on_status(self, cb: callable) -> None:
        self._on_status = cb

    def set_idle_status(self, s: str) -> None:
        self._idle_status = s

    def plot(self, array: np.ndarray) -> None:
        self._array = array
        finite, self._n_total, self._n_used = finite_sample(array)
        self._finite = finite
        self._render()

    def _render(self) -> None:
        """Redraw bars from the cached _finite sample (no re-sampling)."""
        self._ax.cla()
        self._ax.set_xlabel("Value")
        self._ax.set_ylabel("Count")
        self._edges = None
        self._counts = None
        self._vline_lo = None
        self._vline_hi = None
        self._vtext_lo = None
        self._vtext_hi = None
        finite = self._finite

        if finite is None or finite.size == 0:
            self._ax.text(
                0.5, 0.5, "No finite values",
                transform=self._ax.transAxes, ha="center", va="center",
                color="gray", fontsize=12,
            )
        else:
            bins = self._n_bins if self._n_bins == "auto" else int(self._n_bins)
            counts, edges = np.histogram(finite, bins=bins)
            self._counts = counts
            self._edges = edges
            self._ax.bar(
                edges[:-1], counts, width=np.diff(edges), align="edge",
                color="steelblue", edgecolor="none",
            )
            if self._clim is not None:
                self._draw_clim_markers(*self._clim)

        self._ax.set_yscale("log" if self._log else "linear")
        self.draw_idle()

    def _draw_clim_markers(self, vmin: float, vmax: float) -> None:
        self._vline_lo = self._ax.axvline(
            vmin, color="tomato", lw=1.5, ls="--", alpha=0.85, zorder=5
        )
        self._vline_hi = self._ax.axvline(
            vmax, color="tomato", lw=1.5, ls="--", alpha=0.85, zorder=5
        )
        tr = self._ax.get_xaxis_transform()
        self._vtext_lo = self._ax.text(
            vmin, 0.98, "vmin", transform=tr,
            ha="center", va="top", color="tomato", fontsize=7,
        )
        self._vtext_hi = self._ax.text(
            vmax, 0.98, "vmax", transform=tr,
            ha="center", va="top", color="tomato", fontsize=7,
        )

    def set_bins(self, n: int | str) -> None:
        self._n_bins = n
        if self._array is not None:
            self._render()  # re-bin the cached sample; no re-sampling

    def set_log_scale(self, enable: bool) -> None:
        self._log = enable
        if self._array is not None:
            # Only the y-axis scale changes — no need to re-sample or re-bin.
            self._ax.set_yscale("log" if enable else "linear")
            self.draw_idle()

    def set_clim_marker(self, vmin: float | None, vmax: float | None) -> None:
        """Store clim without redrawing — called before plot()."""
        self._clim = (vmin, vmax) if vmin is not None and vmax is not None else None

    def update_clim_marker(self, vmin: float | None, vmax: float | None) -> None:
        """Live-update vlines on an already-rendered histogram."""
        self._clim = (vmin, vmax) if vmin is not None and vmax is not None else None
        for artist in (self._vline_lo, self._vline_hi, self._vtext_lo, self._vtext_hi):
            if artist is not None:
                artist.remove()
        self._vline_lo = self._vline_hi = None
        self._vtext_lo = self._vtext_hi = None
        if self._clim is not None and self._edges is not None:
            self._draw_clim_markers(*self._clim)
        self.draw_idle()

    def _on_press(self, ev) -> None:
        if ev.dblclick and ev.inaxes is self._ax:
            self.xlim_full()

    def _on_motion(self, ev) -> None:
        if ev.inaxes is not self._ax or self._edges is None or ev.xdata is None:
            return
        idx = min(int(np.searchsorted(self._edges[1:], ev.xdata)), len(self._counts) - 1)
        lo, hi = self._edges[idx], self._edges[idx + 1]
        self._on_status(f"bin [{lo:.4g}, {hi:.4g})  count: {self._counts[idx]}")

    def _on_axes_leave(self, ev) -> None:
        self._on_status(self._idle_status)

    def _on_scroll(self, ev) -> None:
        if ev.inaxes is not self._ax or self._edges is None:
            return
        factor = 0.8 if ev.step > 0 else 1.25
        xc = ev.xdata
        xl = self._ax.get_xlim()
        self._ax.set_xlim(xc + (xl[0] - xc) * factor, xc + (xl[1] - xc) * factor)
        self.draw_idle()

    def xlim_full(self) -> None:
        if self._edges is None:
            return
        self._ax.set_xlim(self._edges[0], self._edges[-1])
        self.draw_idle()

    def xlim_robust(self) -> None:
        if self._finite is None or self._finite.size < 2:
            return
        lo, hi = np.percentile(self._finite, [2, 98])
        if lo == hi:
            delta = abs(lo) * 0.05 if lo != 0 else 0.5
            lo, hi = lo - delta, hi + delta
        self._ax.set_xlim(lo, hi)
        self.draw_idle()


class HistogramView(BaseView):
    VIEW_ID = "histogram"
    VIEW_NAME = "Histogram"

    def __init__(self) -> None:
        super().__init__()
        self._status: str = ""
        self._canvas = HistogramCanvas()

        self._bins_combo = QComboBox()
        self._bins_combo.addItems(_BIN_OPTIONS)
        self._bins_combo.setFixedWidth(80)
        self._bins_combo.currentTextChanged.connect(self._on_bins_changed)

        self._log_check = QCheckBox("Log scale")
        self._log_check.toggled.connect(self._canvas.set_log_scale)

        self._full_btn = QPushButton("Full")
        self._full_btn.setFixedWidth(48)
        self._full_btn.clicked.connect(self._canvas.xlim_full)

        self._robust_btn = QPushButton("Robust")
        self._robust_btn.setFixedWidth(56)
        self._robust_btn.setToolTip("Set x-range to p2–p98")
        self._robust_btn.clicked.connect(self._canvas.xlim_robust)

        self._stats_label = QLabel()
        self._stats_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._sample_label = QLabel()
        self._sample_label.setStyleSheet("color: #b8860b;")
        self._sample_label.setVisible(False)

        self._anomaly_label = QLabel()
        self._anomaly_label.setStyleSheet("color: red;")
        self._anomaly_label.setVisible(False)

        ctrl = QWidget()
        ctrl_layout = QHBoxLayout(ctrl)
        ctrl_layout.setContentsMargins(6, 3, 6, 3)
        ctrl_layout.addWidget(QLabel("Bins:"))
        ctrl_layout.addWidget(self._bins_combo)
        ctrl_layout.addSpacing(12)
        ctrl_layout.addWidget(self._log_check)
        ctrl_layout.addSpacing(16)
        ctrl_layout.addWidget(QLabel("X range:"))
        ctrl_layout.addWidget(self._full_btn)
        ctrl_layout.addWidget(self._robust_btn)
        ctrl_layout.addStretch()
        ctrl_layout.addWidget(self._stats_label)
        ctrl_layout.addSpacing(8)
        ctrl_layout.addWidget(self._sample_label)
        ctrl_layout.addSpacing(8)
        ctrl_layout.addWidget(self._anomaly_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(ctrl)
        layout.addWidget(self._canvas)

    @classmethod
    def can_handle(cls, array: np.ndarray) -> bool:
        return is_real_numeric(array) and array.size > 0

    def set_data(self, array: np.ndarray, stats: ArrayStats | None = None) -> None:
        self._canvas.set_clim_marker(None, None)  # reset; app.py syncs from ImageView
        self._canvas.plot(array)  # samples once; stores _finite / _n_total / _n_used

        finite = self._canvas._finite
        n_total = self._canvas._n_total
        n_used = self._canvas._n_used

        if finite is not None and finite.size > 0:
            fmin, fmax = float(finite.min()), float(finite.max())
            mean = float(np.mean(finite))
            std = float(np.std(finite))
            p1, p50, p99 = (float(v) for v in np.percentile(finite, [1, 50, 99]))
            stats_str = (
                f"min {fmin:.4g}  max {fmax:.4g}"
                f"  mean {mean:.4g}  std {std:.4g}"
                f"  |  p1 {p1:.4g}  p50 {p50:.4g}  p99 {p99:.4g}"
            )
        else:
            stats_str = "no finite values"
        self._stats_label.setText(stats_str)

        sampled = n_used < n_total
        if sampled:
            self._sample_label.setText(f"sampled {n_used:,} / {n_total:,}")
            self._sample_label.setVisible(True)
        else:
            self._sample_label.setVisible(False)

        self._status = f"shape {array.shape}  dtype {array.dtype}  |  {stats_str}"
        if sampled:
            self._status += "  (sampled)"

        if stats is None:
            stats = array_stats(array)
        if stats is not None and stats.has_anomaly:
            self._anomaly_label.setText(stats.anomaly_str())
            self._anomaly_label.setVisible(True)
        else:
            self._anomaly_label.setVisible(False)

        self._canvas.set_idle_status(self._status)

    def update_clim_marker(self, vmin: float | None, vmax: float | None) -> None:
        self._canvas.update_clim_marker(vmin, vmax)

    def refresh_status(self) -> None:
        self._on_status(self._status)

    def export_targets(self):
        return [("Histogram", self._canvas._export_figure)]

    def set_on_status(self, cb: callable) -> None:
        super().set_on_status(cb)
        self._canvas.set_on_status(cb)

    def _on_bins_changed(self, text: str) -> None:
        self._canvas.set_bins(text if text == "auto" else int(text))
