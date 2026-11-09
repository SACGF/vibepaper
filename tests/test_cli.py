"""CLI-level behaviour."""

import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib  # type: ignore

ROOT = Path(__file__).resolve().parent.parent


def test_version_flag_matches_pyproject():
    # The version is set by hand in several places; --version must not lie.
    expected = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    out = subprocess.run(
        [sys.executable, "-m", "vibepaper", "--version"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert out.strip() == f"vibepaper {expected}"
