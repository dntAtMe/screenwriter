"""Check for a new version: ask GitHub for the latest release, and say so when there's a newer one.

Automatic at most once a day (Help → Check for Updates Automatically, on by default), or any time
with Help → Check for Updates…. Only the public release list is fetched; nothing about you or your
projects is sent. The answer comes on a background thread, so a slow network never holds up the app.
"""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.request
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal

from . import REPOSITORY, __version__, net

LATEST_URL = "https://api.github.com/repos/" + REPOSITORY.split("github.com/", 1)[1] + "/releases/latest"
DAY = 24 * 60 * 60


@dataclass
class Release:
    version: str  # "1.1.0"
    url: str  # the release page, where the downloads are
    notes: str  # what's new (Markdown, from the changelog)


def parse_version(text: str) -> tuple[int, ...]:
    """"v1.10.2" → (1, 10, 2); anything after the numbers ("-beta") is ignored."""
    m = re.match(r"v?(\d+(?:\.\d+)*)", text.strip())
    return tuple(int(n) for n in m.group(1).split(".")) if m else ()


def is_newer(candidate: str, current: str = __version__) -> bool:
    a, b = parse_version(candidate), parse_version(current)
    width = max(len(a), len(b))
    return bool(a) and a + (0,) * (width - len(a)) > b + (0,) * (width - len(b))


def parse_release(data: dict) -> Release | None:
    """The latest release from GitHub's answer; None for drafts, pre-releases or nonsense."""
    tag = data.get("tag_name") or ""
    if data.get("draft") or data.get("prerelease") or not parse_version(tag):
        return None
    return Release(tag.lstrip("v"), data.get("html_url") or "", (data.get("body") or "").strip())


def due(last_check: float, now: float | None = None) -> bool:
    """Whether an automatic check is due: never checked, or not within the last day."""
    return (now if now is not None else time.time()) - last_check >= DAY


def fetch_latest(timeout: float = 15) -> Release | None:
    request = urllib.request.Request(LATEST_URL, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"Screenwriter/{__version__}",
    })
    with net.urlopen(request, timeout=timeout) as response:
        return parse_release(json.loads(response.read().decode("utf-8")))


class Checker(QObject):
    """Runs fetch_latest on a thread; `finished` carries the Release (or None) and an error message."""

    finished = Signal(object, str)

    def __init__(self, parent=None, fetch=fetch_latest):
        super().__init__(parent)
        self.fetch = fetch
        self.busy = False

    def start(self) -> None:
        if self.busy:
            return
        self.busy = True

        def run() -> None:
            try:
                release, error = self.fetch(), ""
            except Exception as e:  # offline, GitHub down, rate-limited…
                release, error = None, str(e) or type(e).__name__
            self.finished.emit(release, error)  # delivered on the main thread

        threading.Thread(target=run, daemon=True, name="version-check").start()
