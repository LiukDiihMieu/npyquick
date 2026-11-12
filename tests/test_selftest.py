"""`npyquick --self-test` run against the source tree."""
from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from npyquick import selftest
from npyquick.main import app_icon


@pytest.fixture(autouse=True)
def window_icon():
    """main() sets the window icon; the shared test application has none."""
    QApplication.setWindowIcon(app_icon())
    yield
    QApplication.setWindowIcon(QIcon())


def test_self_test_passes_and_writes_the_report(tmp_path, capsys):
    report = tmp_path / "report.txt"

    assert selftest.run(report_path=str(report)) == 0

    text = report.read_text(encoding="utf-8")
    assert text == capsys.readouterr().out
    assert f"Result: {len(selftest.CHECKS)} passed, 0 failed" in text
    assert "FAIL" not in text


def test_failed_check_is_reported_and_the_rest_still_run(monkeypatch, capsys):
    def broken(window, workdir):
        raise selftest.CheckFailed("simulated")

    monkeypatch.setattr(selftest, "CHECKS", [("broken", broken), *selftest.CHECKS])

    assert selftest.run() == 1

    out = capsys.readouterr().out
    assert "FAIL  broken: CheckFailed: simulated" in out
    assert f"Result: {len(selftest.CHECKS) - 1} passed, 1 failed" in out


def test_error_dialog_fails_the_check_instead_of_blocking(monkeypatch, capsys):
    def opens_missing_file(window, workdir):
        window.load_file(str(workdir / "missing.npy"))  # would pop a modal dialog

    monkeypatch.setattr(selftest, "CHECKS", [("missing file", opens_missing_file)])

    assert selftest.run() == 1
    assert "FAIL  missing file: CheckFailed: Open failed" in capsys.readouterr().out


def test_user_settings_and_dialogs_are_left_as_they_were():
    store = QSettings("npyquick", "npyquick")
    store.setValue("recent_files", ["/somewhere/kept.npy"])
    store.setValue("last_dir", "/somewhere")
    warning = QMessageBox.warning

    selftest.run()

    store = QSettings("npyquick", "npyquick")
    assert store.value("recent_files") in ("/somewhere/kept.npy", ["/somewhere/kept.npy"])
    assert store.value("last_dir") == "/somewhere"
    assert QMessageBox.warning is warning
    store.clear()
