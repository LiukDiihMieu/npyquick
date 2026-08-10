# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 LiukDiihMieu

"""A directory browser dialog for picking a .npy/.npz file on the remote
machine's filesystem — there's no local file input to fall back on, since the
browser is remote from where the files actually live. Adapted from NiceGUI's
own documented `local_file_picker` example (a `ui.dialog` subclass + a
`ui.aggrid` listing, resolved via `submit()`/`await` rather than a callback) —
this gets row rendering and the dialog's own await-based result delivery for
free instead of hand-rolling a button-per-row list plus a manual callback.
"""

from __future__ import annotations

from pathlib import Path

from nicegui import events, ui

_SUFFIXES = (".npy", ".npz")


class FilePicker(ui.dialog):
    def __init__(self, start_dir: str) -> None:
        super().__init__()
        self._current_dir = Path(start_dir).resolve()
        if not self._current_dir.is_dir():
            self._current_dir = self._current_dir.parent
        # Wherever browsing STARTS also serves as the upper bound on where it
        # can go — that's already the file's own directory when one was given
        # on the command line, or the process's cwd otherwise (see cli.py).
        # No separate "root" concept/flag: exposing this dialog to a whole
        # filesystem via ".." was a real gap (this app can be pointed at a
        # non-loopback --host), and defining the boundary as "whatever this
        # instance was already anchored to" closes it with no new parameter
        # and no case where the boundary and the starting point disagree.
        self._root_dir = self._current_dir

        with self, ui.card().classes("w-full max-w-2xl"):
            self.path_label = ui.label().classes("text-sm text-gray-500")
            # html_columns=[0]: row names carry a "📁 <strong>" prefix for
            # directories, same as the upstream example, to visually
            # distinguish them from files without a second column. No
            # rowSelection: we only ever act on cellDoubleClicked (navigate or
            # pick), never read getSelectedRows(), so AG Grid's default
            # per-row + select-all checkbox column (which rowSelection would
            # otherwise render) would be pure clutter with no function.
            self.grid = ui.aggrid({
                "columnDefs": [{"field": "name", "headerName": ""}],
                "headerHeight": 0,
            }, html_columns=[0]).classes("w-full").style("height: 24rem")
            self.grid.on("cellDoubleClicked", self._handle_double_click)
            self.error_label = ui.label().classes("text-red-500")
            self.error_label.set_visibility(False)
            with ui.row().classes("w-full justify-end"):
                ui.button("Cancel", on_click=self.close)

        self._update_grid()

    def _update_grid(self) -> None:
        self.path_label.text = str(self._current_dir)
        self.error_label.set_visibility(False)

        try:
            entries = list(self._current_dir.iterdir())
        except OSError as exc:
            self.error_label.text = f"Can't list this directory: {exc}"
            self.error_label.set_visibility(True)
            entries = []

        dirs = sorted((e for e in entries if e.is_dir()), key=lambda p: p.name.lower())
        files = sorted(
            (e for e in entries if e.is_file() and e.suffix.lower() in _SUFFIXES),
            key=lambda p: p.name.lower(),
        )

        rows = []
        if self._current_dir != self._root_dir:
            rows.append({"name": "⬆ <strong>..</strong>", "path": str(self._current_dir.parent)})
        rows += [{"name": f"📁 <strong>{d.name}</strong>", "path": str(d)} for d in dirs]
        rows += [{"name": f"📄 {f.name}", "path": str(f)} for f in files]

        # Mutate the existing options dict in place rather than replacing it
        # wholesale — see serve/views/table.py's docstring for why: AG Grid's
        # Vue wrapper looks up options.theme on every (re)mount, and a bare
        # `self.grid.options = {...}` would drop it and crash the grid dead.
        self.grid.options["rowData"] = rows
        self.grid.update()

    def _handle_double_click(self, e: events.GenericEventArguments) -> None:
        path = Path(e.args["data"]["path"])
        if path.is_dir():
            self._current_dir = path
            self._update_grid()
        else:
            self.submit(str(path))
