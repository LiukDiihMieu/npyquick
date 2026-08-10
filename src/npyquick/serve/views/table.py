# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 LiukDiihMieu

"""Table view. Ported from views/table.py's NpyTableModel/RawTableView — the
universal fallback view (can_handle is always True: any dtype/shape lands
here as a last resort, even structured/string arrays, via plain str()).

Caveat carried over from the Image view: ag-Grid's simple row model needs the
whole capped grid of formatted cells sent to the browser up front — unlike the
desktop's QAbstractTableModel, which only ever formats whatever cells are
actually scrolled into view. Measured directly against a real 12000x12000
array: formatting the desktop's TABLE_MAX_PER_AXIS=2000 cap (4M cells, in a
pure-Python loop) alone took ~12.8s — the single largest contributor to a slow
page load, bigger than the Image view's own cost. Serve gets its own, much
smaller cap instead of touching the shared constant (which the desktop app
still relies on as-is) — same idea as _SERVE_IMAGE_MAX_PIXELS in
serve/views/image.py.
"""

from __future__ import annotations

import numpy as np
from nicegui import ui

from npyquick.core import limits
from npyquick.core.stats import ArrayStats, array_stats
from npyquick.serve.views._shared import fit_height_to_viewport

_SERVE_TABLE_MAX_PER_AXIS = 512


def _too_large_to_tabulate_message(array: np.ndarray) -> str:
    gib = array.nbytes / 1024**3
    size = f"{gib:.1f} GiB" if gib >= 1 else f"{array.nbytes / 1024**2:.0f} MiB"
    return (
        f"This {array.ndim}-D array ({size}) is stored in Fortran (column-major) "
        f"order. Reshaping it to 2-D for the table would copy the whole array "
        f"into memory, so the Table view is disabled for it. The Histogram view "
        f"still works (it samples without copying)."
    )


def _format_cell(val) -> str:
    if isinstance(val, (np.floating, float)):
        return f"{val:.6g}"
    return str(val)


def _prepare_table_array(array: np.ndarray) -> tuple[np.ndarray | None, bool, str]:
    """Mirror NpyTableModel.set_array. Returns (2d_or_flat_array, is_flat,
    message) — message is non-empty (and the array None) when refused."""
    if array.ndim == 0:
        return array.reshape(1, 1), False, ""
    if array.ndim == 1:
        return array, True, ""
    if array.ndim == 2:
        return array, False, ""
    if array.nbytes > limits.LARGE_BYTES and not array.flags["C_CONTIGUOUS"]:
        # Check BEFORE reshaping: reshape(-1, last) is C-order and would copy
        # a large Fortran-order memmap fully into RAM. Refuse instead.
        return None, False, _too_large_to_tabulate_message(array)
    return array.reshape(-1, array.shape[-1]), False, ""


def _grid_data(sub: np.ndarray, flat: bool) -> tuple[list[dict], list[dict]]:
    """AG Grid columnDefs/rowData for an already-truncated 2D (or flat 1D)
    array slice. A pinned "_idx" column replicates the desktop QTableView's
    always-shown row-number header (ag-Grid has no such default)."""
    cols = 1 if flat else sub.shape[1]
    column_defs = [{"field": "_idx", "headerName": "", "pinned": "left", "width": 60}]
    column_defs += [{"field": str(c), "headerName": str(c)} for c in range(cols)]
    row_data = []
    for r in range(sub.shape[0]):
        row = {"_idx": r}
        if flat:
            row["0"] = _format_cell(sub[r])
        else:
            for c in range(cols):
                row[str(c)] = _format_cell(sub[r, c])
        row_data.append(row)
    return column_defs, row_data


class TableView:
    def __init__(self) -> None:
        # No card/title wrapper: this view now lives in its own ui.tab_panel
        # (app.py), which already supplies that visual identity via the tab
        # bar — see the Image/Histogram/Line Plot views' docstrings for the
        # same note. No hide() either: Table is the universal fallback (never
        # incompatible), and the "nothing loaded at all" global case is
        # handled by app.py hiding the whole tabs+panels container in one
        # shot, not per-view.
        self.info_label = ui.label()
        self.trunc_label = ui.label().classes("text-amber-600")
        self.trunc_label.set_visibility(False)

        # auto_size_columns=False: its default (True, when columnDefs has
        # no flex columns) sets an autoSizeStrategy that fits columns to
        # the grid width — AG Grid crashes on mount trying to do that
        # against the placeholder empty columnDefs=[] every grid here
        # starts with (before the first set_data call ever supplies real
        # data), which silently leaves the whole element broken (later
        # .options updates never take effect either). Explicit widths
        # below match the desktop QTableView's
        # setDefaultSectionSize(90)/(70) instead.
        self.single_grid = ui.aggrid(
            {"columnDefs": [], "rowData": [], "defaultColDef": {"width": 90}, "suppressMovableColumns": True},
            auto_size_columns=False,
        ).classes("w-full").style("height: 500px")
        self.single_grid.set_visibility(False)

        with ui.row().classes("w-full gap-2") as self.rgb_row:
            self.rgb_grids = []
            for label in "RGB":
                with ui.column().classes("flex-1 gap-1"):
                    ui.label(label).classes("font-bold")
                    grid = ui.aggrid(
                        {"columnDefs": [], "rowData": [], "defaultColDef": {"width": 70}, "suppressMovableColumns": True},
                        auto_size_columns=False,
                    ).style("height: 500px")
                    self.rgb_grids.append(grid)
        self.rgb_row.set_visibility(False)

        self.message_label = ui.label().classes("text-gray-500")
        self.message_label.set_visibility(False)
        # Dark mode note: AG Grid's theme is already dark-mode-aware natively
        # — NiceGUI's bundled aggrid.js watches document.body's Quasar
        # "body--dark" class and switches the grid's own colorSchemeVariable
        # accordingly, with zero code needed here (confirmed by reading
        # aggrid.js directly) — so, unlike the three Plotly-based views,
        # TableView has no set_dark method at all.

    async def resize(self) -> None:
        """Fit whichever grid is currently visible to the viewport (see
        _shared.fit_height_to_viewport's docstring) — called on tab-
        activation and on a live browser-window resize, same triggers as
        the three Plotly views' resize(). Unlike those views, ag-Grid has
        no analogous stale-react()-while-hidden bug to also guard against
        (see ImageView.resize's docstring) — it just needs its container's
        height kept in sync with the window, nothing needs re-rendering."""
        if self.single_grid.visible:
            await fit_height_to_viewport(self.single_grid)
        elif self.rgb_row.visible:
            await fit_height_to_viewport(*self.rgb_grids)

    def set_data(self, array: np.ndarray, stats: ArrayStats | None = None) -> None:
        """Always succeeds — Table is the universal fallback (can_handle is
        always True on the desktop), so this never returns an error."""
        self.single_grid.set_visibility(False)
        self.rgb_row.set_visibility(False)
        self.message_label.set_visibility(False)

        if array.ndim == 3 and array.shape[2] == 3:
            full_rows, full_cols = array.shape[:2]
            rows = min(full_rows, _SERVE_TABLE_MAX_PER_AXIS)
            cols = min(full_cols, _SERVE_TABLE_MAX_PER_AXIS)
            for i, grid in enumerate(self.rgb_grids):
                column_defs, row_data = _grid_data(array[:rows, :cols, i], flat=False)
                # Merge into the existing options rather than replacing the
                # dict outright: AG Grid's Vue wrapper looks up options.theme
                # on every (re)mount (including the one triggered later by
                # set_visibility(True), if that's implemented as v-if) —
                # dropping it crashes with "Cannot read properties of
                # undefined (reading 'withPart')" and leaves the grid dead.
                grid.options = {**grid.options, "columnDefs": column_defs, "rowData": row_data}
                grid.update()
            self.rgb_row.set_visibility(True)
            status = f"shape {array.shape}  dtype {array.dtype}  —  3 channels"
            trunc_prefix = ", each showing"
        else:
            arr2d, flat, message = _prepare_table_array(array)
            if message:
                self.message_label.text = message
                self.message_label.set_visibility(True)
                self.trunc_label.set_visibility(False)
                self.info_label.text = f"shape {array.shape}  dtype {array.dtype}"
                return
            assert arr2d is not None
            full_rows = arr2d.shape[0]
            full_cols = 1 if flat else arr2d.shape[1]
            rows = min(full_rows, _SERVE_TABLE_MAX_PER_AXIS)
            cols = min(full_cols, _SERVE_TABLE_MAX_PER_AXIS)
            sub = arr2d[:rows] if flat else arr2d[:rows, :cols]
            column_defs, row_data = _grid_data(sub, flat)
            self.single_grid.options = {**self.single_grid.options, "columnDefs": column_defs, "rowData": row_data}
            self.single_grid.update()
            self.single_grid.set_visibility(True)
            status = f"shape {array.shape}  dtype {array.dtype}"
            trunc_prefix = "  —  showing"

        truncated = rows < full_rows or cols < full_cols
        if truncated:
            self.trunc_label.text = f"{trunc_prefix} {rows}×{cols} of {full_rows}×{full_cols}  (truncated)"
        self.trunc_label.set_visibility(truncated)

        if stats is None:
            stats = array_stats(array)
        if stats is not None and stats.has_anomaly:
            status += f"  |  {stats.anomaly_str()}"
        self.info_label.text = status
