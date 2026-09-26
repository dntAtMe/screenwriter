"""Release helpers used by the GitHub workflow (and handy locally).

    python packaging/release.py version            → 0.1.0
    python packaging/release.py check v0.1.0       → fails unless the tag matches the code
    python packaging/release.py notes 0.1.0        → that version's CHANGELOG section
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def code_version() -> str:
    return re.search(r'__version__ = "([^"]+)"', (ROOT / "screenwriter" / "__init__.py").read_text()).group(1)


def project_version() -> str:
    return re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.MULTILINE).group(1)


def notes(version: str) -> str:
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    m = re.search(rf"^## \[?{re.escape(version)}\]?.*?\n(.*?)(?=^## |\Z)", changelog, re.MULTILINE | re.DOTALL)
    if not m:
        sys.exit(f"CHANGELOG.md has no section for {version}")
    return m.group(1).strip() + "\n"


def main(argv: list[str]) -> None:
    command, *args = argv or ["version"]
    if command == "version":
        print(code_version())
    elif command == "check":
        tag = args[0]
        version = tag.removeprefix("refs/tags/").removeprefix("v")
        problems = []
        if version != code_version():
            problems.append(f"tag {tag} ≠ screenwriter/__init__.py {code_version()}")
        if version != project_version():
            problems.append(f"tag {tag} ≠ pyproject.toml {project_version()}")
        notes(version)  # exits if the changelog section is missing
        if problems:
            sys.exit("Version mismatch: " + "; ".join(problems))
        print(f"{tag} matches version {version}")
    elif command == "notes":
        print(notes(args[0].removeprefix("v")), end="")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
