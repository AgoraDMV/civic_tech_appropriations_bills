"""Tests for scripts/fetch_test_assets.py."""

from __future__ import annotations

import urllib.request

from scripts.fetch_test_assets import ASSETS, fetch_asset


def test_assets_registry_well_formed():
    assert ASSETS, "registry should not be empty"
    for dest_rel, url in ASSETS:
        assert dest_rel.startswith("test_data/"), dest_rel
        assert url.startswith("https://www.govinfo.gov/"), url


def test_watermark_pdf_registered():
    dests = [dest for dest, _ in ASSETS]
    assert "test_data/BILLS-118s4795rs.pdf" in dests


def test_skips_existing(tmp_path, monkeypatch):
    dest = tmp_path / "test_data" / "x.pdf"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"already")
    monkeypatch.setattr("scripts.fetch_test_assets._ROOT", tmp_path)

    def boom(*args, **kwargs):
        raise AssertionError("should not download when the file already exists")

    monkeypatch.setattr(urllib.request, "urlopen", boom)

    wrote = fetch_asset("test_data/x.pdf", "https://www.govinfo.gov/whatever.pdf")
    assert wrote is False
    assert dest.read_bytes() == b"already"


def test_writes_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.fetch_test_assets._ROOT", tmp_path)

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b"%PDF-fake"

    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: FakeResp())

    wrote = fetch_asset("test_data/new.pdf", "https://www.govinfo.gov/new.pdf")
    assert wrote is True
    assert (tmp_path / "test_data" / "new.pdf").read_bytes() == b"%PDF-fake"
