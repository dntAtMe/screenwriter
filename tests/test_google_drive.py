import urllib.parse

import pytest

from fake_google import EMAIL, FakeGoogle
from screenwriter.google_drive import (
    ClientConfig,
    DriveClient,
    DriveError,
    GoogleAccount,
    MemoryTokenStore,
    OAuthFlow,
    load_client_config,
)
from screenwriter.merge import load_conflicts
from screenwriter.project import PROSE, Project
from screenwriter.projecthistory import ProjectHistory
from screenwriter.sync import open_package, sync
from screenwriter.synctargets import DriveTarget, target_from_key, FolderTarget

CONFIG = ClientConfig("client-123.apps.googleusercontent.com", "not-really-secret")


@pytest.fixture
def google():
    return FakeGoogle()


def signed_in(google, store=None):
    flow = OAuthFlow(CONFIG, "http://127.0.0.1:5555")
    tokens = flow.exchange("good-code", google.http)
    return GoogleAccount(CONFIG, tokens, store or MemoryTokenStore(), google.http)


def test_authorization_url_and_redirect_checks():
    flow = OAuthFlow(CONFIG, "http://127.0.0.1:5555")
    params = urllib.parse.parse_qs(urllib.parse.urlsplit(flow.authorization_url()).query)
    assert params["scope"] == ["https://www.googleapis.com/auth/drive.file openid email"]
    assert params["code_challenge_method"] == ["S256"] and params["redirect_uri"] == ["http://127.0.0.1:5555"]
    assert flow.code_from_redirect(f"/?state={flow.state}&code=abc") == "abc"
    with pytest.raises(DriveError, match="didn't match"):
        flow.code_from_redirect("/?state=forged&code=abc")
    with pytest.raises(DriveError, match="cancelled"):
        flow.code_from_redirect(f"/?state={flow.state}&error=access_denied")


def test_sign_in_remember_restore_and_refresh(google):
    store = MemoryTokenStore()
    account = signed_in(google, store)
    assert account.email == EMAIL and account.tokens.refresh_token == "refresh-1"
    assert account.remember()
    again = GoogleAccount.restore(CONFIG, store, google.http)
    assert again.email == EMAIL
    assert again.access_token() in google.valid_tokens  # refreshed on first use
    account.sign_out()
    assert GoogleAccount.restore(CONFIG, store, google.http) is None


def test_bad_code_is_reported(google):
    with pytest.raises(DriveError):
        OAuthFlow(CONFIG, "http://127.0.0.1:1").exchange("wrong", google.http)


def test_drive_client_folder_upload_download(google, tmp_path):
    client = DriveClient(signed_in(google))
    folder = client.app_folder()
    assert client.app_folder() == folder and DriveClient(client.account).app_folder() == folder  # found, not recreated
    package = tmp_path / "Story.screenwriter"
    package.write_bytes(b"v1")
    created = client.upload(package, "Story.screenwriter", "pid-1", properties={"head": "abc"})
    assert google.files[created.id]["parents"] == [folder]
    assert client.find_project("pid-1").id == created.id and created.properties["head"] == "abc"
    package.write_bytes(b"v2")
    updated = client.upload(package, "Story.screenwriter", "pid-1", created.id)
    assert updated.id == created.id and int(updated.version) > int(created.version)
    client.download(created.id, tmp_path / "copy")
    assert (tmp_path / "copy").read_bytes() == b"v2"
    client.set_properties(created.id, {"open_on": "Laptop"})
    assert client.metadata(created.id).properties["open_on"] == "Laptop"


def test_expired_access_token_is_refreshed(google, tmp_path):
    client = DriveClient(signed_in(google))
    client.app_folder()
    google.expire_tokens()  # e.g. revoked server-side; the client refreshes once and retries
    assert client.list_projects() == []


def test_config_from_environment(monkeypatch):
    monkeypatch.setenv("SCREENWRITER_GOOGLE_CLIENT_ID", "id")
    monkeypatch.setenv("SCREENWRITER_GOOGLE_CLIENT_SECRET", "secret")
    assert load_client_config() == ClientConfig("id", "secret")


def test_target_from_key(tmp_path):
    assert isinstance(target_from_key(str(tmp_path / "a.screenwriter"), "p", None, tmp_path), FolderTarget)
    target = target_from_key("gdrive:f9", "p", None, tmp_path)
    assert isinstance(target, DriveTarget) and target.file_id == "f9" and not target.available()


class Computer:
    def __init__(self, path, name, google, cache):
        self.project = Project.open(path)
        self.history = ProjectHistory(path)
        self.history.machine = name
        self.target = DriveTarget(DriveClient(signed_in(google)), self.project.id, None, cache)

    def sync(self):
        self.history.save_point()
        package = self.target.prepare(self.project)
        result = sync(self.history, self.project.id, self.project.name, package)
        self.target.finish(result, self.project)
        self.project = Project.open(self.project.path)
        return result


def test_two_computers_sync_through_drive(google, tmp_path):
    p = Project.create(tmp_path / "desktop" / "Story", "Story")
    chapter = p.new_node(PROSE, "Chapter 1")
    p.root.insert(0, chapter)
    p.save()
    p.write_text(chapter, "One.")
    desktop = Computer(p.path, "Desktop", google, tmp_path / "cache-desktop")
    assert desktop.sync().status == "uploaded"
    assert desktop.sync().status == "up-to-date"
    assert not desktop.target.changed()

    # the laptop finds the project in Drive and opens it
    client = DriveClient(signed_in(google))
    [remote] = client.list_projects()
    client.download(remote.id, tmp_path / "download.screenwriter")
    laptop = Computer(open_package(tmp_path / "download.screenwriter", tmp_path / "laptop"), "Laptop", google, tmp_path / "cache-laptop")
    laptop.target.file_id = remote.id
    assert laptop.sync().status == "up-to-date"

    laptop.project.write_text(laptop.project.find(chapter.id), "One, from the laptop.")
    assert laptop.sync().status == "uploaded"
    assert desktop.target.changed()
    assert desktop.sync().status == "downloaded"
    assert desktop.project.read_text(desktop.project.find(chapter.id)) == "One, from the laptop."

    # both edit: merge, with the other version waiting in conflicts.json for both of them
    laptop.project.write_text(laptop.project.find(chapter.id), "Laptop.")
    laptop.sync()
    desktop.project.write_text(desktop.project.find(chapter.id), "Desktop.")
    result = desktop.sync()
    assert result.status == "merged" and result.conflicts
    assert laptop.sync().status == "downloaded"
    [record] = load_conflicts(laptop.project.path)
    assert (record.kept, record.other) == ("Desktop.", "Laptop.")

    # presence
    laptop.target.lock("Laptop", laptop.project.id)
    desktop.target.changed()  # refreshes what we know about the file
    assert desktop.target.other_machine("Desktop") == "Laptop"
    laptop.target.unlock("Laptop")
    desktop.target.changed()
    assert desktop.target.other_machine("Desktop") is None


def test_file_deleted_in_drive_is_recreated(google, tmp_path):
    p = Project.create(tmp_path / "Story", "Story")
    computer = Computer(p.path, "Desktop", google, tmp_path / "cache")
    computer.sync()
    google.files[computer.target.file_id]["trashed"] = True
    old_id = computer.target.file_id
    assert computer.sync().status == "uploaded"
    assert computer.target.file_id != old_id
