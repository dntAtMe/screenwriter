"""An in-memory stand-in for Google's token endpoint and the Drive calls the app uses."""

import base64
import itertools
import json
import urllib.parse

from screenwriter.google_drive import API, TOKEN_URL, UPLOAD_API

EMAIL = "writer@example.com"


def _id_token(email: str) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"email": email}).encode()).rstrip(b"=").decode()
    return f"header.{payload}.signature"


class FakeGoogle:
    def __init__(self):
        self.files: dict[str, dict] = {}  # id -> {name, mimeType, parents, appProperties, content, version, trashed}
        self.valid_tokens = set()
        self.uploads: dict[str, dict] = {}
        self._ids = itertools.count(1)
        self.calls = []

    def _new_id(self, prefix="f"):
        return f"{prefix}{next(self._ids)}"

    def _token(self):
        token = self._new_id("access")
        self.valid_tokens.add(token)
        return token

    def expire_tokens(self):
        self.valid_tokens.clear()

    def http(self, method, url, headers, body):
        self.calls.append((method, url.split("?")[0]))
        split = urllib.parse.urlsplit(url)
        query = urllib.parse.parse_qs(split.query)
        base = f"{split.scheme}://{split.netloc}{split.path}"
        if base == TOKEN_URL:
            return self._token_endpoint(urllib.parse.parse_qs(body.decode()))
        if base.startswith("https://fake-upload/"):
            return self._finish_upload(base.rsplit("/", 1)[1], body)
        auth = headers.get("Authorization", "")
        if auth.removeprefix("Bearer ") not in self.valid_tokens:
            return 401, {}, json.dumps({"error": {"message": "Invalid Credentials"}}).encode()
        if base.startswith(UPLOAD_API + "/files"):
            file_id = base.removeprefix(UPLOAD_API + "/files").strip("/") or None
            session = self._new_id("upload")
            self.uploads[session] = {"file_id": file_id, "metadata": json.loads(body)}
            return 200, {"Location": f"https://fake-upload/{session}"}, b""
        if base == API + "/files" and method == "GET":
            return 200, {}, json.dumps({"files": [self._meta(i) for i in self._query(query["q"][0])]}).encode()
        if base == API + "/files" and method == "POST":
            meta = json.loads(body)
            file_id = self._new_id()
            self.files[file_id] = {"name": meta["name"], "mimeType": meta.get("mimeType"), "parents": meta.get("parents", []),
                                   "appProperties": {}, "content": b"", "version": 1, "trashed": False}
            return 200, {}, json.dumps({"id": file_id}).encode()
        file_id = base.removeprefix(API + "/files/")
        if file_id not in self.files or self.files[file_id]["trashed"]:
            return 404, {}, json.dumps({"error": {"message": "File not found"}}).encode()
        f = self.files[file_id]
        if method == "GET" and query.get("alt") == ["media"]:
            return 200, {}, f["content"]
        if method == "GET":
            return 200, {}, json.dumps(self._meta(file_id)).encode()
        if method == "PATCH":
            for k, v in json.loads(body).get("appProperties", {}).items():
                if v is None:
                    f["appProperties"].pop(k, None)
                else:
                    f["appProperties"][k] = v
            f["version"] += 1
            return 200, {}, json.dumps({"id": file_id}).encode()
        return 400, {}, b"{}"

    def _token_endpoint(self, form):
        grant = form["grant_type"][0]
        if grant == "authorization_code":
            if form["code"][0] != "good-code" or not form.get("code_verifier"):
                return 400, {}, json.dumps({"error": "invalid_grant"}).encode()
            return 200, {}, json.dumps({"access_token": self._token(), "refresh_token": "refresh-1",
                                        "expires_in": 3600, "id_token": _id_token(EMAIL)}).encode()
        if grant == "refresh_token" and form["refresh_token"][0] == "refresh-1":
            return 200, {}, json.dumps({"access_token": self._token(), "expires_in": 3600}).encode()
        return 400, {}, json.dumps({"error": "invalid_grant", "error_description": "Token has been revoked"}).encode()

    def _query(self, q):
        if "application/vnd.google-apps.folder" in q:
            name = q.split("name = '")[1].split("'")[0]
            return [i for i, f in self.files.items() if f["name"] == name and f["mimeType"] and "folder" in f["mimeType"] and not f["trashed"]]
        if "appProperties has" in q:
            return [i for i, f in self.files.items() if f["appProperties"].get("screenwriter") == "1" and not f["trashed"]]
        return []

    def _finish_upload(self, session, content):
        up = self.uploads.pop(session)
        meta = up["metadata"]
        file_id = up["file_id"]
        if file_id is None:
            file_id = self._new_id()
            self.files[file_id] = {"name": meta["name"], "mimeType": meta.get("mimeType"), "parents": meta.get("parents", []),
                                   "appProperties": {}, "content": b"", "version": 0, "trashed": False}
        f = self.files[file_id]
        f["name"] = meta.get("name", f["name"])
        f["appProperties"].update(meta.get("appProperties", {}))
        f["content"] = content
        f["version"] += 1
        return 200, {}, json.dumps(self._meta(file_id)).encode()

    def _meta(self, file_id):
        f = self.files[file_id]
        return {"id": file_id, "name": f["name"], "modifiedTime": "2026-09-26T12:00:00Z",
                "version": str(f["version"]), "appProperties": dict(f["appProperties"])}
