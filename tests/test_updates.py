import json
import runpy
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtNetwork import QNetworkReply
from PySide6.QtWidgets import QMenu, QToolButton

from npyquick import main, updates
from npyquick.app import MainWindow, REPO_URL


class Reply(QObject):
    finished = Signal()

    def __init__(self):
        super().__init__()
        self.network_error = QNetworkReply.NetworkError.NoError
        self.payload = b""

    def error(self):
        return self.network_error

    def readAll(self):
        return self.payload

    def release(self, tag):
        self.payload = json.dumps({"tag_name": tag, "draft": False, "prerelease": False}).encode()
        self.finished.emit()


@pytest.fixture
def desktop(tmp_path, monkeypatch):
    settings = QSettings(str(tmp_path / "updates.ini"), QSettings.IniFormat)
    monkeypatch.setattr(updates, "QSettings", lambda *args: settings)
    monkeypatch.setattr(updates.QStandardPaths, "writableLocation", lambda _: str(tmp_path))
    monkeypatch.setattr(updates, "__version__", "0.1.5")
    network = Mock()
    network.get.side_effect = lambda request: Reply()
    monkeypatch.setattr(updates, "QNetworkAccessManager", lambda parent: network)
    w = MainWindow(github_release_updates=True)
    yield w, w._updates, settings, network
    w.close()
    w.deleteLater()


def test_normal_install_has_no_update_controls(main_window):
    help_menu = next(menu for menu in main_window.findChildren(QMenu) if menu.title() == "&Help")
    assert [action.text() for action in help_menu.actions()] == ["&About npyquick"]
    assert not hasattr(main_window, "_updates")


def test_frozen_entry_opts_in(monkeypatch):
    launch = Mock()
    monkeypatch.setattr(main, "main", launch)
    entry = Path(__file__).resolve().parents[1] / "packaging/pyinstaller/npyquick_entry.py"
    runpy.run_path(str(entry), run_name="__main__")
    launch.assert_called_once_with(github_release_updates=True)


def test_first_paint_schedules_one_check(desktop, qapp):
    w, control, settings, network = desktop
    assert not control._startup.isActive()
    network.get.assert_not_called()
    w.show()
    qapp.processEvents()
    assert control._startup.isActive()
    control._startup.stop()
    control._check_automatically()
    assert network.get.call_args.args[0].url().toString() == updates.LATEST_RELEASE
    control._reply.release("v0.1.10")
    assert control._label.text() == (
        f'Update available · <a href="{REPO_URL}/releases/tag/v0.1.10">0.1.10 ↗</a>'
    )
    assert control._label.openExternalLinks()
    assert not control.isHidden()
    assert control._dialog is None
    w.statusBar().showMessage("Pixel (8, 3)")
    assert control.isVisible()
    control._check_automatically()
    network.get.assert_called_once()


def test_skip_is_per_version_and_manual_check_overrides_it(desktop):
    _, control, settings, network = desktop
    control._check_automatically()
    control._reply.release("v0.1.6")
    control.findChild(QToolButton).click()
    assert settings.value("updates/skippedTag") == "v0.1.6"
    control._check_automatically()
    assert control.isHidden()
    control._check_manually()
    control._reply.release("v0.1.6")
    assert control.isHidden()
    assert control._dialog.isVisible()
    assert f'href="{REPO_URL}/releases/tag/v0.1.6">0.1.6 ↗</a>' in control._dialog.message.text()
    assert control._dialog.message.openExternalLinks()
    control._dialog.close()
    settings.setValue("updates/lastAttempt", 0)
    control._check_automatically()
    control._reply.release("v0.1.7")
    assert not control.isHidden()
    assert network.get.call_count == 3


def test_disabled_automatic_checks_allow_manual_check(desktop):
    w, control, settings, network = desktop
    control._automatic.setChecked(False)
    assert settings.value("updates/automatic", type=bool) is False
    control._check_automatically()
    network.get.assert_not_called()
    menu = next(menu for menu in w.findChildren(QMenu) if menu.title() == "&Help")
    next(action for action in menu.actions() if action.text() == "Check for updates…").trigger()
    assert control._dialog.isVisible()
    assert control._dialog.message.text() == "Checking for updates…"
    control._reply.release("v0.1.5")
    assert control._dialog.message.text() == "npyquick 0.1.5 is up to date."
    assert control.isHidden()


def test_disable_while_automatic_request_is_pending(desktop):
    _, control, _, _ = desktop
    control._check_automatically()
    control._automatic.setChecked(False)
    control._reply.release("v0.1.10")
    assert control.isHidden()
    control._automatic.setChecked(True)
    assert not control.isHidden()


@pytest.mark.parametrize("bad_reply", [
    b"not JSON", b"[]", b'{"tag_name":"main","prerelease":false,"draft":false}',
    b'{"tag_name":"v2","prerelease":false,"draft":true}',
    b'{"tag_name":"v2rc1","prerelease":false,"draft":false}',
    b'{"tag_name":"v2","prerelease":true,"draft":false}',
])
def test_bad_response_is_silent_except_on_manual_check(desktop, bad_reply):
    w, control, settings, network = desktop
    settings.setValue("updates/latestTag", "v0.1.6")
    w.statusBar().showMessage("Viewing array")
    control._check_automatically()
    control._reply.payload = bad_reply
    control._reply.finished.emit()
    assert w.statusBar().currentMessage() == "Viewing array"
    assert control._dialog is None
    assert settings.value("updates/latestTag") == "v0.1.6"
    control._check_manually()
    control._reply.network_error = QNetworkReply.NetworkError.TimeoutError
    control._reply.finished.emit()
    assert control._dialog.isVisible()
    assert "Couldn’t check" in control._dialog.message.text()
    assert network.get.call_count == 2


def test_manual_check_reuses_inflight_request(desktop):
    _, control, _, network = desktop
    control._check_automatically()
    control._check_manually()
    network.get.assert_called_once()
    control._reply.release("v0.1.4")
    assert control._dialog.isVisible()
    assert "up to date" in control._dialog.message.text()


def test_dismiss_pending_manual_check(desktop):
    _, control, _, network = desktop
    control._automatic.setChecked(False)
    control._check_manually()
    control._dialog.reject()
    control._reply.release("v0.1.7")
    assert not control._dialog.isVisible()
    assert control.isHidden()
    network.get.assert_called_once()
