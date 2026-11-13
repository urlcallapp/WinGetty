import hashlib
import io

from app.models import Installer, Package, PackageVersion

EXE_BYTES = b"MZ fake exe content for tests"


def _add_package(client, identifier="Test.App", name="Test App",
                 publisher="TestPublisher"):
    return client.post(
        "/api/add_package",
        data={"name": name, "publisher": publisher, "identifier": identifier},
    )


def _add_version(client, identifier, version):
    return client.post(
        f"/api/package/{identifier}/add_version",
        data={"installer-version": version},
    )


def _add_installer(client, identifier, version, arch="x64", scope="machine",
                   content=EXE_BYTES):
    return client.post(
        f"/api/package/{identifier}/add_installer",
        data={
            "installer-version": version,
            "installer-architecture": arch,
            "installer-installer_type": "exe",
            "installer-installer_scope": scope,
            "installer-file": (io.BytesIO(content), "app.exe"),
        },
        content_type="multipart/form-data",
    )


def test_add_package_requires_login(client):
    resp = _add_package(client)
    assert resp.status_code in (302, 401)


def test_add_package_and_duplicate(admin_client):
    assert _add_package(admin_client).status_code == 200
    resp = _add_package(admin_client)
    assert resp.status_code == 409


def test_add_version_and_duplicate(admin_client):
    _add_package(admin_client)
    assert _add_version(admin_client, "Test.App", "1.0").status_code == 302
    resp = _add_version(admin_client, "Test.App", "1.0")
    assert resp.status_code == 409


def test_add_installer_stores_file_and_hash(admin_client, app):
    _add_package(admin_client)
    _add_version(admin_client, "Test.App", "1.0")
    resp = _add_installer(admin_client, "Test.App", "1.0")
    assert resp.status_code == 302

    with app.app_context():
        installer = Installer.query.first()
        assert installer is not None
        assert installer.installer_sha256 == hashlib.sha256(EXE_BYTES).hexdigest()
        assert installer.file_name == "machine.exe"
        assert installer.architecture == "x64"


def test_add_installer_duplicate_arch_scope_rejected(admin_client):
    _add_package(admin_client)
    _add_version(admin_client, "Test.App", "1.0")
    assert _add_installer(admin_client, "Test.App", "1.0").status_code == 302
    resp = _add_installer(admin_client, "Test.App", "1.0")
    assert resp.status_code == 409


def test_add_installer_scoped_to_own_package(admin_client, app):
    """Regression: version codes repeat across packages; the installer must
    land on the package in the URL, not on whichever package's matching
    version code the database returns first."""
    _add_package(admin_client, identifier="Test.A", name="A")
    _add_package(admin_client, identifier="Test.B", name="B")
    _add_version(admin_client, "Test.A", "1.0")
    _add_version(admin_client, "Test.B", "1.0")

    resp = _add_installer(admin_client, "Test.B", "1.0")
    assert resp.status_code == 302

    with app.app_context():
        version_a = PackageVersion.query.filter_by(
            identifier="Test.A", version_code="1.0"
        ).first()
        version_b = PackageVersion.query.filter_by(
            identifier="Test.B", version_code="1.0"
        ).first()
        assert len(version_a.installers) == 0
        assert len(version_b.installers) == 1


def test_add_installer_without_file_or_url_fails(admin_client):
    _add_package(admin_client)
    _add_version(admin_client, "Test.App", "1.0")
    resp = admin_client.post(
        "/api/package/Test.App/add_installer",
        data={
            "installer-version": "1.0",
            "installer-architecture": "x64",
            "installer-installer_type": "exe",
            "installer-installer_scope": "machine",
        },
    )
    assert resp.status_code in (400, 500)  # validation error, never silent None


def test_manifest_uses_internal_download_url(admin_client, app):
    _add_package(admin_client)
    _add_version(admin_client, "Test.App", "1.0")
    _add_installer(admin_client, "Test.App", "1.0")

    resp = admin_client.get("/wg/packageManifests/Test.App")
    assert resp.status_code == 200
    data = resp.get_json()
    installer = data["Data"]["Versions"][0]["Installers"][0]
    assert installer["InstallerUrl"].startswith("https://")
    assert "/api/download/Test.App/1.0/x64/" in installer["InstallerUrl"]
    assert installer["InstallerSha256"] == hashlib.sha256(EXE_BYTES).hexdigest()


def test_download_serves_stored_file(admin_client):
    _add_package(admin_client)
    _add_version(admin_client, "Test.App", "1.0")
    _add_installer(admin_client, "Test.App", "1.0")

    resp = admin_client.get("/api/download/Test.App/1.0/x64/machine")
    assert resp.status_code == 200
    assert resp.data == EXE_BYTES


def test_package_json_lists_versions(admin_client):
    _add_package(admin_client)
    _add_version(admin_client, "Test.App", "1.0")
    _add_installer(admin_client, "Test.App", "1.0")

    resp = admin_client.get("/api/package/Test.App")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["identifier"] == "Test.App"
    assert data["versions"][0]["version_code"] == "1.0"
    assert data["versions"][0]["installers"][0]["architecture"] == "x64"
