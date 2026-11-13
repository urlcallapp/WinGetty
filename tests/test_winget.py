import hashlib
import io

EXE_BYTES = b"MZ winget search test"


def _seed(admin_client, identifier="Search.App", name="Searchable App"):
    admin_client.post(
        "/api/add_package",
        data={"name": name, "publisher": "SearchPublisher", "identifier": identifier},
    )
    admin_client.post(
        f"/api/package/{identifier}/add_version",
        data={"installer-version": "1.0"},
    )
    admin_client.post(
        f"/api/package/{identifier}/add_installer",
        data={
            "installer-version": "1.0",
            "installer-architecture": "x64",
            "installer-installer_type": "exe",
            "installer-installer_scope": "machine",
            "installer-file": (io.BytesIO(EXE_BYTES), "app.exe"),
        },
        content_type="multipart/form-data",
    )


def test_manifest_search_exact(admin_client):
    _seed(admin_client)
    resp = admin_client.post(
        "/wg/manifestSearch",
        json={
            "Query": {"KeyWord": "Search.App", "MatchType": "Exact"},
            "MaximumResults": 10,
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()["Data"]
    assert data[0]["PackageIdentifier"] == "Search.App"


def test_manifest_search_case_insensitive_partial(admin_client):
    """`winget search searchable` sends a CaseInsensitive/Substring query -
    it must match by name, not only by exact identifier."""
    _seed(admin_client)
    resp = admin_client.post(
        "/wg/manifestSearch",
        json={
            "Query": {"KeyWord": "searchable", "MatchType": "CaseInsensitive"},
            "MaximumResults": 10,
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()["Data"]
    assert data[0]["PackageIdentifier"] == "Search.App"


def test_manifest_search_no_match_returns_204(admin_client):
    resp = admin_client.post(
        "/wg/manifestSearch",
        json={
            "Query": {"KeyWord": "nothing-matches-this", "MatchType": "Exact"},
            "MaximumResults": 10,
        },
    )
    assert resp.status_code == 204


def test_information_endpoint(client):
    resp = client.get("/wg/information")
    assert resp.status_code == 200
    assert "SourceIdentifier" in resp.get_json()["Data"]


def test_package_manifest_unknown_returns_204(client):
    assert client.get("/wg/packageManifests/Nope.Nope").status_code == 204
