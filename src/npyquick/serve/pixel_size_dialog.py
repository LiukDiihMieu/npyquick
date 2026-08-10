# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 LiukDiihMieu

"""Pixel-size/physical-unit dialog. Ported from views/pixel_size_dialog.py,
sharing the same arithmetic-expression evaluator (core/pixel_expr.py) so an
expression like "3.45/10" parses identically on both the desktop and here.

A `ui.dialog` subclass resolved via `submit()`/`await` (see serve/file_picker.py
for the same pattern) rather than an injected on_apply callback, and
`ui.input`'s own `validation` mechanism for the inline error message rather
than a manually toggled error label — NiceGUI already re-validates on every
keystroke and renders the error under the field itself.

No expression history: the desktop persists the last 5 expressions via
QSettings, but there's no equivalent single-user local settings store for a
browser session, and it's not worth reaching for app.storage.browser just for
this — a plain default of "1" is a fine starting point each time.
"""

from __future__ import annotations

from nicegui import ui

from npyquick.core.pixel_expr import UNITS, eval_expr


class PixelSizeDialog(ui.dialog):
    def __init__(self) -> None:
        super().__init__()
        self._expr = "1"
        self._unit = "None"

        # min-width: an unconstrained ui.card shrinks to whatever's smallest
        # among its children, which left the Expression/Unit fields only
        # ~160px wide — too cramped to comfortably type/read an expression.
        # dense + an explicit gap tighten the default Quasar per-field
        # spacing (each field normally reserves room below it for hint/error
        # text even when none is shown), which was leaving oddly large gaps
        # between stacked fields.
        with self, ui.card().classes("min-w-[22rem]"):
            ui.label("Set Pixel Size").classes("text-lg font-bold")
            with ui.column().classes("w-full gap-3"):
                self.expr_input = ui.input(
                    "Expression", placeholder="e.g.  3.45/10  or  0.5",
                    validation=self._validate_expr,
                ).classes("w-full").props("dense")
                self.unit_select = ui.select(UNITS, label="Unit").classes("w-full").props("dense")
            with ui.row().classes("w-full justify-end"):
                ui.button("Cancel", on_click=self.close)
                ui.button("OK", on_click=self._on_ok)

    @staticmethod
    def _validate_expr(text: str) -> str | None:
        try:
            eval_expr(text)
        except Exception as exc:  # noqa: BLE001 - message surfaced inline
            return str(exc)
        return None

    def open(self) -> None:  # noqa: A003 - overrides OpenableElement.open, not builtins.open
        # Re-prime the fields with the last-applied values every time the
        # dialog is (re)opened — Dialog.__await__ calls this itself before
        # waiting on submit(), so `result = await dialog` already shows the
        # right starting values with no separate setup step needed by callers.
        self.expr_input.value = self._expr
        self.unit_select.value = self._unit
        super().open()

    def _on_ok(self) -> None:
        if not self.expr_input.validate():
            return
        expr = self.expr_input.value.strip()
        value = eval_expr(expr)  # safe: validate() above already confirmed this parses
        unit = self.unit_select.value
        self._expr = expr
        self._unit = unit
        self.submit((value, expr, unit))
