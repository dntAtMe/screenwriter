import pytest
from PySide6.QtCore import QEventLoop, QSettings

from conftest import dispose
from screenwriter import __version__, newversion
from screenwriter.newversion import Release


def test_versions_compare_as_numbers():
    assert newversion.parse_version("v1.10.2") == (1, 10, 2)
    assert newversion.is_newer("1.10.0", "1.9.9") and newversion.is_newer("v2", "1.99")
    assert not newversion.is_newer("1.0", "1.0.0") and not newversion.is_newer("0.9.0", "1.0.0")
    assert not newversion.is_newer("nightly", "1.0.0")


def test_parse_release_skips_drafts_and_prereleases():
    data = {"tag_name": "v1.1.0", "html_url": "https://example/r", "body": " What's new \n"}
    assert newversion.parse_release(data) == Release("1.1.0", "https://example/r", "What's new")
    assert newversion.parse_release({**data, "prerelease": True}) is None
    assert newversion.parse_release({**data, "draft": True}) is None
    assert newversion.parse_release({"message": "Not Found"}) is None


def test_automatic_checks_are_daily():
    assert newversion.due(0)
    assert not newversion.due(1000, now=1000 + 3600)
    assert newversion.due(1000, now=1000 + newversion.DAY)


def wait_for(done, ms: int = 3000) -> None:
    """Run the event loop until done() (the answer came back on the main thread)."""
    import time

    end = time.monotonic() + ms / 1000
    while not done() and time.monotonic() < end:
        QEventLoop().processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)


def test_checker_answers_on_the_main_thread(qapp):
    got = []
    checker = newversion.Checker(fetch=lambda: Release("9.0.0", "u", ""))
    checker.finished.connect(lambda r, e: got.append((r, e)))
    checker.start()
    wait_for(lambda: got)
    assert got == [(Release("9.0.0", "u", ""), "")]

    def offline():
        raise OSError("no network")

    checker = newversion.Checker(fetch=offline)
    checker.finished.connect(lambda r, e: got.append((r, e)))
    checker.start()
    wait_for(lambda: len(got) == 2)
    assert got[-1] == (None, "no network")


@pytest.fixture
def window(qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from screenwriter.mainwindow import MainWindow

    QSettings().clear()
    w = MainWindow()
    w.messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a: w.messages.append(a[2]))
    yield w
    QSettings().clear()
    dispose(w)


def check(w, release, manual=False) -> None:
    w.version_checker.fetch = lambda: release
    w.check_for_updates(manual=manual)
    wait_for(lambda: not w.version_checker.busy)


def test_newer_version_shows_a_notice(window, monkeypatch):
    check(window, Release("9.0.0", "https://example/r", "Lots"))
    assert window.update_action.isVisible() and window.update_button.text() == "Update to 9.0.0"
    assert window.welcome.new_version.isVisibleTo(window.welcome) and "9.0.0" in window.welcome.new_version.text()
    assert window.messages == []  # automatic: no dialog

    # not again the same day
    window.version_checker.fetch = lambda: pytest.fail("checked twice in a day")
    window.check_for_updates()

    # skipping the version hides it, and automatic checks stay quiet about it
    from PySide6.QtWidgets import QMessageBox

    def click(box, text):
        next(b for b in box.buttons() if b.text() == text).click()
        return 0

    monkeypatch.setattr(QMessageBox, "exec", lambda box: click(box, "Skip This Version"))
    window.show_new_version()
    assert not window.update_action.isVisible()
    assert QSettings().value("updates/skipped") == "9.0.0"
    QSettings().setValue("updates/last_check", 0)
    check(window, Release("9.0.0", "u", ""))
    assert not window.update_action.isVisible()


def test_manual_check_always_answers(window, monkeypatch):
    check(window, Release(__version__, "u", ""), manual=True)
    assert window.messages == [f"You have the latest version, Screenwriter {__version__}."]
    assert not window.update_action.isVisible()

    def offline():
        raise OSError("no network")

    window.version_checker.fetch = offline
    window.check_for_updates(manual=True)
    wait_for(lambda: not window.version_checker.busy)
    assert "Couldn't reach GitHub" in window.messages[-1]


def test_automatic_check_can_be_turned_off(window):
    window.auto_update_action.setChecked(False)
    window.auto_update_action.triggered.emit()
    window.version_checker.fetch = lambda: pytest.fail("checked while turned off")
    window.check_for_updates()
    assert QSettings().value("updates/auto", type=bool) is False
