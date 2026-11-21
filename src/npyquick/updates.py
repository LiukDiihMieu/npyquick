# SPDX-License-Identifier: GPL-3.0-or-later
"""GitHub release notifications for the Windows installer and AppImage."""
from __future__ import annotations

import json
import time
from urllib.parse import quote

from packaging.version import InvalidVersion, Version
from PySide6.QtCore import QDir, QEvent, QLockFile, QSettings, QStandardPaths, Qt, QTimer, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLayout, QMainWindow, QMenu,
    QToolButton, QVBoxLayout, QWidget,
)

from . import __version__


LATEST_RELEASE = "https://api.github.com/repos/LiukDiihMieu/npyquick/releases/latest"
DAY = 24 * 60 * 60


def _stable_version(tag: str) -> Version | None:
    try:
        version = Version(tag)
    except InvalidVersion:
        return None
    return None if version.is_prerelease else version


def _reserve_daily_check(settings: QSettings) -> bool:
    # Double-clicking several files can start several independent viewers.
    cache = QDir(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation))
    if not cache.mkpath("."):
        return False
    lock = QLockFile(cache.filePath("npyquick-release-check.lock"))
    if not lock.tryLock(0):
        return False
    try:
        settings.sync()
        now = int(time.time())
        last = settings.value("updates/lastAttempt", 0, type=int)
        if 0 <= now - last < DAY:
            return False
        settings.setValue("updates/lastAttempt", now)
        settings.sync()
        return True
    finally:
        lock.unlock()


class _UpdateCheckDialog(QDialog):
    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self.setWindowTitle("Check for updates")
        self.message = QLabel()
        self.message.setTextFormat(Qt.TextFormat.RichText)
        self.message.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.message.setOpenExternalLinks(True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        layout.addWidget(self.message)
        layout.addWidget(buttons)


class ReleaseUpdates(QWidget):
    def __init__(self, window: QMainWindow, menu: QMenu, repo_url: str) -> None:
        super().__init__(window)
        self._repo_url = repo_url
        self._settings = QSettings("npyquick", "npyquick")
        self._manager: QNetworkAccessManager | None = None
        self._reply: QNetworkReply | None = None
        self._dialog: _UpdateCheckDialog | None = None
        self._shown_tag = ""

        menu.addAction("Check for updates…", self._check_manually)
        self._automatic = menu.addAction("Automatically check for updates")
        self._automatic.setCheckable(True)
        self._automatic.setChecked(self._settings.value("updates/automatic", True, type=bool))
        self._automatic.toggled.connect(self._toggle_automatic)

        self._label = QLabel()
        self._label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self._label.setOpenExternalLinks(True)
        skip = QToolButton()
        skip.setText("×")
        skip.setAutoRaise(True)
        skip.setAccessibleName("Skip this version")
        skip.setToolTip("Skip this version")
        skip.clicked.connect(self._skip_version)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 2, 0)
        layout.setSpacing(4)
        layout.addWidget(self._label, alignment=Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(skip, alignment=Qt.AlignmentFlag.AlignVCenter)
        window.statusBar().addPermanentWidget(self)
        self.hide()

        self._startup = QTimer(self)
        self._startup.setSingleShot(True)
        self._startup.timeout.connect(self._check_automatically)
        window.installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.Paint:
            watched.removeEventFilter(self)
            self._startup.start(500)
        return False

    def _toggle_automatic(self, enabled: bool) -> None:
        self._settings.setValue("updates/automatic", enabled)
        if enabled:
            self._check_automatically()
        else:
            self.hide()

    def _check_automatically(self) -> None:
        if self._automatic.isChecked():
            self._show_cached()
            if self._reply is None and _reserve_daily_check(self._settings):
                self._check()

    def _check_manually(self) -> None:
        self._startup.stop()
        if self._dialog is None:
            self._dialog = _UpdateCheckDialog(self.window())
        self._dialog.message.setText("Checking for updates…")
        self._dialog.open()
        self._settings.setValue("updates/lastAttempt", int(time.time()))
        if self._reply is None:
            self._check()

    def _check(self) -> None:
        if self._manager is None:
            self._manager = QNetworkAccessManager(self)
        request = QNetworkRequest(QUrl(LATEST_RELEASE))
        request.setRawHeader(b"Accept", b"application/vnd.github+json")
        request.setRawHeader(b"User-Agent", b"npyquick")
        request.setTransferTimeout(5000)
        self._reply = self._manager.get(request)
        self._reply.finished.connect(self._finished)

    def _finished(self) -> None:
        reply = self._reply
        dialog = self._dialog if self._dialog and self._dialog.isVisible() else None
        self._reply = None
        reply.deleteLater()
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                raise ValueError
            release = json.loads(bytes(reply.readAll()))
            tag = release["tag_name"]
            if (release["draft"] is not False or release["prerelease"] is not False
                    or not isinstance(tag, str) or _stable_version(tag) is None):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            if dialog is not None:
                dialog.message.setText("Couldn’t check for updates. Try again later.")
            return

        self._settings.setValue("updates/latestTag", tag)
        link = self._show_cached()
        if dialog is not None:
            if link:
                dialog.message.setText(
                    f"Update available · {link}<br>You’re running npyquick {__version__}."
                )
            else:
                dialog.message.setText(f"npyquick {__version__} is up to date.")

    def _show_cached(self) -> str:
        """Refresh the automatic notice and return the release link for a manual check."""
        tag = self._settings.value("updates/latestTag", "", type=str)
        version = _stable_version(tag)
        if version is None or version <= Version(__version__):
            self.hide()
            return ""
        self._shown_tag = tag
        url = f"{self._repo_url}/releases/tag/{quote(tag, safe='')}"
        link = f'<a href="{url}">{version} ↗</a>'
        self._label.setText(f"Update available · {link}")
        skipped = self._settings.value("updates/skippedTag")
        self.setVisible(self._automatic.isChecked() and tag != skipped)
        return link

    def _skip_version(self) -> None:
        self._settings.setValue("updates/skippedTag", self._shown_tag)
        self.hide()
