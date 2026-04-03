"""Tests for the fetch-csl subcommand."""

import sys
from argparse import Namespace
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from vibepaper.cli import _run_fetch_csl

FAKE_CSL = b'<?xml version="1.0"?><style>vancouver</style>'


def fake_urlopen_ok(url):
    """Simulate a successful HTTP response."""
    cm = MagicMock()
    cm.__enter__ = lambda s: MagicMock(read=lambda: FAKE_CSL)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


def fake_urlopen_404(url):
    import urllib.error
    raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)


def _make_args(style, output=None):
    return Namespace(style=style, output=output)


# --- happy path ---

def test_downloads_to_default_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch("urllib.request.urlopen", fake_urlopen_ok):
        _run_fetch_csl(_make_args("vancouver"))
    assert (tmp_path / "paper" / "vancouver.csl").read_bytes() == FAKE_CSL

def test_downloads_to_custom_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "styles" / "my.csl"
    with patch("urllib.request.urlopen", fake_urlopen_ok):
        _run_fetch_csl(_make_args("vancouver", output=str(out)))
    assert out.read_bytes() == FAKE_CSL

def test_creates_output_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch("urllib.request.urlopen", fake_urlopen_ok):
        _run_fetch_csl(_make_args("vancouver"))
    assert (tmp_path / "paper").is_dir()

def test_fetches_correct_url(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    captured = {}

    def capture_url(url):
        captured["url"] = url
        return fake_urlopen_ok(url)

    with patch("urllib.request.urlopen", capture_url):
        _run_fetch_csl(_make_args("nature"))

    assert captured["url"] == "https://www.zotero.org/styles/nature"


# --- error handling ---

def test_404_exits_with_error(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    with patch("urllib.request.urlopen", fake_urlopen_404):
        with pytest.raises(SystemExit) as exc:
            _run_fetch_csl(_make_args("nonexistent-style-xyz"))
    assert exc.value.code != 0
    err = capsys.readouterr().err
    assert "nonexistent-style-xyz" in err
    assert "zotero.org" in err
