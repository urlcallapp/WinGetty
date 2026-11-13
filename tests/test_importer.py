import hashlib
import os

import pytest

from wingetty_import.importer import run_import, scan_drop_dir, sha256_file


def _make_drop(tmp_path, identifier="Contoso.App", version="1.2.3",
               arch="x64", scope="machine", content=b"fake-installer-bytes"):
    """Create a winget-download style drop: installer + merged YAML."""
    file_name = f"{identifier}-{version}-{arch}.exe"
    installer_path = tmp_path / file_name
    installer_path.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    manifest = f"""
PackageIdentifier: {identifier}
PackageVersion: {version}
DefaultLocale:
  PackageLocale: en-US
  Publisher: Contoso Ltd
  PackageName: Contoso App
  ShortDescription: Contoso demo application
Installers:
- Architecture: {arch}
  InstallerType: exe
  InstallerUrl: https://vendor.example.com/downloads/{file_name}
  InstallerSha256: {digest}
  Scope: {scope}
ManifestType: merged
ManifestVersion: 1.5.0
"""
    (tmp_path / f"{identifier}.{arch}.yaml").write_text(manifest)
    return file_name, digest


class FakeBackend:
    """In-memory Backend used to test import logic without a server."""

    def __init__(self):
        self.packages = {}

    def get_package(self, identifier):
        return self.packages.get(identifier)

    def create_package(self, pkg):
        self.packages[pkg.identifier] = {
            "identifier": pkg.identifier,
            "name": pkg.name,
            "publisher": pkg.publisher,
            "versions": [],
        }

    def create_version(self, pkg):
        self.packages[pkg.identifier]["versions"].append(
            {"version_code": pkg.version, "installers": []}
        )

    def create_installer(self, pkg, installer, file_path):
        for version in self.packages[pkg.identifier]["versions"]:
            if version["version_code"] == pkg.version:
                version["installers"].append(
                    {
                        "architecture": installer.architecture,
                        "scope": installer.scope,
                        "file": file_path,
                    }
                )


def test_scan_groups_multi_yaml_drop(tmp_path):
    # Same package/version split across two YAML files (one per installer).
    _make_drop(tmp_path, arch="x64")
    _make_drop(tmp_path, arch="x86")

    items, errors = scan_drop_dir(str(tmp_path))
    assert errors == []
    assert len(items) == 1
    pkg, file_map = items[0]
    assert pkg.identifier == "Contoso.App"
    assert len(pkg.installers) == 2
    assert all(path is not None for path in file_map.values())


def test_import_adds_and_skips_on_second_run(tmp_path):
    _make_drop(tmp_path)
    backend = FakeBackend()

    first = run_import(str(tmp_path), backend)
    assert first["summary"] == {"added": 1, "skipped": 0, "errors": 0}
    assert first["items"][0]["status"] == "added"

    second = run_import(str(tmp_path), backend)
    assert second["summary"] == {"added": 0, "skipped": 1, "errors": 0}
    assert second["items"][0]["detail"] == "already present"


def test_import_reports_hash_mismatch(tmp_path):
    file_name, _ = _make_drop(tmp_path)
    # Corrupt the installer after the manifest was written.
    (tmp_path / file_name).write_bytes(b"tampered")

    backend = FakeBackend()
    report = run_import(str(tmp_path), backend)
    assert report["summary"]["errors"] == 1
    assert "hash mismatch" in report["items"][0]["detail"]
    assert backend.packages == {}


def test_import_reports_missing_file(tmp_path):
    file_name, _ = _make_drop(tmp_path)
    os.remove(tmp_path / file_name)

    backend = FakeBackend()
    report = run_import(str(tmp_path), backend)
    assert report["summary"]["errors"] == 1
    assert "no local installer file" in report["items"][0]["detail"]


def test_dry_run_changes_nothing(tmp_path):
    _make_drop(tmp_path)
    backend = FakeBackend()
    report = run_import(str(tmp_path), backend, dry_run=True)
    assert report["summary"]["added"] == 1
    assert backend.packages == {}


def test_hash_matching_fallback_without_url_name(tmp_path):
    # Installer file renamed locally: the importer must still find it by hash.
    file_name, digest = _make_drop(tmp_path)
    os.rename(tmp_path / file_name, tmp_path / "renamed-installer.exe")

    backend = FakeBackend()
    report = run_import(str(tmp_path), backend)
    assert report["summary"]["errors"] == 0
    assert report["summary"]["added"] == 1


def test_local_backend_persists_each_switch_once(app, tmp_path):
    """The local backend writes exactly one InstallerSwitch row per switch
    (the API route had a duplicate-append regression; pin both paths)."""
    from app.models import Installer
    from wingetty_import.importer import LocalBackend

    file_name, _ = _make_drop(tmp_path)
    # Add a switch to the manifest
    manifest = tmp_path / "Contoso.App.x64.yaml"
    manifest.write_text(
        manifest.read_text().replace(
            "  Scope: machine",
            "  Scope: machine\n  InstallerSwitches:\n    Silent: /qn",
        )
    )

    backend = LocalBackend()
    try:
        report = run_import(str(tmp_path), backend)
    finally:
        backend.close()
    assert report["summary"]["added"] == 1, report

    with app.app_context():
        installer = Installer.query.one()
        assert len(installer.switches) == 1
        assert installer.switches[0].parameter == "Silent"
        assert installer.switches[0].value == "/qn"


def test_local_backend_refuses_s3_mode(app):
    """Under USE_S3 the importer's local-disk files would be unservable, so
    the backend must fail explicitly instead of importing."""
    from app import db
    from app.models import Setting
    from wingetty_import.importer import LocalBackend

    with app.app_context():
        setting = Setting.get("USE_S3")
        setting.value = "True"
        db.session.commit()

    with pytest.raises(RuntimeError, match="USE_S3"):
        LocalBackend()


def test_sha256_file(tmp_path):
    path = tmp_path / "x.bin"
    path.write_bytes(b"abc")
    assert sha256_file(str(path)) == hashlib.sha256(b"abc").hexdigest()
