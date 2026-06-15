# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
    QVBoxLayout, QWidget,
)

from ..core import limits
from ..core.stats import ArrayStats, array_stats, is_real_numeric
from .base import BaseView, ExportableMixin


class LineplotCanvas(ExportableMixin, FigureCanvas):
    panel_name = "Line Plot"
    def __init__(self, on_status: callable) -> None:
        self._fig = Figure(constrained_layout=True)
        self._ax = self._fig.add_subplot(111)
        super().__init__(self._fig)

        self._on_status = on_status
        self._data: np.ndarray | None = None   # full-res (may be memmap)
        self._disp: np.ndarray | None = None   # float display array (maybe downsampled)
        self._x_disp: np.ndarray | None = None # x coords for _disp points
        self._stride: int = 1
        self._mode: str = "1d"                 # "1d" | "xy"
        self._col_xy: bool = False             # True when shape is (N, 2)
        self._log_x: bool = False
        self._log_y: bool = False
        self._hover_idx: int | None = None     # full-res index under cursor
        self._line = None                       # Line2D artist
        self._pan_start_px: tuple | None = None  # pixel coords at pan press
        self._pan_start_xl: tuple | None = None # xlim at pan press
        self._pan_start_yl: tuple | None = None # ylim at pan press
        self._on_selected: callable = lambda _: None

        self.mpl_connect("motion_notify_event", self._on_motion)
        self.mpl_connect("button_press_event", self._on_press)
        self.mpl_connect("button_release_event", self._on_release)
        self.mpl_connect("scroll_event", self._on_scroll)
        self.mpl_connect("axes_leave_event", self._on_axes_leave)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, data: np.ndarray) -> None:
        self._data = data
        self._col_xy = data.ndim == 2 and data.shape[1] == 2
        self._mode = "1d" if data.ndim == 1 else "xy"
        # n = number of data points (last axis for (2,N); first axis for (N,2))
        n = data.shape[0] if self._col_xy else data.shape[-1]

        # Downsample display array before any astype so a memmap stays lazy.
        s = limits.downsample_stride(n, limits.LINEPLOT_MAX_POINTS)
        self._stride = s

        if self._mode == "xy":
            if self._col_xy:
                y_sub = np.asarray(data[::s, 1], dtype=float)
                x_raw = np.asarray(data[::s, 0], dtype=float)
            else:
                y_sub = np.asarray(data[1, ::s], dtype=float)
                x_raw = np.asarray(data[0, ::s], dtype=float)
            self._x_disp = x_raw
        else:
            y_sub = np.asarray(data[::s], dtype=float)
            self._x_disp = np.arange(0, n, s, dtype=float)

        self._disp = y_sub

        self._ax.cla()
        self._ax.set_xlabel(self._x_label())
        self._ax.set_ylabel("Value")
        self._ax.set_xscale("log" if self._log_x else "linear")
        self._ax.set_yscale("log" if self._log_y else "linear")
        self._ax.grid(True, alpha=0.25)
        (self._line,) = self._ax.plot(self._x_disp, self._disp, lw=1.2, color="steelblue")
        self._hover_idx = None
        self.draw()

    def set_log_x(self, enable: bool) -> None:
        self._log_x = enable
        if enable:
            self._ax.set_xscale("log")
            # Clamp lower xlim to the smallest positive x so log scale is valid.
            if self._x_disp is not None:
                x_pos = self._x_disp[self._x_disp > 0]
                if x_pos.size > 0 and self._ax.get_xlim()[0] <= 0:
                    self._ax.set_xlim(float(x_pos.min()), self._ax.get_xlim()[1])
        else:
            self._ax.set_xscale("linear")
            self._reset_x_autoscale()
        self.draw_idle()

    def set_log_y(self, enable: bool) -> None:
        self._log_y = enable
        if enable:
            self._ax.set_yscale("log")
            # Clamp lower ylim to the smallest positive y so log scale is valid.
            if self._disp is not None:
                y_pos = self._disp[self._disp > 0]
                if y_pos.size > 0 and self._ax.get_ylim()[0] <= 0:
                    self._ax.set_ylim(float(y_pos.min()), self._ax.get_ylim()[1])
        else:
            self._ax.set_yscale("linear")
            self._reset_y_autoscale()
        self.draw_idle()

    def reset_zoom(self) -> None:
        if self._x_disp is None or self._disp is None:
            return
        # relim + autoscale applies matplotlib's default 5% margin on both axes,
        # so the first/last data point isn't flush against the frame.
        self._ax.relim()
        self._ax.autoscale(True)
        # Re-apply log-axis clamping after autoscale re-expands the range.
        if self._log_x:
            x_pos = self._x_disp[self._x_disp > 0]
            if x_pos.size > 0 and self._ax.get_xlim()[0] <= 0:
                self._ax.set_xlim(float(x_pos.min()), self._ax.get_xlim()[1])
        if self._log_y:
            y_pos = self._disp[self._disp > 0]
            if y_pos.size > 0 and self._ax.get_ylim()[0] <= 0:
                self._ax.set_ylim(float(y_pos.min()), self._ax.get_ylim()[1])
        self.draw_idle()

    def status_str(self) -> str:
        if self._hover_idx is None or self._data is None:
            return ""
        i = self._hover_idx
        if self._mode == "xy":
            if self._col_xy:
                x_val = float(self._data[i, 0])
                y_val = float(self._data[i, 1])
            else:
                x_val = float(self._data[0, i])
                y_val = float(self._data[1, i])
            return f"x={x_val:.4g}  val={y_val:.4g}"
        else:
            y_val = float(self._data[i])
            return f"idx={i}  val={y_val:.4g}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _x_label(self) -> str:
        return "x" if self._mode == "xy" else "index"

    # ------------------------------------------------------------------
    # Mouse interaction
    # ------------------------------------------------------------------

    def _on_motion(self, ev) -> None:
        if self._pan_start_px is not None:
            bbox = self._ax.get_window_extent()
            if bbox.width > 0 and bbox.height > 0:
                xl0, xl1 = self._pan_start_xl
                yl0, yl1 = self._pan_start_yl
                # pixel delta → data delta (drag right = data shifts left)
                dx = -(ev.x - self._pan_start_px[0]) / bbox.width  * (xl1 - xl0)
                dy = -(ev.y - self._pan_start_px[1]) / bbox.height * (yl1 - yl0)
                new_xl = [xl0 + dx, xl1 + dx]
                new_yl = [yl0 + dy, yl1 + dy]
                # No explicit log-axis guard here: matplotlib clips non-positive
                # limits silently when log scale is active, so panning into the
                # negative range just shows blank space — intentional, not missing.
                self._ax.set_xlim(new_xl)
                self._ax.set_ylim(new_yl)
                self.draw_idle()
            return

        if ev.inaxes is self._ax and self._x_disp is not None and ev.xdata is not None:
            n = self._data.shape[0] if self._col_xy else self._data.shape[-1]
            if self._mode == "xy":
                # Nearest search on downsampled _x_disp only — never touches the
                # full memmap during motion. Map back to full-res with stride.
                i_disp = int(np.argmin(np.abs(self._x_disp - ev.xdata)))
                self._hover_idx = min(i_disp * self._stride, n - 1)
            else:
                i = int(round(ev.xdata))   # x axis is plain index
                self._hover_idx = int(np.clip(i, 0, n - 1))
        else:
            self._hover_idx = None
        self._on_status(self.status_str())

    def _on_press(self, ev) -> None:
        # Any click anywhere on this canvas selects it as the export target.
        self._on_selected(self)
        if ev.button == 1 and ev.dblclick:
            self.reset_zoom()
        elif ev.button == 1 and not ev.dblclick and ev.inaxes is self._ax:
            self._pan_start_px = (ev.x, ev.y)
            self._pan_start_xl = self._ax.get_xlim()
            self._pan_start_yl = self._ax.get_ylim()

    def _on_release(self, ev) -> None:
        if ev.button == 1:
            self._pan_start_px = None
            self._pan_start_xl = None
            self._pan_start_yl = None

    def _on_scroll(self, ev) -> None:
        # No log-axis guard on scroll either — same rationale as pan: matplotlib
        # handles non-positive limits silently under log scale.
        if ev.inaxes is not self._ax or self._x_disp is None:
            return
        factor = 0.8 if ev.step > 0 else 1.25
        shift_held = bool(QApplication.keyboardModifiers() & Qt.ShiftModifier)
        if shift_held:
            if ev.ydata is None:
                return
            yc = ev.ydata
            yl = list(self._ax.get_ylim())
            new_yl = [yc + (yl[0] - yc) * factor, yc + (yl[1] - yc) * factor]
            if new_yl[0] >= new_yl[1]:
                return
            self._ax.set_ylim(new_yl)
        else:
            if ev.xdata is None:
                return
            xc = ev.xdata
            xl = list(self._ax.get_xlim())
            new_xl = [xc + (xl[0] - xc) * factor, xc + (xl[1] - xc) * factor]
            if new_xl[0] >= new_xl[1]:
                self.reset_zoom()
                return
            self._ax.set_xlim(new_xl)
        self.draw_idle()

    def _on_axes_leave(self, ev) -> None:
        self._hover_idx = None
        self._on_status("")

    def _reset_x_autoscale(self) -> None:
        self._ax.relim()
        self._ax.autoscale(True, axis="x")

    def _reset_y_autoscale(self) -> None:
        self._ax.relim()
        self._ax.autoscale(True, axis="y")


class LineplotView(BaseView):
    VIEW_ID = "lineplot"
    VIEW_NAME = "Line Plot"

    def __init__(self) -> None:
        super().__init__()
        self._status: str = ""

        def _status_proxy(msg: str) -> None:
            self._on_status(msg)

        self._canvas = LineplotCanvas(_status_proxy)

        _s = QSettings("npyquick", "npyquick")

        self._log_x_check = QCheckBox("Log X")
        self._log_x_check.toggled.connect(self._canvas.set_log_x)
        self._log_x_check.toggled.connect(
            lambda checked: QSettings("npyquick", "npyquick").setValue("lineplot_log_x", checked)
        )

        self._log_y_check = QCheckBox("Log Y")
        self._log_y_check.toggled.connect(self._canvas.set_log_y)
        self._log_y_check.toggled.connect(
            lambda checked: QSettings("npyquick", "npyquick").setValue("lineplot_log_y", checked)
        )

        if _s.value("lineplot_log_x", False, type=bool):
            self._log_x_check.setChecked(True)
        if _s.value("lineplot_log_y", False, type=bool):
            self._log_y_check.setChecked(True)

        self._full_btn = QPushButton("Reset")
        self._full_btn.setFixedWidth(52)
        self._full_btn.clicked.connect(self._canvas.reset_zoom)

        self._stats_label = QLabel()
        self._stats_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._sample_label = QLabel()
        self._sample_label.setStyleSheet("color: #b8860b;")
        self._sample_label.setVisible(False)

        self._anomaly_label = QLabel()
        self._anomaly_label.setStyleSheet("color: red;")
        self._anomaly_label.setVisible(False)

        ctrl = QWidget()
        # The control row is one line tall; never let it absorb vertical space.
        ctrl.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        ctrl_layout = QHBoxLayout(ctrl)
        ctrl_layout.setContentsMargins(6, 3, 6, 3)
        ctrl_layout.addWidget(self._log_x_check)
        ctrl_layout.addSpacing(8)
        ctrl_layout.addWidget(self._log_y_check)
        ctrl_layout.addSpacing(16)
        ctrl_layout.addWidget(self._full_btn)
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
        layout.addWidget(self._canvas, 1)

    @classmethod
    def can_handle(cls, array: np.ndarray) -> bool:
        if not is_real_numeric(array):
            return False
        if array.ndim == 1:
            return array.size > 0
        if array.ndim == 2 and array.shape[0] == 2:
            return array.shape[1] > 2   # (2, N) row-based x-y
        if array.ndim == 2 and array.shape[1] == 2:
            return array.shape[0] > 2   # (N, 2) column-based x-y
        return False

    def set_data(self, array: np.ndarray, stats: ArrayStats | None = None) -> None:
        # Intentionally ignore full-array stats from app.py.
        # Line plot displays y-only stats, so it recomputes stats on y values.
        self._canvas.load(array)

        n_total = self._canvas._data.shape[0] if self._canvas._col_xy else self._canvas._data.shape[-1]
        n_used = (n_total + self._canvas._stride - 1) // self._canvas._stride

        x_has_pos = bool(np.any(self._canvas._x_disp > 0))
        y_has_pos = bool(np.any(self._canvas._disp > 0))
        self._log_x_check.setEnabled(x_has_pos)
        self._log_y_check.setEnabled(y_has_pos)
        if not x_has_pos and self._log_x_check.isChecked():
            self._log_x_check.setChecked(False)
        if not y_has_pos and self._log_y_check.isChecked():
            self._log_y_check.setChecked(False)

        y_arr = array if array.ndim == 1 else (array[:, 1] if self._canvas._col_xy else array[1])
        stats = array_stats(y_arr)
        if stats is not None and stats.finite_min is not None:
            self._stats_label.setText(
                f"min {stats.finite_min:.4g}  max {stats.finite_max:.4g}"
            )
        else:
            self._stats_label.setText("no finite values")

        sampled = n_used < n_total
        if sampled:
            self._sample_label.setText(f"sampled {n_used:,} / {n_total:,}")
            self._sample_label.setVisible(True)
        else:
            self._sample_label.setVisible(False)

        if stats is not None and stats.has_anomaly:
            self._anomaly_label.setText(stats.anomaly_str())
            self._anomaly_label.setVisible(True)
        else:
            self._anomaly_label.setVisible(False)

        self._status = (
            f"shape {array.shape}  dtype {array.dtype}"
            + (f"  |  min {stats.finite_min:.4g}  max {stats.finite_max:.4g}"
               if stats and stats.finite_min is not None else "")
        )

    def refresh_status(self) -> None:
        s = self._canvas.status_str()
        self._on_status(s if s else self._status)

    def set_on_canvas_selected(self, cb: callable) -> None:
        self._canvas._on_selected = cb

    def export_targets(self):
        return [("Line Plot", self._canvas._export_figure)]
