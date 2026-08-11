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
        # Custom theme color (Quasar's own CSS-variable mechanism via
        # ui.colors, not per-element hand-rolled colors) — a muted teal
        # instead of Quasar's default blue, so this reads as a purpose-built
        # tool rather than a generic default-styled page.
        ui.colors(primary="#00695c", secondary="#26a69a", accent="#ff7043")
        # NiceGUI's own page root (.nicegui-content) carries a default
        # padding+gap of its own, stacking on top of this page's outer
        # ui.column() AND each ui.tab_panel()'s padding below — confirmed via
        # a real browser's computed-style inspection (not just a visual
        # glance) that all three layers were contributing independently to
        # the header->tabs and tabs->controls gaps looking oversized. Only
        # ONE layer should own the page's outer margin; zeroing this one out
        # and letting the ui.column() below be that single owner is the fix.
        ui.query(".nicegui-content").classes("p-0 gap-0")
        # value=None: NiceGUI/Quasar's native "auto" mode, following the
        # browser's prefers-color-scheme — the default, so the page matches
        # the system without the user having to do anything.
        dark = ui.dark_mode(value=None)

        # text-white on the header itself: ui.header()'s background follows
        # the primary theme color (set above), but flat buttons don't
        # inherit a readable text color from that automatically — without an
        # explicit color, both buttons rendered nearly invisible against the
        # teal background (confirmed via screenshot: "Open..." disappeared
        # entirely, "Pixel size..." was barely a shade darker than the bar).
        #
        # NOTE: ui.button(..., color="white") looks like the obvious fix but
        # is WRONG — tried it, made things worse (solid white boxes with
        # invisible text). Traced why: NiceGUI's Button maps `color` to
        # BackgroundColorElement, which checks Quasar's color-name list
        # first, then Tailwind's; "white" isn't a Quasar color name but IS a
        # Tailwind one, so it silently added a literal `bg-white` CSS class
        # (an actual background fill) instead of tinting the flat button's
        # text via Quasar's own color prop. Fix: color=None (skip that
        # machinery entirely, don't even take the default 'primary') plus a
        # plain `text-white` Tailwind class, which flat QBtn text/icons do
        # correctly inherit via normal CSS color inheritance.
        with ui.header().classes("items-center justify-between px-4 py-1 text-white"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("insights").classes("text-2xl")
                ui.label("npyquick serve").classes("text-lg font-medium")
            with ui.row().classes("items-center gap-2"):
                open_btn = ui.button("Open...", icon="folder_open", color=None).props("flat dense").classes("text-white")
                pixel_size_btn = ui.button(
                    "Pixel size...", icon="straighten", color=None,
                ).props("flat dense").classes("text-white")
                current_file_label = ui.label().classes("text-sm text-white opacity-90 max-w-[24rem] truncate")
                dark_btn = ui.button(icon="brightness_auto", color=None).props("flat dense round").classes("text-white")
                dark_btn.tooltip("Theme: follows system")

        with ui.column().classes("w-full max-w-[1600px] mx-auto px-2 pb-2 pt-0 gap-2"):
            # A compact, bordered/tinted banner with an icon — instead of a
            # bare line of red text — for load/compatibility errors ("Line
            # Plot doesn't support dtype complex64", a failed npz select,
            # etc.), aligned with the rest of the page content (same column,
            # same max-width) rather than sitting flush at the page edge.
            # Text color is left unstyled deliberately: it inherits Quasar's
            # own light/dark default text color, so it stays readable in
            # both themes without needing separate dark: variants.
            with ui.row().classes(
                "w-full items-center gap-2 rounded-borders px-3 py-2 border-l-4 border-red-500 bg-red-500/10"
            ) as error_banner:
                ui.icon("error_outline").classes("text-red-600 text-lg")
                error_label = ui.label().classes("text-sm")
            error_banner.set_visibility(False)

            def show_error(text: str) -> None:
                error_label.text = text
                error_banner.set_visibility(True)

            def clear_error() -> None:
                error_label.text = ""
                error_banner.set_visibility(False)

            # npz archives never auto-materialize a member, even when there's
            # only one — the desktop deliberately requires an explicit selection
            # every time (member size is only checked once you actually try to
            # select it, not speculatively), and this matches that exactly rather
            # than special-casing the single-member case for convenience.
            with ui.row().classes("items-center gap-2") as array_bar:
                array_select = ui.select({}, label="Array").classes("min-w-[20rem]").props("dense")
            array_bar.set_visibility(False)

            model = NpyDataModel()

            # Tabs, like the desktop's QTabWidget — a view whose shape/dtype
            # doesn't fit the current array gets its TAB disabled (below, in
            # refresh_views) rather than showing a page-wide error banner:
            # each view's own compatibility is contextual to that view, not
            # a global page problem, and the desktop makes the same call
            # (setTabEnabled + auto-switch away, never a modal/banner for
            # this specific case — see app.py's _set_tabs_enabled).
            with ui.tabs().classes("w-full").props("dense") as view_tabs:
                tab_image = ui.tab("image", label="Image")
                tab_histogram = ui.tab("histogram", label="Histogram")
                tab_lineplot = ui.tab("lineplot", label="Line Plot")
                tab_table = ui.tab("table", label="Table")
            # p-0 gap-2: Quasar's own QTabPanel default padding (16px)
            # would be a FOURTH layer of outer margin stacking on top of
            # .nicegui-content and the outer ui.column() above (see the
            # ui.query(".nicegui-content") comment near the top of this
            # function for the general principle: only one layer should own
            # outer spacing) — zeroed out entirely; the outer column's gap-2
            # already separates the tabs from their panel content. This overrides
            # Quasar's own rule because NiceGUI's CSS layer order (@layer
            # ... quasar, nicegui, ... utilities ...) puts "quasar" BEFORE
            # "utilities", so a plain (non-!important) Tailwind class here
            # reliably wins.
            with ui.tab_panels(view_tabs).classes("w-full") as view_panels:
                with ui.tab_panel(tab_image).classes("p-0 gap-2"):
                    image_view = ImageView()
                with ui.tab_panel(tab_histogram).classes("p-0 gap-2"):
                    histogram_view = HistogramView()
                with ui.tab_panel(tab_lineplot).classes("p-0 gap-2"):
                    lineplot_view = LineplotView()
                with ui.tab_panel(tab_table).classes("p-0 gap-2"):
                    table_view = TableView()
            view_tabs.set_visibility(False)
            view_panels.set_visibility(False)
            tabs_by_id = {
                "image": tab_image, "histogram": tab_histogram,
                "lineplot": tab_lineplot, "table": tab_table,
            }
            # All four views get a post-tab-switch (and, via the window-
            # resize listener below, post-window-resize) resize() call. The
            # three Plotly-based ones need it for two reasons (see
            # ImageView.resize's docstring): fitting the plot to the current
            # viewport, and a tab-activation staleness race that's specific
            # to them. Table's ag-Grid isn't affected by that second issue
            # at all, but still needs its own resize() for the first reason
            # — its grid should also fit the viewport, not sit at a fixed
            # pixel height.
            resizable_by_id = {
                "image": image_view, "histogram": histogram_view,
                "lineplot": lineplot_view, "table": table_view,
            }

            def current_tab_id() -> str | None:
                # view_tabs.value is a Tab object right after we set it
                # programmatically (see refresh_views), but degrades to a
                # plain string (the tab's own `name` prop) the moment the
                # USER clicks a tab — NiceGUI's Tabs class only converts
                # Tab/str -> str going OUT to the client
                # (_value_to_model_value), never the reverse on an incoming
                # change event, so .value ends up holding whichever shape
                # last set it. Normalize both here rather than relying on
                # a dict keyed by Tab objects, which would silently stop
                # matching after the first real click.
                value = view_tabs.value
                return value if isinstance(value, str) or value is None else value.props["name"]

        # Bidirectional clim sync, matching desktop app.py's wiring between
        # ImageView and HistogramView: a clim change on either side updates
        # the other. update_clim_marker/set_clim_from_histogram are both
        # silent sinks (no callback fired back), so this can't loop.
        image_view.set_on_clim_change(histogram_view.update_clim_marker)
        image_view.set_on_active_panel_change(
            lambda: histogram_view.update_clim_marker(*image_view.get_clim())
        )
        histogram_view.set_on_clim_dragged(image_view.set_clim_from_histogram)

        def apply_dark_to_views(is_dark: bool) -> None:
            # Quasar's own dark mode already recolors the header/cards/
            # controls/AG Grid (see TableView's __init__ comment) with zero
            # extra code — only Plotly needs telling explicitly, since it has
            # no way to observe that switch itself.
            image_view.set_dark(is_dark)
            histogram_view.set_dark(is_dark)
            lineplot_view.set_dark(is_dark)

        async def check_system_dark() -> bool:
            return bool(await ui.run_javascript(
                "window.matchMedia('(prefers-color-scheme: dark)').matches",
            ))

        def handle_media_change(e) -> None:
            # Only relevant while still in "auto" (dark.value is None) — a
            # manual pick means the user already overrode the system once,
            # and a later OS-level theme flip shouldn't silently undo that.
            if dark.value is None:
                apply_dark_to_views(bool(e.args.get("matches")))

        # Bridges Plotly to prefers-color-scheme using the SAME element
        # .on()/emit() idiom already used for the wheel-zoom handler in
        # lineplot.py: window.matchMedia has no direct line to the server, so
        # its 'change' event is re-dispatched as a CustomEvent on dark_btn's
        # own DOM node, which NiceGUI's normal event-forwarding then picks up
        # like any other client event.
        dark_btn.on("media_dark_change", handle_media_change, js_handler="(...args) => emit(args[0].detail)")

        async def arm_system_dark_listener() -> None:
            # Plotly has no native way to follow prefers-color-scheme itself
            # (confirmed by reading NiceGUI's dark_mode.js: it only ever
            # pushes a value server->client, never reports the resolved
            # system preference back) — this call both reads the CURRENT
            # preference once (for the very first render) and arms the
            # persistent listener above (for later, live OS theme switches).
            is_dark = await ui.run_javascript(f"""
                const mq = window.matchMedia('(prefers-color-scheme: dark)');
                const el = getHtmlElement({dark_btn.id});
                mq.addEventListener('change', (e) => {{
                    el.dispatchEvent(new CustomEvent('media_dark_change', {{detail: {{matches: e.matches}}, bubbles: true}}));
                }});
                return mq.matches;
            """)
            if dark.value is None:
                apply_dark_to_views(bool(is_dark))

        async def toggle_dark() -> None:
            # Three-state cycle: auto (follow system) -> dark -> light -> auto
            # ... rather than DarkMode.toggle(), which only flips True<->False
            # and raises ValueError when currently in auto (value=None) — the
            # default state here, so a plain toggle would crash on first click.
            if dark.value is None:
                dark.value = True
            elif dark.value:
                dark.value = False
            else:
                dark.value = None

            if dark.value is True:
                icon, tooltip, is_dark = "dark_mode", "Theme: dark", True
            elif dark.value is False:
                icon, tooltip, is_dark = "light_mode", "Theme: light", False
            else:
                icon, tooltip = "brightness_auto", "Theme: follows system"
                is_dark = await check_system_dark()  # re-sync to whatever the system currently is
            dark_btn.props(f"icon={icon}")
            dark_btn.tooltip(tooltip)
            apply_dark_to_views(is_dark)

        dark_btn.on_click(toggle_dark)

        async def handle_window_resized() -> None:
            # Only the currently ACTIVE tab's view — calling resize() on an
            # inactive one would re-render it while hidden, which is exactly
            # the staleness bug ImageView.resize's docstring describes (the
            # tab-switch case re-renders on purpose right as a tab becomes
            # active; this live-resize case must not do that to a tab that
            # ISN'T becoming active).
            vid = current_tab_id()
            target = resizable_by_id.get(vid) if vid is not None else None
            if target is not None:
                await target.resize()

        def handle_tab_activated() -> None:
            """Resizes whichever view the tab bar just switched TO. Reached
            two ways, never both at once for the same switch (see
            refresh_views' comment on `previous == target` for why): as
            `view_tabs.on_value_change`'s handler, whenever `view_tabs.value`
            actually changes identity — covers both the user clicking a
            different tab by hand, and refresh_views() landing on a
            different tab than was previously active; NiceGUI's
            BindableProperty fires on_value_change the same way regardless
            of who changed the value. And called directly, from
            refresh_views(), for the one case a value CHANGE can't cover:
            a fresh array landing on the SAME tab that was already active,
            where .value never actually changes and thus never fires
            on_value_change on its own. Without either path, a tab's view
            would sit at the tab-switch-staleness-bug sizing (see
            ImageView.resize's docstring) or its fallback height from
            construction time. Delayed slightly (same reasoning either way):
            gives the client a moment to actually apply the tab switch
            before this measures anything."""
            vid = current_tab_id()
            target = resizable_by_id.get(vid) if vid is not None else None
            if target is not None:
                ui.timer(0.05, target.resize, once=True)

        view_tabs.on_value_change(handle_tab_activated)

        # Same element .on()/emit() bridge as the system-dark-mode listener
        # above: window resize has no direct line to the server, so it's
        # re-dispatched as a CustomEvent on view_tabs' own DOM node. Debounced
        # client-side (a resize drag fires dozens of native events) before
        # forwarding a single event to Python.
        view_tabs.on("window_resized", handle_window_resized, js_handler="(...args) => emit(...args)")

        async def arm_window_resize_listener() -> None:
            """Lets each view's plot/grid keep fitting the browser window
            if the window is resized live without switching tabs or files
            (see _shared.fit_height_to_viewport's docstring for why this
            matters — without it, a view that fit the window at load time
            would fall out of sync the moment the window is resized)."""
            await ui.run_javascript(f"""
                let timer = null;
                const el = getHtmlElement({view_tabs.id});
                window.addEventListener('resize', () => {{
                    clearTimeout(timer);
                    timer = setTimeout(() => el.dispatchEvent(new CustomEvent('window_resized', {{bubbles: true}})), 200);
                }});
            """)

        def hide_view_tabs() -> None:
            """Hide the whole tabs+panels UI — used whenever the model has no
            displayable array right now (an .npz still needs a member picked,
            a pick failed with nothing valid ever selected, or a selected
            member turned out to be empty). Without this, a view's content
            from a PREVIOUS, unrelated file/array stayed on screen under a
            label/state that no longer matched it."""
            view_tabs.set_visibility(False)
            view_panels.set_visibility(False)

        def refresh_views(array) -> None:
            # Each view independently decides whether it can display this
            # array (e.g. a 1D array has no Image view but still has a
            # Histogram and a Line Plot) — array_stats is computed once and
            # shared, same as desktop app.py's single _refresh_views() scan
            # feeding every view's set_data(). Line Plot ignores the shared
            # stats by design (it shows y-values-only stats), so it isn't
            # passed here.
            clear_error()
            stats = array_stats(array)
            image_error = image_view.set_data(array, stats)
            histogram_error = histogram_view.set_data(array, stats)
            lineplot_error = lineplot_view.set_data(array)
            table_view.set_data(array, stats)  # never errors — universal fallback

            # A view that doesn't fit gets its TAB disabled, not a page-wide
            # error banner — matches the desktop's _set_tabs_enabled exactly
            # (setTabEnabled per view, never a modal/banner for this specific
            # case). Table is always compatible (it's the universal
            # fallback, same as the desktop), so `compatible` is never empty
            # here and there's always a tab to land on.
            errors_by_id = {
                "image": image_error, "histogram": histogram_error,
                "lineplot": lineplot_error, "table": None,
            }
            compatible = [vid for vid, err in errors_by_id.items() if err is None]
            for vid, tab in tabs_by_id.items():
                tab.set_enabled(vid in compatible)

            view_tabs.set_visibility(True)
            view_panels.set_visibility(True)

            # Same preference rule as the desktop: always jump to Line Plot
            # when it's compatible (regardless of whatever tab was previously
            # selected), else the first compatible tab.
            preferred = "lineplot" if lineplot_error is None else None
            target = preferred if preferred in compatible else compatible[0]
            # Setting .value only actually fires handle_tab_activated (via
            # on_value_change) if the tab identity is CHANGING — NiceGUI's
            # BindableProperty skips its change handlers entirely on a no-op
            # reassignment (e.g. picking a different array while staying on
            # the Image tab). Call it manually for exactly that case, so a
            # new load on the SAME tab still gets one resize() — and only
            # ONE: letting on_value_change fire on its own for the "tab
            # identity changed" case, instead of ALSO scheduling one here
            # unconditionally, is what used to double-fire resize() on every
            # ordinary tab switch (confirmed in a real browser's console:
            # the same Plotly relayout error appearing twice per switch).
            previous = current_tab_id()
            view_tabs.value = tabs_by_id[target]
            if previous == target:
                handle_tab_activated()

            if not image_error:
                histogram_view.update_clim_marker(*image_view.get_clim())

        def on_array_selected() -> None:
            key = array_select.value
            if key is None:
                return
            try:
                model.select_array(key)
            except Exception as exc:  # noqa: BLE001 - surfaced on the page, not re-raised
                show_error(f"Failed to load array '{key}': {exc}")
                array_select.value = None
                # select_array only mutates model.array on SUCCESS, so on
                # failure it's still whatever was selected before (still
                # valid, still correctly displayed) — UNLESS nothing has ever
                # been selected for this .npz yet, in which case the views are
                # showing an unrelated PREVIOUS file/array and must be hidden.
                if model.array is None:
                    hide_view_tabs()
                return
            if model.array.size == 0:
                show_error(f"Array '{key}' is empty.")
                hide_view_tabs()
                return
            refresh_views(model.array)

        array_select.on_value_change(on_array_selected)

        def load_file(path: str) -> None:
            try:
                model.load(path)
            except Exception as exc:  # noqa: BLE001 - surfaced on the page, not re-raised
                show_error(f"Failed to load '{path}': {exc}")
                # Do NOT touch current_file_label/array_bar/views here: model
                # still holds whatever was successfully loaded before (load()
                # only mutates its state on success), so the page must keep
                # matching that, not the new path that never actually loaded.
                return

            # Filename only, matching the desktop's window-title behavior —
            # not the full path, which for a remote-mounted test-data
            # directory can be long enough to dominate the header. The full
            # path is still one hover away via the tooltip.
            current_file_label.text = os.path.basename(path)
            current_file_label.tooltip(path)
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
                show_error(f"'{os.path.basename(path)}' is an .npz archive with {len(metas)} array(s) — pick one above.")
                hide_view_tabs()
                return

            if model.array.size == 0:
                show_error("Array is empty.")
                hide_view_tabs()
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

        # Before the first render, not after: this primes state.dark on all
        # three Plotly-based views (each set_dark() only actually re-renders
        # if data is already loaded, which it isn't yet at this point in
        # index() — so this call just stores the right value, and the very
        # FIRST figure any of them build already uses the correct template
        # instead of flashing light-then-dark). Also doubles as this page's
        # client.connected() signal (ui.run_javascript awaits it internally)
        # for the response_timeout race described below, regardless of which
        # branch runs next.
        await arm_system_dark_listener()
        await arm_window_resize_listener()

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
            # of ever showing a page to open the picker on. (Already
            # satisfied by arm_system_dark_listener() above, but kept
            # explicit here so this branch stays correct on its own if
            # anything before it is ever reordered.)
            await ui.context.client.connected()
            await open_picker()

    ui.run(host=host, port=port, title="npyquick serve", reload=False, show=False)
