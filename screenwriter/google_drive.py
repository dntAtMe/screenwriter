"""Google Drive: sign in with Google and keep projects in Drive directly.

- Sign-in is OAuth 2.0 for desktop apps: the browser opens Google's page, and Google
  sends the answer back to a one-off local address (http://127.0.0.1:<port>). PKCE
  protects the exchange. See https://developers.google.com/identity/protocols/oauth2/native-app
- Scope `drive.file`: the app sees only files it created itself — never the rest of Drive.
- Projects are the same `.screenwriter` package files as cloud-folder sync (sync.py),
  kept in a "Screenwriter" folder in My Drive and tagged with appProperties.
- The sign-in is remembered in the system's secure store (keyring).

Plain urllib keeps the app free of the heavy Google client libraries. The HTTP
function is injectable so tests run against a fake Drive.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
API = "https://www.googleapis.com/drive/v3"
UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"
SCOPES = "https://www.googleapis.com/auth/drive.file openid email"
FOLDER_NAME = "Screenwriter"
FOLDER_MIME = "application/vnd.google-apps.folder"
PACKAGE_MIME = "application/zip"
FILE_FIELDS = "id,name,modifiedTime,version,appProperties"
KEYRING_SERVICE = "Screenwriter"
KEYRING_USER = "google-account"

# (method, url, headers, body) -> (status, headers, body)
Http = Callable[[str, str, dict, bytes | None], tuple[int, dict, bytes]]


class DriveError(Exception):
    pass


def urllib_http(method: str, url: str, headers: dict, body: bytes | None) -> tuple[int, dict, bytes]:
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise DriveError(f"Can't reach Google ({getattr(e, 'reason', e)})") from e


# --- app credentials ------------------------------------------------------------------------


@dataclass
class ClientConfig:
    client_id: str
    client_secret: str


def load_client_config() -> ClientConfig | None:
    """The app's Google OAuth client: from the environment, or a google_client.json
    written into the build by the release workflow (see docs/google-drive-setup.md)."""
    client_id = os.environ.get("SCREENWRITER_GOOGLE_CLIENT_ID")
    secret = os.environ.get("SCREENWRITER_GOOGLE_CLIENT_SECRET")
    if client_id and secret:
        return ClientConfig(client_id, secret)
    path = Path(__file__).resolve().parent / "resources" / "google_client.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data = data.get("installed", data)  # accept the file Google Cloud Console downloads, too
        return ClientConfig(data["client_id"], data["client_secret"])
    except (OSError, ValueError, KeyError):
        return None


# --- signing in -------------------------------------------------------------------------------


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


@dataclass
class Tokens:
    access_token: str
    refresh_token: str
    expires_at: float
    email: str = ""


class OAuthFlow:
    """One sign-in attempt: build the browser URL, check the redirect, exchange the code."""

    def __init__(self, config: ClientConfig, redirect_uri: str):
        self.config = config
        self.redirect_uri = redirect_uri
        self.verifier = secrets.token_urlsafe(64)
        self.state = secrets.token_urlsafe(16)

    def authorization_url(self) -> str:
        challenge = _b64url(hashlib.sha256(self.verifier.encode()).digest())
        return AUTH_URL + "?" + urllib.parse.urlencode({
            "client_id": self.config.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": SCOPES,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": self.state,
            "access_type": "offline",
            "prompt": "consent",
        })

    def code_from_redirect(self, path: str) -> str:
        """The authorization code from the redirect's path + query."""
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)
        if query.get("state", [""])[0] != self.state:
            raise DriveError("Sign-in answer didn't match this request — please try again")
        if "error" in query:
            error = query["error"][0]
            raise DriveError("Sign-in was cancelled" if error == "access_denied" else f"Google said: {error}")
        if "code" not in query:
            raise DriveError("Google didn't send a sign-in code")
        return query["code"][0]

    def exchange(self, code: str, http: Http = urllib_http) -> Tokens:
        data = _post_form(http, TOKEN_URL, {
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "code": code,
            "code_verifier": self.verifier,
            "grant_type": "authorization_code",
            "redirect_uri": self.redirect_uri,
        })
        return Tokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", ""),
            expires_at=time.time() + int(data.get("expires_in", 3600)),
            email=_email_from_id_token(data.get("id_token", "")),
        )


def _post_form(http: Http, url: str, fields: dict) -> dict:
    status, _, body = http("POST", url, {"Content-Type": "application/x-www-form-urlencoded"},
                           urllib.parse.urlencode(fields).encode())
    data = json.loads(body or b"{}")
    if status != 200:
        raise DriveError(data.get("error_description") or data.get("error") or f"Google sign-in failed ({status})")
    return data


def _email_from_id_token(id_token: str) -> str:
    """The account's email, for display. (The token came straight from Google over TLS.)"""
    try:
        payload = id_token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))).get("email", "")
    except (IndexError, ValueError):
        return ""


class TokenStore:
    """Keeps the refresh token in the system's secure store."""

    def load(self) -> dict | None:
        try:
            import keyring

            raw = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
        except Exception:  # no usable keyring backend on this system
            return None
        return json.loads(raw) if raw else None

    def save(self, data: dict) -> bool:
        try:
            import keyring

            keyring.set_password(KEYRING_SERVICE, KEYRING_USER, json.dumps(data))
            return True
        except Exception:
            return False

    def clear(self) -> None:
        try:
            import keyring

            keyring.delete_password(KEYRING_SERVICE, KEYRING_USER)
        except Exception:
            pass


class MemoryTokenStore(TokenStore):
    def __init__(self):
        self.data = None

    def load(self):
        return self.data

    def save(self, data):
        self.data = data
        return True

    def clear(self):
        self.data = None


class GoogleAccount:
    def __init__(self, config: ClientConfig, tokens: Tokens, store: TokenStore | None = None, http: Http = urllib_http):
        self.config, self.tokens, self.http = config, tokens, http
        self.store = store or TokenStore()

    @property
    def email(self) -> str:
        return self.tokens.email

    @classmethod
    def restore(cls, config: ClientConfig, store: TokenStore | None = None, http: Http = urllib_http) -> GoogleAccount | None:
        """The signed-in account remembered from last time, if any."""
        store = store or TokenStore()
        data = store.load()
        if not data or not data.get("refresh_token"):
            return None
        return cls(config, Tokens("", data["refresh_token"], 0, data.get("email", "")), store, http)

    def remember(self) -> bool:
        return self.store.save({"refresh_token": self.tokens.refresh_token, "email": self.tokens.email})

    def access_token(self) -> str:
        if not self.tokens.access_token or time.time() > self.tokens.expires_at - 60:
            self.refresh()
        return self.tokens.access_token

    def refresh(self) -> None:
        data = _post_form(self.http, TOKEN_URL, {
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "refresh_token": self.tokens.refresh_token,
            "grant_type": "refresh_token",
        })
        self.tokens.access_token = data["access_token"]
        self.tokens.expires_at = time.time() + int(data.get("expires_in", 3600))

    def sign_out(self) -> None:
        try:
            self.http("POST", REVOKE_URL + "?" + urllib.parse.urlencode({"token": self.tokens.refresh_token}),
                      {"Content-Type": "application/x-www-form-urlencoded"}, b"")
        except DriveError:
            pass  # offline: forgetting it locally is what matters
        self.store.clear()


# --- Drive ----------------------------------------------------------------------------------------


@dataclass
class DriveFile:
    id: str
    name: str
    modified: str
    version: str
    properties: dict

    @property
    def project_id(self) -> str:
        return self.properties.get("project_id", "")

    @classmethod
    def from_json(cls, d: dict) -> DriveFile:
        return cls(d["id"], d.get("name", ""), d.get("modifiedTime", ""), str(d.get("version", "")), d.get("appProperties") or {})


class DriveClient:
    def __init__(self, account: GoogleAccount):
        self.account = account
        self._folder_id: str | None = None

    def _request(self, method: str, url: str, body: bytes | None = None, headers: dict | None = None,
                 expect_json: bool = True):
        for attempt in (1, 2):
            all_headers = {"Authorization": f"Bearer {self.account.access_token()}", **(headers or {})}
            status, response_headers, data = self.account.http(method, url, all_headers, body)
            if status == 401 and attempt == 1:
                self.account.refresh()
                continue
            break
        if status >= 400:
            try:
                message = json.loads(data)["error"]["message"]
            except (ValueError, KeyError, TypeError):
                message = data[:200].decode("utf-8", "replace")
            raise DriveError(f"Google Drive: {message} ({status})")
        if not expect_json:
            return status, response_headers, data
        return json.loads(data or b"{}")

    def _list(self, query: str) -> list[DriveFile]:
        params = urllib.parse.urlencode({"q": query, "fields": f"files({FILE_FIELDS})", "spaces": "drive", "pageSize": 200})
        return [DriveFile.from_json(f) for f in self._request("GET", f"{API}/files?{params}").get("files", [])]

    def app_folder(self) -> str:
        """The "Screenwriter" folder in My Drive (created on first use)."""
        if self._folder_id:
            return self._folder_id
        found = self._list(f"name = '{FOLDER_NAME}' and mimeType = '{FOLDER_MIME}' and trashed = false")
        if found:
            self._folder_id = found[0].id
        else:
            body = json.dumps({"name": FOLDER_NAME, "mimeType": FOLDER_MIME}).encode()
            self._folder_id = self._request("POST", f"{API}/files?fields=id", body, {"Content-Type": "application/json"})["id"]
        return self._folder_id

    def list_projects(self) -> list[DriveFile]:
        return self._list("appProperties has { key='screenwriter' and value='1' } and trashed = false")

    def find_project(self, project_id: str) -> DriveFile | None:
        return next((f for f in self.list_projects() if f.project_id == project_id), None)

    def metadata(self, file_id: str) -> DriveFile:
        return DriveFile.from_json(self._request("GET", f"{API}/files/{file_id}?fields={FILE_FIELDS}"))

    def download(self, file_id: str, dest: Path) -> None:
        _, _, data = self._request("GET", f"{API}/files/{file_id}?alt=media", expect_json=False)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, dest)

    def upload(self, path: Path, name: str, project_id: str, file_id: str | None = None,
               properties: dict | None = None) -> DriveFile:
        """Create or replace a project package (resumable upload: any size)."""
        metadata: dict = {"name": name, "appProperties": {"screenwriter": "1", "project_id": project_id, **(properties or {})}}
        if file_id:
            start = f"{UPLOAD_API}/files/{file_id}?uploadType=resumable&fields={FILE_FIELDS}"
            method = "PATCH"
        else:
            metadata["parents"] = [self.app_folder()]
            metadata["mimeType"] = PACKAGE_MIME
            start = f"{UPLOAD_API}/files?uploadType=resumable&fields={FILE_FIELDS}"
            method = "POST"
        data = path.read_bytes()
        _, headers, _ = self._request(method, start, json.dumps(metadata).encode(), {
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": PACKAGE_MIME,
            "X-Upload-Content-Length": str(len(data)),
        }, expect_json=False)
        location = headers.get("Location") or headers.get("location")
        if not location:
            raise DriveError("Google Drive didn't accept the upload")
        _, _, body = self._request("PUT", location, data, {"Content-Type": PACKAGE_MIME}, expect_json=False)
        return DriveFile.from_json(json.loads(body))

    def set_properties(self, file_id: str, properties: dict) -> None:
        """Update a few appProperties (a value of None removes the key)."""
        body = json.dumps({"appProperties": properties}).encode()
        self._request("PATCH", f"{API}/files/{file_id}?fields=id", body, {"Content-Type": "application/json"})
