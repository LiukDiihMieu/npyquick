# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 LiukDiihMieu

"""Table view. Ported from views/table.py's NpyTableModel/RawTableView — the
universal fallback view (can_handle is always True: any dtype/shape lands
here as a last resort, even structured/string arrays, via plain str()).

Caveat carried over from the Image view: a simple row model needs the whole
capped grid of formatted cells sent to the browser up front — unlike the
desktop's QAbstractTableModel, which only ever formats whatever cells are
actually scrolled into view. Measured directly against a real 12000x12000
array: formatting the desktop's TABLE_MAX_PER_AXIS=2000 cap (4M cells, in a
pure-Python loop) alone took ~12.8s — the single largest contributor to a slow
page load, bigger than the Image view's own cost. Serve gets its own, much
smaller cap instead of touching the shared constant (which the desktop app
still relies on as-is) — same idea as _SERVE_IMAGE_MAX_PIXELS in
serve/views/image.py.

Uses ui.table (Quasar QTable), not ui.aggrid: this is meant to be a read-only
data preview, and QTable has no built-in drag-to-reorder or drag-to-resize at
all (nothing to suppress), unlike AG Grid, which needed both explicitly
turned off. See git history for the AG Grid version this replaced.
"""

from __future__ import annotations

import numpy as np
from nicegui import ui

from npyquick.core import limits
from npyquick.core.stats import ArrayStats, array_stats
from npyquick.serve.views._shared import fit_height_to_viewport

_SERVE_TABLE_MAX_PER_AXIS = 512

# Gives the "_idx" row-number column a sticky (stays put while scrolling
# horizontally) header-toned look, matching the desktop QTableView's always-
# visible row header — QTable has no native pinned-column feature, but
# `position: sticky` plus a solid background (so scrolled-under content
# doesn't show through) gets the same effect with plain CSS, no JS. Injected
# once per page via ui.add_css, not inline per element: it's the same rule
# for every grid this view creates (the single table and all three RGB ones).
#
# The `table.q-table { width: auto }` rule fixes a separate issue: Quasar
# reuses the class name "q-table" on BOTH the outer wrapper div (which does
# need width:100% — see _make_grid's docstring for why) AND the actual inner
# <table> element. Quasar's own default styling stretches that inner
# <table> to 100% too, and since individual cells' explicit width (see
# _table_columns) is only a MINIMUM under the browser's default table-layout
# algorithm, a table with few narrow columns (e.g. a 1D array's single data
# column) still gets stretched to fill the whole container, leaving each
# cell awkwardly wide. `table.q-table` (tag AND class) targets only the
# inner element — the outer wrapper is a <div>, never matched by a tag-
# qualified `table` selector — letting the table size to its own content
# instead, while the OUTER wrapper (still 100%) is what actually provides
# the horizontal scrollbar once a WIDE table (many columns) exceeds it.
_TABLE_CSS = """
.npyquick-idx-col {
    position: sticky;
    left: 0;
    z-index: 1;
    font-weight: 500;
    background: #f5f5f5;
    color: rgba(0, 0, 0, 0.7);
}
body.body--dark .npyquick-idx-col {
    background: #2d2d2d;
    color: rgba(255, 255, 255, 0.7);
}
table.q-table {
    width: auto;
}
"""


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


def _table_columns(cols: int, *, data_width: int) -> list[dict]:
    """QTable columnDefs for an already-truncated 2D (or flat 1D) array
    slice's `cols` data columns, plus the leading sticky "_idx" row-number
    column (see _TABLE_CSS). Framework-neutral (plain dicts, no NiceGUI
    element involved) so this is unit-testable without mounting a browser."""
    columns = [{
        "name": "_idx", "label": "", "field": "_idx", "align": "left",
        "classes": "npyquick-idx-col", "headerClasses": "npyquick-idx-col",
        "style": "width: 60px", "headerStyle": "width: 60px",
    }]
    columns += [{
        "name": str(c), "label": str(c), "field": str(c), "align": "left",
        "style": f"width: {data_width}px", "headerStyle": f"width: {data_width}px",
    } for c in range(cols)]
    return columns


def _table_rows(sub: np.ndarray, flat: bool) -> list[dict]:
    """QTable rows for an already-truncated 2D (or flat 1D) array slice."""
    cols = 1 if flat else sub.shape[1]
    rows = []
    for r in range(sub.shape[0]):
        row = {"_idx": r}
        if flat:
            row["0"] = _format_cell(sub[r])
        else:
            for c in range(cols):
                row[str(c)] = _format_cell(sub[r, c])
        rows.append(row)
    return rows


def _make_grid(*, data_width: int) -> ui.table:
    # w-full min-w-0: unlike ui.aggrid (which defaults to width: 100%),
    # QTable sizes itself to its natural content width by default — with
    # enough data columns, that's wider than its share of the RGB row's
    # flex layout, which (same flexbox gotcha as ImageView's image_row —
    # see that module's docstring) makes the ROW wrap instead of letting
    # the table scroll horizontally within its own bounded width. w-full
    # pins it to the container's width; min-w-0 removes the flex item's
    # default content-based width floor so w-full can actually shrink it
    # that far. QTable's own internal .q-table__middle wrapper still
    # scrolls horizontally on its own past that point, same as AG Grid did.
    grid = ui.table(rows=[], columns=[], row_key="_idx").props("flat dense virtual-scroll")
    grid.classes("w-full min-w-0")
    grid.style("height: 500px")
    return grid


class TableView:
    def __init__(self) -> None:
        # No card/title wrapper: this view now lives in its own ui.tab_panel
        # (app.py), which already supplies that visual identity via the tab
        # bar — see the Image/Histogram/Line Plot views' docstrings for the
        # same note. No hide() either: Table is the universal fallback (never
        # incompatible), and the "nothing loaded at all" global case is
        # handled by app.py hiding the whole tabs+panels container in one
        # shot, not per-view.
        ui.add_css(_TABLE_CSS)

        self.info_label = ui.label()
        self.trunc_label = ui.label().classes("text-amber-600")
        self.trunc_label.set_visibility(False)

        self.single_grid = _make_grid(data_width=90)
        self.single_grid.set_visibility(False)

        with ui.row().classes("w-full gap-2") as self.rgb_row:
            self.rgb_grids = []
            for label in "RGB":
                with ui.column().classes("flex-1 min-w-0 gap-1"):
                    ui.label(label).classes("font-bold")
                    self.rgb_grids.append(_make_grid(data_width=70))
        self.rgb_row.set_visibility(False)

        self.message_label = ui.label().classes("text-gray-500")
        self.message_label.set_visibility(False)
        # Dark mode note: QTable is already dark-mode-aware natively via
        # Quasar's own global dark setting (confirmed empirically — no code
        # needed here beyond the plain CSS above, which itself keys off the
        # same body--dark class Quasar's dark mode toggles) — so, unlike the
        # three Plotly-based views, TableView has no set_dark method at all.

    async def resize(self) -> None:
        """Fit whichever grid is currently visible to the viewport (see
        _shared.fit_height_to_viewport's docstring) — called on tab-
        activation and on a live browser-window resize, same triggers as
        the three Plotly views' resize(). QTable, like the AG Grid version
        this replaced, has no analogous stale-react()-while-hidden bug to
        also guard against (see ImageView.resize's docstring) — it just
        needs its container's height kept in sync with the window, nothing
        needs re-rendering."""
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
                columns = _table_columns(cols, data_width=70)
                row_data = _table_rows(array[:rows, :cols, i], flat=False)
                # suspend_updates() only silences the AUTOMATIC update that
                # a plain property set would otherwise trigger per
                # assignment (columns/rows are two separate ones here) — it
                # does NOT queue one to fire once the block exits. Confirmed
                # directly with a standalone probe page: without the
                # explicit grid.update() below, the client never receives
                # either property at all, and the table is left showing
                # "No data available" — not a timing issue, genuinely never
                # sent. The trailing update() call is what actually pushes
                # the (already-mutated) current state.
                with grid.props.suspend_updates():
                    grid.columns = columns
                    grid.rows = row_data
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
            columns = _table_columns(cols, data_width=90)
            row_data = _table_rows(sub, flat)
            with self.single_grid.props.suspend_updates():
                self.single_grid.columns = columns
                self.single_grid.rows = row_data
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
