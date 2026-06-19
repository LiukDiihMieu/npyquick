"""Tab-switching hotkeys (issues #25 and #26).

#25 (Linux/Windows): Ctrl+Shift+Tab never moved to the previous tab. Root cause
(QTBUG-8010): StandardKey.PreviousChild resolves to "Ctrl+Shift+Backtab", but
Shift+Tab is delivered as a bare Qt.Key_Backtab with the Shift consumed, so that
sequence can never match. The fix registers "Ctrl+Backtab".

#26 (macOS): StandardKey.NextChild/PreviousChild land on ⌘+Tab / ⌘+Shift+Tab,
which the OS reserves for app switching. On macOS we instead bind the physical
Control key (Qt.MetaModifier) plus the Safari-style ⌘+Shift+] / ⌘+Shift+[.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtGui import QKeySequence, QShortcut

from npyquick.app import _tab_switch_sequences


def _portable(seqs):
    return [s.toString(QKeySequence.PortableText) for s in seqs]


# ---------------------------------------------------------------------------
# Platform sequence selection (host-independent: _tab_switch_sequences takes the
# platform string, so both branches are exercised on any OS).
# ---------------------------------------------------------------------------

def test_linux_sequences():
    nxt, prev = _tab_switch_sequences("linux")
    assert _portable(nxt) == ["Ctrl+Tab"]
    # Ctrl+Backtab, NOT the unmatchable Ctrl+Shift+Backtab from #25.
    assert _portable(prev) == ["Ctrl+Backtab"]


def test_windows_sequences_match_linux():
    assert _portable(_tab_switch_sequences("win32")[0]) == ["Ctrl+Tab"]
    assert _portable(_tab_switch_sequences("win32")[1]) == ["Ctrl+Backtab"]


def test_macos_avoids_cmd_tab():
    nxt, prev = _tab_switch_sequences("darwin")
    next_seqs, prev_seqs = _portable(nxt), _portable(prev)
    # Qt.MetaModifier -> physical Control on macOS (rendered "Meta" off-Mac);
    # Qt.ControlModifier -> ⌘ (rendered "Ctrl"). So the bracket combos below are
    # ⌘+Shift+] / ⌘+Shift+[ at runtime, and "Meta+..." is physical Ctrl+...
    assert next_seqs == ["Meta+Tab", "Ctrl+Shift+]"]
    assert prev_seqs == ["Meta+Backtab", "Ctrl+Shift+["]
    # Nothing must bind plain ⌘+Tab (rendered "Ctrl+Tab") — that's the conflict.
    assert "Ctrl+Tab" not in next_seqs


def test_no_ambiguous_overlap_between_next_and_prev():
    for platform in ("linux", "win32", "darwin"):
        nxt, prev = _tab_switch_sequences(platform)
        assert set(_portable(nxt)).isdisjoint(_portable(prev))


# ---------------------------------------------------------------------------
# Wiring: the window registers exactly those sequences as QShortcuts.
# ---------------------------------------------------------------------------

def test_window_registers_platform_sequences(main_window):
    registered = {
        sc.key().toString(QKeySequence.PortableText)
        for sc in main_window.findChildren(QShortcut)
    }
    nxt, prev = _tab_switch_sequences()
    for seq in _portable(nxt) + _portable(prev):
        assert seq in registered


# ---------------------------------------------------------------------------
# Navigation behaviour (platform-independent).
# ---------------------------------------------------------------------------

def _load_2d(main_window, write_npy):
    main_window.load_file(write_npy(np.arange(12.0).reshape(3, 4)))
    tabs = main_window._tabs
    assert tabs.isVisible()
    enabled = [i for i in range(tabs.count()) if tabs.isTabEnabled(i)]
    assert len(enabled) >= 2
    return tabs


def test_next_then_prev_roundtrips(main_window, write_npy):
    tabs = _load_2d(main_window, write_npy)
    start = tabs.currentIndex()
    main_window._next_tab()
    assert tabs.currentIndex() != start
    main_window._prev_tab()
    assert tabs.currentIndex() == start


def test_prev_lands_on_enabled_tab(main_window, write_npy):
    tabs = _load_2d(main_window, write_npy)
    main_window._prev_tab()
    assert tabs.isTabEnabled(tabs.currentIndex())


def test_tab_switch_noop_without_data(main_window):
    assert not main_window._tabs.isVisible()
    main_window._next_tab()
    main_window._prev_tab()
