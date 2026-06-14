"""Tests for graceful PDF-toolchain handling (issue #6).

These verify the behaviour when weasyprint or its native libraries cannot be
loaded, without requiring the libraries to actually be absent on the test host:
the import is intercepted to simulate each failure mode.
"""

import builtins

import pytest

from vibepaper.build import (
    PdfToolchainError,
    build_pdf,
    pdf_available,
    pdf_toolchain_error,
)


@pytest.fixture
def break_weasyprint(monkeypatch):
    """Make ``import weasyprint`` raise the given exception."""

    def _install(exc):
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "weasyprint" or name.startswith("weasyprint."):
                raise exc
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)

    return _install


def test_probe_reports_missing_package(break_weasyprint):
    break_weasyprint(ImportError("No module named 'weasyprint'"))
    reason = pdf_toolchain_error()
    assert reason is not None
    assert "weasyprint" in reason
    assert pdf_available() is False


def test_probe_reports_missing_native_libraries(break_weasyprint):
    break_weasyprint(OSError("cannot load library 'libpango-1.0-0'"))
    reason = pdf_toolchain_error()
    assert reason is not None
    assert "libpango" in reason
    assert pdf_available() is False


def test_build_pdf_raises_actionable_error_when_package_missing(break_weasyprint, tmp_path):
    break_weasyprint(ImportError("No module named 'weasyprint'"))
    with pytest.raises(PdfToolchainError) as exc:
        build_pdf(["intro.md"], tmp_path / "out.pdf", tmp_path)
    msg = str(exc.value)
    assert "pip install weasyprint" in msg
    assert "pango" in msg  # install hint for the native libraries


def test_build_pdf_raises_actionable_error_when_libraries_missing(break_weasyprint, tmp_path):
    break_weasyprint(OSError("cannot load library 'libpango-1.0-0'"))
    with pytest.raises(PdfToolchainError) as exc:
        build_pdf(["intro.md"], tmp_path / "out.pdf", tmp_path)
    msg = str(exc.value)
    assert "cannot load its system libraries" in msg
    assert "libpango" in msg
