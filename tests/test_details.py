"""Catalog details: sanitize, manifest parsing, importer persistence, API."""

import hashlib
import io
import json

from app import db
from app.models import PackageVersion
from wingetty_import.details_schema import sanitize_version_details
from wingetty_import.manifest import parse_manifest_documents

from tests.test_importer import _make_drop  # noqa: E402 - shared drop helper


# --- sanitize_version_details -------------------------------------------------


def test_sanitize_keeps_allowlisted_fields():
    details = sanitize_version_details(
        {
            "Description": "A long description",
            "Author": "Contoso",
            "License": "MIT",
            "PackageUrl": "https://contoso.example.com/app",
            "Tags": ["tool", "utility"],
            "ReleaseNotes": "Fixed bugs",
        }
    )
    assert details["description"] == "A long description"
    assert details["author"] == "Contoso"
    assert details["license"] == "MIT"
    assert details["homepage"] == "https://contoso.example.com/app"
    assert details["tags"] == ["tool", "utility"]
    assert details["release_notes"] == "Fixed bugs"


def test_sanitize_drops_unknown_keys():
    details = sanitize_version_details(
        {"Description": "ok", "MaliciousField": "payload", "Installers": [1, 2]}
    )
    assert details == {"description": "ok"}


def test_sanitize_rejects_non_http_urls():
    details = sanitize_version_details(
        {
            "PackageUrl": "javascript:alert(1)",
            "PublisherUrl": "file:///C:/Windows/system.ini",
            "LicenseUrl": "ftp://example.com/license",
            "PrivacyUrl": "https://contoso.example.com/privacy",
            "Documentations": [
                {"DocumentLabel": "Docs", "DocumentUrl": "javascript:alert(1)"},
                {"DocumentLabel": "Wiki", "DocumentUrl": "https://example.com/wiki"},
            ],
        }
    )
    assert "homepage" not in details
    assert "publisher_url" not in details
    assert "license_url" not in details
    assert details["privacy_url"] == "https://contoso.example.com/privacy"
    # Documentation without a safe URL keeps its label but gets no url key.
    assert details["documentations"] == [
        {"label": "Docs"},
        {"label": "Wiki", "url": "https://example.com/wiki"},
    ]


def test_sanitize_caps_lengths_and_counts():
    details = sanitize_version_details(
        {
            "Description": "x" * 20000,
            "Tags": [f"tag{i}" for i in range(50)],
        }
    )
    assert len(details["description"]) == 8000
    assert len(details["tags"]) == 16


def test_sanitize_rejects_non_dict():
    assert sanitize_version_details("not a dict") == {}
    assert sanitize_version_details(None) == {}


# --- manifest parsing ---------------------------------------------------------


def _locale_doc(**overrides):
    doc = {
        "PackageIdentifier": "Contoso.App",
        "PackageVersion": "1.2.3",
        "PackageLocale": "en-US",
        "Publisher": "Contoso Ltd",
        "PackageName": "Contoso App",
        "ShortDescription": "short",
        "ManifestType": "defaultLocale",
        "ManifestVersion": "1.5.0",
    }
    doc.update(overrides)
    return doc


def _installer_doc():
    return {
        "PackageIdentifier": "Contoso.App",
        "PackageVersion": "1.2.3",
        "ManifestType": "installer",
        "ManifestVersion": "1.5.0",
        "Installers": [
            {
                "Architecture": "x64",
                "InstallerType": "exe",
                "InstallerUrl": "https://vendor.example.com/app.exe",
                "InstallerSha256": "ab" * 32,
            }
        ],
    }


def test_manifest_collects_locale_and_version_details():
    pkg = parse_manifest_documents(
        [
            {
                "PackageIdentifier": "Contoso.App",
                "PackageVersion": "1.2.3",
                "ManifestType": "version",
                "ManifestVersion": "1.5.0",
                "ReleaseNotes": "multi\nline notes",
                "ReleaseNotesUrl": "https://contoso.example.com/notes",
            },
            _locale_doc(
                Description="Full description",
                Author="Contoso",
                License="MIT",
                PackageUrl="https://contoso.example.com/app",
                Tags=["tool", "demo"],
            ),
            _installer_doc(),
        ]
    )
    assert pkg.details["description"] == "Full description"
    assert pkg.details["author"] == "Contoso"
    assert pkg.details["license"] == "MIT"
    assert pkg.details["homepage"] == "https://contoso.example.com/app"
    assert pkg.details["tags"] == ["tool", "demo"]
    assert pkg.details["release_notes"] == "multi\nline notes"
    assert pkg.details["release_notes_url"] == "https://contoso.example.com/notes"


def test_manifest_without_extra_metadata_has_empty_details():
    pkg = parse_manifest_documents([_locale_doc(), _installer_doc()])
    assert pkg.details == {}


def test_manifest_details_are_sanitized():
    pkg = parse_manifest_documents(
        [
            _locale_doc(PackageUrl="javascript:alert(1)", Description="ok"),
            _installer_doc(),
        ]
    )
    assert "homepage" not in pkg.details
    assert pkg.details["description"] == "ok"


# --- local importer persistence ------------------------------------------------


def test_local_backend_persists_details(app, tmp_path):
    from wingetty_import.importer import LocalBackend, run_import

    file_name, _digest = _make_drop(tmp_path)
    # Extend the drop manifest with locale metadata.
    manifest_path = next(tmp_path.glob("*.yaml"))
    text = manifest_path.read_text()
    text = text.replace(
        "  ShortDescription: Contoso demo application\n",
        "  ShortDescription: Contoso demo application\n"
        "  Description: The full Contoso story\n"
        "  License: MIT\n"
        "  PackageUrl: https://contoso.example.com/app\n"
        "  Tags:\n  - demo\n  - contoso\n",
    )
    manifest_path.write_text(text)

    backend = LocalBackend()
    try:
        report = run_import(str(tmp_path), backend)
    finally:
        backend.close()
    assert report["summary"]["errors"] == 0

    with app.app_context():
        version = PackageVersion.query.filter_by(
            identifier="Contoso.App", version_code="1.2.3"
        ).one()
        assert version.details["description"] == "The full Contoso story"
        assert version.details["license"] == "MIT"
        assert version.details["homepage"] == "https://contoso.example.com/app"
        assert version.details["tags"] == ["demo", "contoso"]


# --- REST API ------------------------------------------------------------------


def test_add_version_accepts_details(admin_client, app):
    admin_client.post(
        "/api/add_package",
        data={
            "name": "Detail App",
            "publisher": "DetailPublisher",
            "identifier": "Detail.App",
        },
    )
    admin_client.post(
        "/api/package/Detail.App/add_version",
        data={
            "installer-version": "3.0",
            "details": json.dumps(
                {
                    "Description": "API supplied description",
                    "License": "Apache-2.0",
                    "PackageUrl": "https://detail.example.com",
                    "EvilUrl": "https://evil.example.com",
                }
            ),
        },
    )
    with app.app_context():
        version = PackageVersion.query.filter_by(
            identifier="Detail.App", version_code="3.0"
        ).one()
        assert version.details["description"] == "API supplied description"
        assert version.details["license"] == "Apache-2.0"
        assert version.details["homepage"] == "https://detail.example.com"
        assert "evilurl" not in {k.lower() for k in version.details}


def test_add_version_rejects_invalid_details_json(admin_client):
    admin_client.post(
        "/api/add_package",
        data={
            "name": "Bad Detail",
            "publisher": "BadPublisher",
            "identifier": "Bad.Detail",
        },
    )
    resp = admin_client.post(
        "/api/package/Bad.Detail/add_version",
        data={"installer-version": "1.0", "details": "{not json"},
    )
    assert resp.status_code == 400


# --- catalog endpoint ------------------------------------------------------------


def _seed_with_details(admin_client):
    admin_client.post(
        "/api/add_package",
        data={
            "name": "Catalog App",
            "publisher": "CatalogPublisher",
            "identifier": "Catalog.App",
        },
    )
    admin_client.post(
        "/api/package/Catalog.App/add_version",
        data={
            "installer-version": "2.1",
            "details": json.dumps(
                {
                    "Description": "Everything about Catalog App",
                    "License": "MIT",
                    "PackageUrl": "https://catalog.example.com",
                    "ReleaseNotes": "2.1 ships details",
                    "Tags": ["catalog"],
                }
            ),
        },
    )
    admin_client.post(
        "/api/package/Catalog.App/add_installer",
        data={
            "installer-version": "2.1",
            "installer-architecture": "x64",
            "installer-installer_type": "exe",
            "installer-installer_scope": "machine",
            "installer-file": (io.BytesIO(b"MZ catalog"), "app.exe"),
        },
        content_type="multipart/form-data",
    )


def test_catalog_packages_include_details(client, admin_client):
    _seed_with_details(admin_client)
    data = client.get("/catalog/packages").get_json()
    package = data["packages"][0]
    assert package["details"]["description"] == "Everything about Catalog App"
    assert package["details"]["license"] == "MIT"
    assert package["details"]["homepage"] == "https://catalog.example.com"
    assert package["details"]["tags"] == ["catalog"]
    assert package["version_details"]["2.1"]["release_notes"] == "2.1 ships details"


def test_catalog_details_resanitize_output(client, admin_client, app):
    """Even if unsafe data reaches the column, the API never emits it."""
    _seed_with_details(admin_client)
    with app.app_context():
        version = PackageVersion.query.filter_by(identifier="Catalog.App").one()
        version.details = {
            "homepage": "javascript:alert(1)",
            "description": "<img src=x onerror=alert(1)>",
            "unknown": "drop me",
        }
        db.session.commit()

    package = client.get("/catalog/packages").get_json()["packages"][0]
    assert "homepage" not in package["details"]
    assert "unknown" not in package["details"]
    # Markup stays plain text (the UI binds with x-text, never HTML).
    assert package["details"]["description"] == "<img src=x onerror=alert(1)>"


def test_catalog_packages_without_details(client, admin_client):
    """Versions imported before details existed still list cleanly."""
    admin_client.post(
        "/api/add_package",
        data={
            "name": "Plain App",
            "publisher": "PlainPublisher",
            "identifier": "Plain.App",
        },
    )
    admin_client.post(
        "/api/package/Plain.App/add_version", data={"installer-version": "1.0"}
    )
    admin_client.post(
        "/api/package/Plain.App/add_installer",
        data={
            "installer-version": "1.0",
            "installer-architecture": "x64",
            "installer-installer_type": "exe",
            "installer-installer_scope": "machine",
            "installer-file": (io.BytesIO(b"MZ plain"), "app.exe"),
        },
        content_type="multipart/form-data",
    )
    package = client.get("/catalog/packages").get_json()["packages"][0]
    assert package["details"] == {}
    assert package["version_details"] == {}


def test_manifest_hash_still_verified_with_details(app, tmp_path):
    """Adding details to a drop must not disturb installer verification."""
    from wingetty_import.importer import LocalBackend, run_import

    content = b"fake-installer-bytes"
    file_name, digest = _make_drop(tmp_path, content=content)
    assert hashlib.sha256(content).hexdigest() == digest
    backend = LocalBackend()
    try:
        report = run_import(str(tmp_path), backend)
    finally:
        backend.close()
    assert report["summary"]["added"] == 1
    assert report["summary"]["errors"] == 0
