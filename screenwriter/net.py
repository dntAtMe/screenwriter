"""HTTPS for the app's own requests (Google Drive, the new-version check).

A packaged app can't count on finding the system's certificate authorities — macOS and some
Linux systems keep them where a bundled Python doesn't look — so requests check certificates
against Mozilla's list from certifi, which ships with the app.
"""

from __future__ import annotations

import ssl
import urllib.request
from functools import lru_cache


@lru_cache(maxsize=1)
def ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except (ImportError, OSError):  # (running from source without it: the system's list)
        return ssl.create_default_context()


def urlopen(request, timeout: float):
    return urllib.request.urlopen(request, timeout=timeout, context=ssl_context())
