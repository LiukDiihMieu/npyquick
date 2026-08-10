# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 LiukDiihMieu

"""npyquick serve — entry point: loads an array and wires it into views.

Image, Histogram, Line Plot, Table, the npz array picker, the file browser,
and the pixel-size dialog are implemented so far. PNG export needs no
dedicated work: every Plotly plot already has a built-in "download plot as
png" button in its modebar.
"""

from __future__ import annotations

import os

from nicegui import core as nicegui_core
from nicegui import ui

from npyquick.core.stats import array_stats
from npyquick.model import NpyDataModel
from npyquick.serve.file_picker import FilePicker
from npyquick.serve.pixel_size_dialog import PixelSizeDialog
from npyquick.serve.views.histogram import HistogramView
from npyquick.serve.views.image import ImageView
from npyquick.serve.views.lineplot import LineplotView
from npyquick.serve.views.table import TableView

# Stopgap: python-socketio defaults to a 1 MB per-message limit, but a
# downsampled array (up to IMAGE_MAX_PIXELS) shipped as raw Heatmap/Image
# numeric data can be tens to ~100+ MB for a large float64 array — that budget
# was sized for local desktop rendering, not for putting bytes on a wire. The
# real fix is to render server-side to a compressed PNG instead of shipping
# raw pixel values over the websocket at all; until that lands, just raise the
# ceiling so a normal-sized array doesn't hit "Payload size ... exceeds the
# maximum allowed limit". Must be set before ui.run() starts accepting
# connections, since the limit is advertised to clients at handshake time.
nicegui_core.sio.eio.max_http_buffer_size = 200 * 1024 * 1024  # 200 MiB


def run_server(file: str | None, *, host: str, port: int) -> None:
    @ui.page("/")
    async def index() -> None:
        error_label = ui.label().classes("text-red-500")

        with ui.row().classes("items-center gap-2"):
            open_btn = ui.button("Open...")
            pixel_size_btn = ui.button("Pixel size...")
            current_file_label = ui.label().classes("text-sm text-gray-500")

        # npz archives never auto-materialize a member, even when there's
        # only one — the desktop deliberately requires an explicit selection
        # every time (member size is only checked once you actually try to
        # select it, not speculatively), and this matches that exactly rather
        # than special-casing the single-member case for convenience.
        with ui.row().classes("items-center gap-2") as array_bar:
            array_select = ui.select({}, label="Array").classes("min-w-[20rem]")
        array_bar.set_visibility(False)

        model = NpyDataModel()
        image_view = ImageView()
        histogram_view = HistogramView()
        lineplot_view = LineplotView()
        table_view = TableView()

        # Bidirectional clim sync, matching desktop app.py's wiring between
        # ImageView and HistogramView: a clim change on either side updates
        # the other. update_clim_marker/set_clim_from_histogram are both
        # silent sinks (no callback fired back), so this can't loop.
        image_view.set_on_clim_change(histogram_view.update_clim_marker)
        image_view.set_on_active_panel_change(
            lambda: histogram_view.update_clim_marker(*image_view.get_clim())
        )
        histogram_view.set_on_clim_dragged(image_view.set_clim_from_histogram)

        def hide_all_views() -> None:
            """Hide every view's widgets — used whenever the model has no
            displayable array right now (an .npz still needs a member picked,
            a pick failed with nothing valid ever selected, or a selected
            member turned out to be empty). Without this, a view's content
            from a PREVIOUS, unrelated file/array stayed on screen under a
            label/state that no longer matched it."""
            image_view.hide()
            histogram_view.hide()
            lineplot_view.hide()
            table_view.hide()

        def refresh_views(array) -> None:
            # Each view independently decides whether it can display this
            # array (e.g. a 1D array has no Image view but still has a
            # Histogram and a Line Plot) — array_stats is computed once and
            # shared, same as desktop app.py's single _refresh_views() scan
            # feeding every view's set_data(). Line Plot ignores the shared
            # stats by design (it shows y-values-only stats), so it isn't
            # passed here.
            error_label.text = ""
            stats = array_stats(array)
            image_error = image_view.set_data(array, stats)
            histogram_error = histogram_view.set_data(array, stats)
            lineplot_error = lineplot_view.set_data(array)
            table_view.set_data(array, stats)  # never errors — universal fallback

            errors = [e for e in (image_error, histogram_error, lineplot_error) if e]
            if len(errors) == 3:
                error_label.text = "  |  ".join(errors)
            elif errors:
                error_label.text = errors[0]

            if not image_error:
                histogram_view.update_clim_marker(*image_view.get_clim())

        def on_array_selected() -> None:
            key = array_select.value
            if key is None:
                return
            try:
                model.select_array(key)
            except Exception as exc:  # noqa: BLE001 - surfaced on the page, not re-raised
                error_label.text = f"Failed to load array '{key}': {exc}"
                array_select.value = None
                # select_array only mutates model.array on SUCCESS, so on
                # failure it's still whatever was selected before (still
                # valid, still correctly displayed) — UNLESS nothing has ever
                # been selected for this .npz yet, in which case the views are
                # showing an unrelated PREVIOUS file/array and must be hidden.
                if model.array is None:
                    hide_all_views()
                return
            if model.array.size == 0:
                error_label.text = f"Array '{key}' is empty."
                hide_all_views()
                return
            refresh_views(model.array)

        array_select.on_value_change(on_array_selected)

        def load_file(path: str) -> None:
            try:
                model.load(path)
            except Exception as exc:  # noqa: BLE001 - surfaced on the page, not re-raised
                error_label.text = f"Failed to load '{path}': {exc}"
                # Do NOT touch current_file_label/array_bar/views here: model
                # still holds whatever was successfully loaded before (load()
                # only mutates its state on success), so the page must keep
                # matching that, not the new path that never actually loaded.
                return

            current_file_label.text = path
            array_bar.set_visibility(False)
            array_select.value = None

            if model.array is None:
                # .npz with (possibly just one) member(s) — always wait for an
                # explicit pick, same as the desktop (see the array_bar
                # comment above for why).
                metas = model.available_array_meta()
                array_select.options = {
                    key: f"{key}   {list(meta.shape)}   {meta.dtype}" for key, meta in metas.items()
                }
                array_select.update()
                array_bar.set_visibility(True)
                error_label.text = f"'{path}' is an .npz archive with {len(metas)} array(s) — pick one above."
                hide_all_views()
                return

            if model.array.size == 0:
                error_label.text = "Array is empty."
                hide_all_views()
                return
            refresh_views(model.array)

        picker = FilePicker(start_dir=os.path.dirname(os.path.abspath(file)) if file else os.getcwd())

        async def open_picker() -> None:
            path = await picker
            if path:
                load_file(path)

        open_btn.on_click(open_picker)

        pixel_size_dialog = PixelSizeDialog()

        async def open_pixel_size_dialog() -> None:
            result = await pixel_size_dialog
            if result is not None:
                value, _expr, unit = result
                # Applies even with nothing loaded yet — ImageView.set_pixel_size
                # just remembers it and re-renders next time an array supports
                # the Image view, same as the desktop's independent top-level
                # _pixel_size/_pixel_unit state.
                image_view.set_pixel_size(value, unit)

        pixel_size_btn.on_click(open_pixel_size_dialog)

        if file:
            load_file(file)
        else:
            # No path on the command line — open the browser directly rather
            # than making the user notice and click "Open..." themselves
            # after reading an error message. MUST wait for the client to
            # actually connect first: open_picker() awaits the dialog's
            # submit(), which doesn't resolve until the user picks a file —
            # NiceGUI races index() against the client actually connecting
            # and sends the initial page response as soon as EITHER finishes
            # (see page.py's response_timeout handling), but only if
            # something inside index() signals that wait via
            # client.connected(). Without it, the initial HTTP response never
            # gets released and index() itself blocks on the picker, which
            # trips the "took longer than response_timeout" 500 error instead
            # of ever showing a page to open the picker on.
            await ui.context.client.connected()
            await open_picker()

    ui.run(host=host, port=port, title="npyquick serve", reload=False, show=False)
