from PySide6.QtCore import QCoreApplication, QElapsedTimer
from PySide6.QtNetwork import QTcpSocket

from conftest import dispose
from fake_google import EMAIL, FakeGoogle
from screenwriter.google_drive import ClientConfig, GoogleAccount, MemoryTokenStore, OAuthFlow
from screenwriter.googlesignin import SignInDialog
from screenwriter.mainwindow import MainWindow
from screenwriter.synctargets import DriveTarget

CONFIG = ClientConfig("client-123.apps.googleusercontent.com", "not-really-secret")


def browser_redirect(port: int, path: str) -> str:
    """What the browser does after Google's page: GET the local address. Returns the response."""
    socket = QTcpSocket()
    socket.connectToHost("127.0.0.1", port)
    assert socket.waitForConnected(2000)
    socket.write(f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n".encode())
    socket.flush()
    timer = QElapsedTimer()
    timer.start()
    received = b""
    while timer.elapsed() < 3000 and b"</body>" not in received:
        QCoreApplication.processEvents()
        socket.waitForReadyRead(20)
        received += bytes(socket.readAll())
    return received.decode("utf-8", "replace")


def test_sign_in_dialog_receives_googles_answer(qapp):
    google = FakeGoogle()
    dialog = SignInDialog(CONFIG, http=google.http, open_browser=False)
    port = dialog.server.serverPort()
    forged = browser_redirect(port, "/?state=forged&code=good-code")
    assert "400" in forged.split("\r\n")[0] and dialog.account is None
    reply = browser_redirect(port, f"/?state={dialog.flow.state}&code=good-code")
    assert reply.startswith("HTTP/1.1 200") and "signed in</h2>" in reply
    assert dialog.account is not None and dialog.account.email == EMAIL
    dialog.deleteLater()


def test_main_window_google_drive_flow(qapp, sample_project, tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QMessageBox

    QSettings().clear()
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    google = FakeGoogle()

    def account():
        tokens = OAuthFlow(CONFIG, "http://127.0.0.1:1").exchange("good-code", google.http)
        return GoogleAccount(CONFIG, tokens, MemoryTokenStore(), google.http)

    desktop = MainWindow()
    desktop.google_config, desktop.google_account = CONFIG, account()
    monkeypatch.setattr(desktop, "_drive_cache", lambda: tmp_path / "cache-desktop")
    desktop.open_project(sample_project)
    desktop._set_target(DriveTarget(desktop._drive_client(), desktop.project.id, None, tmp_path / "cache-desktop"))
    assert desktop.sync_now().status == "uploaded"
    assert desktop.settings.value(f"sync/{desktop.project.id}").startswith("gdrive:f")

    desktop.settings.remove(f"sync_local/{desktop.project.id}")
    laptop = MainWindow()
    laptop.google_config, laptop.google_account = CONFIG, account()
    monkeypatch.setattr(laptop, "_drive_cache", lambda: tmp_path / "cache-laptop")
    [remote] = laptop._drive_client().list_projects()
    laptop.open_from_google_drive(remote.id, str(tmp_path / "laptop"))
    laptop.history.machine = "Laptop"
    assert laptop.project.id == desktop.project.id and laptop.sync_target.kind == "gdrive"

    laptop.open_document("ch01")
    laptop.editors["ch01"].replace_all("From the laptop, via Google Drive.")
    assert laptop.sync_now().status == "uploaded"
    desktop.open_document("ch01")
    desktop._check_cloud()  # the minute timer notices the change and pulls it
    assert desktop.editors["ch01"].text() == "From the laptop, via Google Drive."

    desktop.sign_out_google()
    assert desktop.google_account is None and desktop.sync_now(quiet=True) is None
    assert "Not syncing" in desktop.sync_label.text()
    dispose(laptop, desktop)
