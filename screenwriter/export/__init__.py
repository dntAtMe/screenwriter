"""Export formats, grouped by what is being exported."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class Format:
    label: str
    extension: str
    paper: bool  # offers Letter / A4
    run: Callable[..., None]  # run(path, paper)
