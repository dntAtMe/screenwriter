import subprocess
import sys
from pathlib import Path

import screenwriter

ROOT = Path(__file__).parent.parent


def release(*args):
    return subprocess.run([sys.executable, "packaging/release.py", *args], cwd=ROOT, capture_output=True, text=True)


def test_versions_agree_and_changelog_has_notes():
    version = screenwriter.__version__
    assert release("version").stdout.strip() == version
    assert release("check", f"v{version}").returncode == 0
    assert release("notes", version).stdout.strip()


def test_mismatched_tag_is_rejected():
    result = release("check", "v999.0.0")
    assert result.returncode != 0
