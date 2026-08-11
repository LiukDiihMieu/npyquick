# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 LiukDiihMieu

"""A directory browser dialog for picking a .npy/.npz file on the remote
machine's filesystem — there's no local file input to fall back on, since the
browser is remote from where the files actually live.

Built on ui.list/ui.item rather than the earlier ui.aggrid version: each
row's on_click closure captures the Path object directly, computed
server-side from our own directory listing — the browser only ever tells the
server "item N was clicked", never a path string. That's a stronger boundary
than accepting a client-supplied path and validating it after the fact:
there's no path for a tampered/forged client event to supply in the first
place, since none is ever sent. Filenames go through ui.item_label (plain
text interpolation — confirmed via a throwaway probe page that
"<img onerror=...>"-style content renders as escaped literal text, not
executed HTML) rather than the previous approach of interpolating raw
filenames into an HTML string for ui.aggrid's html_columns.
"""

from __future__ import annotations

from pathlib import Path

from nicegui import ui

_SUFFIXES = (".npy", ".npz")


def _list_dir(current_dir: Path) -> tuple[list[Path], list[Path], str | None]:
    """Directories then .npy/.npz files under `current_dir`, both sorted
    case-insensitively by name — or ([], [], message) if the directory
    can't be listed. Framework-neutral (no NiceGUI/ui element involved), so
    this is unit-testable directly without mounting a browser."""
    try:
        entries = list(current_dir.iterdir())
    except OSError as exc:
        return [], [], f"Can't list this directory: {exc}"

    dirs = sorted((e for e in entries if e.is_dir()), key=lambda p: p.name.lower())
    files = sorted(
        (e for e in entries if e.is_file() and e.suffix.lower() in _SUFFIXES),
        key=lambda p: p.name.lower(),
    )
    return dirs, files, None


class FilePicker(ui.dialog):
    def __init__(self, start_dir: str) -> None:
        super().__init__()
        self._current_dir = Path(start_dir).resolve()
        if not self._current_dir.is_dir():
            self._current_dir = self._current_dir.parent
        # Wherever browsing starts also bounds how far up it can go — no
        # separate --root flag, no case where the boundary and the starting
        # point disagree (see git history for the fuller rationale). Reaching
        # a symlink that points outside this tree is not specially blocked:
        # doing so still requires descending through directories the user
        # can already browse, which the listing already exposes regardless.
        self._root_dir = self._current_dir

        with self, ui.card().classes("w-full max-w-2xl"):
            self.path_label = ui.label().classes("text-sm text-gray-500")
            self.error_label = ui.label().classes("text-red-500")
            self.error_label.set_visibility(False)
            self.list_column = ui.column().classes("w-full gap-0").style("height: 24rem; overflow-y: auto")
            with ui.row().classes("w-full justify-end"):
                ui.button("Cancel", on_click=self.close)

        self._render()

    def _enter(self, path: Path) -> None:
        self._current_dir = path
        self._render()

    def _render(self) -> None:
        self.path_label.text = str(self._current_dir)
        self.error_label.set_visibility(False)
        self.list_column.clear()

        dirs, files, message = _list_dir(self._current_dir)
        if message:
            self.error_label.text = message
            self.error_label.set_visibility(True)

        with self.list_column, ui.list().props("separator").classes("w-full"):
            if self._current_dir != self._root_dir:
                self._row("arrow_upward", "..", on_click=lambda: self._enter(self._current_dir.parent))
            for d in dirs:
                self._row("folder", d.name, on_click=lambda p=d: self._enter(p))
            for f in files:
                self._row("description", f.name, on_click=lambda p=f: self.submit(str(p)))

    def _row(self, icon: str, label: str, *, on_click) -> None:
        with ui.item(on_click=on_click):
            with ui.item_section().props("avatar"):
                ui.icon(icon)
            with ui.item_section():
                ui.item_label(label)
