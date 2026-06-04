from __future__ import annotations

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from ..core.stats import array_stats
from .base import BaseView

_BIN_OPTIONS = ["auto", "64", "128", "256", "512"]


class HistogramCanvas(FigureCanvas):
    def __init__(self) -> None:
        self._fig = Figure(constrained_layout=True)
        super().__init__(self._fig)
        self._ax = self._fig.add_subplot(111)
        self._on_status: callable = lambda _: None
        self._idle_status: str = ""
        self._n_bins: int | str = "auto"
        self._log: bool = False
        self._array: np.ndarray | None = None
        self._edges: np.ndarray | None = None
        self._counts: np.ndarray | None = None
        self._clim: tuple[float, float] | None = None
        self._vline_lo = None
        self._vline_hi = None

        self.mpl_connect("motion_notify_event", self._on_motion)
        self.mpl_connect("axes_leave_event", self._on_axes_leave)

    def set_on_status(self, cb: callable) -> None:
        self._on_status = cb

    def set_idle_status(self, s: str) -> None:
        self._idle_status = s

    def plot(self, array: np.ndarray) -> None:
        self._array = array
        flat = array.flatten()
        finite = flat[np.isfinite(flat)] if np.issubdtype(array.dtype, np.inexact) else flat

        self._ax.cla()
        self._ax.set_xlabel("Value")
        self._ax.set_ylabel("Count")
        self._edges = None
        self._counts = None
        self._vline_lo = None
        self._vline_hi = None

        if finite.size == 0:
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
                vmin, vmax = self._clim
                self._vline_lo = self._ax.axvline(
                    vmin, color="tomato", lw=1.5, ls="--", alpha=0.85, zorder=5
                )
                self._vline_hi = self._ax.axvline(
                    vmax, color="tomato", lw=1.5, ls="--", alpha=0.85, zorder=5
                )

        self._ax.set_yscale("log" if self._log else "linear")
        self.draw_idle()

    def set_bins(self, n: int | str) -> None:
        self._n_bins = n
        if self._array is not None:
            self.plot(self._array)

    def set_log_scale(self, enable: bool) -> None:
        self._log = enable
        if self._array is not None:
            self.plot(self._array)

    def set_clim_marker(self, vmin: float | None, vmax: float | None) -> None:
        """Store clim without redrawing — called before plot()."""
        self._clim = (vmin, vmax) if vmin is not None and vmax is not None else None

    def update_clim_marker(self, vmin: float | None, vmax: float | None) -> None:
        """Live-update vlines on an already-rendered histogram."""
        self._clim = (vmin, vmax) if vmin is not None and vmax is not None else None
        for line in (self._vline_lo, self._vline_hi):
            if line is not None:
                line.remove()
        self._vline_lo = self._vline_hi = None
        if self._clim is not None and self._edges is not None:
            vmin, vmax = self._clim
            self._vline_lo = self._ax.axvline(
                vmin, color="tomato", lw=1.5, ls="--", alpha=0.85, zorder=5
            )
            self._vline_hi = self._ax.axvline(
                vmax, color="tomato", lw=1.5, ls="--", alpha=0.85, zorder=5
            )
        self.draw_idle()

    def _on_motion(self, ev) -> None:
        if ev.inaxes is not self._ax or self._edges is None or ev.xdata is None:
            return
        idx = min(int(np.searchsorted(self._edges[1:], ev.xdata)), len(self._counts) - 1)
        lo, hi = self._edges[idx], self._edges[idx + 1]
        self._on_status(f"bin [{lo:.4g}, {hi:.4g})  count: {self._counts[idx]}")

    def _on_axes_leave(self, ev) -> None:
        self._on_status(self._idle_status)


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

        self._stats_label = QLabel()
        self._stats_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

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
        ctrl_layout.addStretch()
        ctrl_layout.addWidget(self._stats_label)
        ctrl_layout.addSpacing(8)
        ctrl_layout.addWidget(self._anomaly_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(ctrl)
        layout.addWidget(self._canvas)

    @classmethod
    def can_handle(cls, array: np.ndarray) -> bool:
        return np.issubdtype(array.dtype, np.number) and array.size > 0

    def set_data(self, array: np.ndarray) -> None:
        stats = array_stats(array)

        if stats is not None and stats.finite_min is not None:
            flat = array.flatten()
            finite = flat[np.isfinite(flat)] if np.issubdtype(array.dtype, np.inexact) else flat
            mean = float(np.mean(finite))
            std = float(np.std(finite))
            p1, p50, p99 = (float(v) for v in np.percentile(finite, [1, 50, 99]))
            stats_str = (
                f"min {stats.finite_min:.4g}  max {stats.finite_max:.4g}"
                f"  mean {mean:.4g}  std {std:.4g}"
                f"  |  p1 {p1:.4g}  p50 {p50:.4g}  p99 {p99:.4g}"
            )
        else:
            stats_str = "no finite values"

        self._stats_label.setText(stats_str)
        self._status = f"shape {array.shape}  dtype {array.dtype}  |  {stats_str}"

        if stats is not None and stats.has_anomaly:
            self._anomaly_label.setText(stats.anomaly_str())
            self._anomaly_label.setVisible(True)
        else:
            self._anomaly_label.setVisible(False)

        self._canvas.set_clim_marker(None, None)  # reset; app.py syncs from ImageView
        self._canvas.set_idle_status(self._status)
        self._canvas.plot(array)

    def update_clim_marker(self, vmin: float | None, vmax: float | None) -> None:
        self._canvas.update_clim_marker(vmin, vmax)

    def refresh_status(self) -> None:
        self._on_status(self._status)

    def set_on_status(self, cb: callable) -> None:
        super().set_on_status(cb)
        self._canvas.set_on_status(cb)

    def _on_bins_changed(self, text: str) -> None:
        self._canvas.set_bins(text if text == "auto" else int(text))
