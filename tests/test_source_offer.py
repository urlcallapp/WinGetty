"""Tests for the AGPL source-offer routes (app/source_routes.py)."""

import os
import tarfile

from app.source_routes import DEFAULT_REPOSITORY_URL, DEFAULT_UPSTREAM_URL


def test_source_page_lists_license_and_links(client):
    resp = client.get("/source/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "AGPL-3.0" in body
    assert "Thilo Jaeggi" in body  # original copyright preserved
    assert DEFAULT_REPOSITORY_URL in body
    assert DEFAULT_UPSTREAM_URL in body
    assert "2026-11-13" in body  # dated modification notice


def test_source_page_is_public(client):
    # The offer must reach users without a login (public catalog users).
    resp = client.get("/source/", follow_redirects=False)
    assert resp.status_code == 200


def test_footer_links_source_offer(client):
    resp = client.get("/source/")
    assert 'href="/source/"' in resp.get_data(as_text=True)


def test_archive_404_when_missing(client):
    resp = client.get("/source/archive")
    assert resp.status_code == 404


def test_archive_served_when_present(client, app, tmp_path):
    archive = tmp_path / "wingetty-source.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        payload = tmp_path / "SOURCE_VERSION"
        payload.write_text("source_revision=test\n")
        tar.add(payload, arcname="SOURCE_VERSION")

    app.config["SOURCE_ARCHIVE_PATH"] = str(archive)
    try:
        resp = client.get("/source/archive")
        assert resp.status_code == 200
        assert resp.headers["Content-Type"] == "application/gzip"
        out = tmp_path / "downloaded.tar.gz"
        out.write_bytes(resp.data)
        with tarfile.open(out, "r:gz") as tar:
            assert "SOURCE_VERSION" in tar.getnames()

        page = client.get("/source/").get_data(as_text=True)
        assert "Download source archive" in page
        assert os.path.getsize(archive) > 0
    finally:
        app.config.pop("SOURCE_ARCHIVE_PATH", None)
