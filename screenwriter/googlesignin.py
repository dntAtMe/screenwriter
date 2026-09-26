"""The "Sign in with Google" window: opens the browser, waits for Google's answer
on a one-off local address, and exchanges it for tokens."""

from __future__ import annotations

import html

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtNetwork import QHostAddress, QTcpServer
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from .google_drive import ClientConfig, DriveError, GoogleAccount, OAuthFlow, urllib_http

PAGE = """<!doctype html><meta charset="utf-8"><title>Screenwriter</title>
<body style="font:17px -apple-system,Segoe UI,sans-serif;text-align:center;padding:12vh 16px;background:#fbfaf7;color:#1f2328">
<h2>{title}</h2><p>{text}</p></body>"""


class SignInDialog(QDialog):
    def __init__(self, config: ClientConfig, parent=None, http=urllib_http, open_browser: bool = True):
        super().__init__(parent)
        self.setWindowTitle("Sign in with Google")
        self.setMinimumWidth(460)
        self.config, self.http = config, http
        self.account: GoogleAccount | None = None

        self.server = QTcpServer(self)
        if not self.server.listen(QHostAddress.SpecialAddress.LocalHost, 0):
            raise DriveError("Couldn't start the sign-in listener on this computer")
        self.server.newConnection.connect(self._on_connection)
        self.flow = OAuthFlow(config, f"http://127.0.0.1:{self.server.serverPort()}")

        self.message = QLabel(
            "<p><b>Continue in your browser.</b></p>"
            "<p>Sign in with Google and allow Screenwriter to keep its files in your Drive. "
            "It can only see files it creates — never the rest of your Drive.</p>"
            "<p style='color:gray'>This window closes by itself when you're done.</p>")
        self.message.setWordWrap(True)
        again = QPushButton("Open Browser Again")
        again.clicked.connect(self.open_browser)
        copy = QPushButton("Copy Link")
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.flow.authorization_url()))
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addWidget(again)
        buttons.addWidget(copy)
        buttons.addStretch()
        buttons.addWidget(cancel)
        layout = QVBoxLayout(self)
        layout.addWidget(self.message)
        layout.addLayout(buttons)
        if open_browser:
            self.open_browser()

    def open_browser(self) -> None:
        QDesktopServices.openUrl(QUrl(self.flow.authorization_url()))

    def _on_connection(self) -> None:
        socket = self.server.nextPendingConnection()
        socket.readyRead.connect(lambda s=socket: self._on_request(s))

    def _on_request(self, socket) -> None:
        request = bytes(socket.readAll()).decode("latin-1")
        try:
            path = request.split(" ", 2)[1]
        except IndexError:
            return
        if not path.startswith("/?"):  # e.g. /favicon.ico
            self._reply(socket, 404, "Not found", "")
            return
        try:
            code = self.flow.code_from_redirect(path)
            tokens = self.flow.exchange(code, self.http)
        except DriveError as e:
            self._reply(socket, 400, "Not signed in", html.escape(str(e)) + "<br>You can close this tab and try again.")
            self.message.setText(f"<p><b>Not signed in.</b></p><p>{html.escape(str(e))}</p>")
            return
        self._reply(socket, 200, "You're signed in",
                    "You can close this tab and go back to Screenwriter.")
        self.account = GoogleAccount(self.config, tokens, http=self.http)
        self.server.close()
        self.accept()

    @staticmethod
    def _reply(socket, status: int, title: str, text: str) -> None:
        body = PAGE.format(title=html.escape(title), text=text).encode()
        reason = {200: "OK", 400: "Bad Request", 404: "Not Found"}[status]
        socket.write(f"HTTP/1.1 {status} {reason}\r\nContent-Type: text/html; charset=utf-8\r\n"
                     f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode() + body)
        socket.flush()
        socket.disconnectFromHost()


def sign_in_with_google(config: ClientConfig, parent=None) -> GoogleAccount | None:
    try:
        dialog = SignInDialog(config, parent)
    except DriveError:
        return None
    return dialog.account if dialog.exec() else None
