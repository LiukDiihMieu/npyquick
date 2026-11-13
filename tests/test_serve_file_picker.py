# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 LiukDiihMieu

"""Framework-neutral tests for npyquick.serve.file_picker's pure directory-
listing helper, per AG_GRID_REPLACEMENT_PLAN.md's guidance to keep this
migration's coverage runnable as ordinary Python unit tests.

The root-boundary and no-client-supplied-path properties FilePicker itself
provides are NOT covered here by mounting a browser (this project has no
NiceGUI browser-testing harness set up, and the plan explicitly says not to
build an extensive one just for this migration) — they were instead verified
by hand, repeatedly, against a real running server this session: browsing
never showed a ".." row at the configured start directory, and every
row's on_click closure is a plain Python lambda bound to a server-side Path
object with no event-argument path in sight (visible directly in
file_picker.py — there is no code path where a client-supplied string ever
becomes a Path)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("nicegui")

from npyquick.serve.file_picker import _list_dir  # noqa: E402


def test_dirs_before_files_both_case_insensitive(tmp_path):
    (tmp_path / "banana.npy").touch()
    (tmp_path / "Apple.npy").touch()
    (tmp_path / "Zebra").mkdir()
    (tmp_path / "aardvark").mkdir()

    dirs, files, message = _list_dir(tmp_path)

    assert message is None
    assert [d.name for d in dirs] == ["aardvark", "Zebra"]
    assert [f.name for f in files] == ["Apple.npy", "banana.npy"]


def test_npy_and_npz_are_included_case_insensitively(tmp_path):
    (tmp_path / "a.npy").touch()
    (tmp_path / "b.NPY").touch()
    (tmp_path / "c.npz").touch()
    (tmp_path / "d.NPZ").touch()

    _, files, _ = _list_dir(tmp_path)

    assert {f.name for f in files} == {"a.npy", "b.NPY", "c.npz", "d.NPZ"}


def test_other_suffixes_are_excluded(tmp_path):
    (tmp_path / "keep.npy").touch()
    (tmp_path / "skip.txt").touch()
    (tmp_path / "skip.png").touch()
    (tmp_path / "skip").touch()  # no suffix at all

    _, files, _ = _list_dir(tmp_path)

    assert [f.name for f in files] == ["keep.npy"]


def test_filenames_with_html_special_characters_pass_through_as_plain_text(tmp_path):
    # There is no HTML-escaping step to test here BY DESIGN: unlike the
    # ui.aggrid version this replaced (which built raw HTML strings for
    # html_columns), this function returns plain Path objects and the
    # picker renders their .name through ui.item_label (confirmed via a
    # separate throwaway probe page to render as literal text, not
    # executed HTML) — so the only property to verify at this layer is
    # that the name simply isn't mangled or dropped.
    weird_name = "<img src=x onerror=alert(1)>weird&name.npy"
    (tmp_path / weird_name).touch()

    _, files, _ = _list_dir(tmp_path)

    assert [f.name for f in files] == [weird_name]


def test_unreadable_directory_returns_error_message_and_no_entries(tmp_path, monkeypatch):
    def fake_iterdir(self):
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "iterdir", fake_iterdir)

    dirs, files, message = _list_dir(tmp_path)

    assert dirs == []
    assert files == []
    assert message is not None
    assert "denied" in message


def test_empty_directory_lists_cleanly(tmp_path):
    dirs, files, message = _list_dir(tmp_path)
    assert dirs == []
    assert files == []
    assert message is None
