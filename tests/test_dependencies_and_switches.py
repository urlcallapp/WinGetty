"""Schema-valid roundtrip of installer switches and Dependencies:

manifest YAML -> importer parse -> API intake -> stored -> emitted winget
manifest. Plus artifact-store fetch/extract safety tests.
"""

import hashlib
import io
import json
import os
import tarfile
import zipfile

import pytest

from wingetty_import.artifact import (
    ArtifactError,
    redact_url,
    safe_extract,
)
from wingetty_import.dependencies_schema import (
    DependenciesError,
    validate_dependencies,
)
from wingetty_import.manifest import parse_manifest_documents

from app.models import Installer

from test_api import EXE_BYTES, _add_package, _add_version, _add_installer

DEPS = {
    "PackageDependencies": [
        {"PackageIdentifier": "Microsoft.VCRedist.2015+.x64",
         "MinimumVersion": "14.0.0"}
    ],
    "ExternalDependencies": ["usb-driver"],
}

MULTIARCH_MANIFEST = f"""\
PackageIdentifier: Vendor.Tool
PackageVersion: 2.0
PackageName: Tool
Publisher: Vendor
Installers:
- Architecture: x64
  InstallerType: exe
  InstallerUrl: https://vendor.example/tool-x64.exe
  InstallerSha256: {hashlib.sha256(EXE_BYTES).hexdigest()}
  Scope: machine
  InstallerSwitches:
    Silent: /quiet
    Custom: /norestart
  Dependencies:
    PackageDependencies:
    - PackageIdentifier: Microsoft.VCRedist.2015+.x64
      MinimumVersion: "14.0.0"
    ExternalDependencies:
    - usb-driver
- Architecture: arm64
  InstallerType: exe
  InstallerUrl: https://vendor.example/tool-arm64.exe
  InstallerSha256: {hashlib.sha256(b"arm64 bytes").hexdigest()}
  Scope: user
ManifestType: merged
ManifestVersion: "1.6"
"""


def test_validate_dependencies_accepts_valid():
    assert validate_dependencies(json.loads(json.dumps(DEPS))) == DEPS


@pytest.mark.parametrize("bad", [
    [],
    {"Unknown": []},
    {"PackageDependencies": []},
    {"PackageDependencies": [{"MinimumVersion": "1.0"}]},
    {"PackageDependencies": [{"PackageIdentifier": "  "}]},
    {"PackageDependencies": [{"PackageIdentifier": "X", "Extra": 1}]},
    {"ExternalDependencies": [""]},
    {"ExternalDependencies": "not-a-list"},
])
def test_validate_dependencies_rejects_invalid(bad):
    with pytest.raises(DependenciesError):
        validate_dependencies(bad)


def test_manifest_parser_multiarch_switches_dependencies():
    docs = list(__import__("yaml").safe_load_all(MULTIARCH_MANIFEST))
    pkg = parse_manifest_documents(docs)
    assert pkg.identifier == "Vendor.Tool"
    assert len(pkg.installers) == 2
    by_arch = {i.architecture: i for i in pkg.installers}
    x64 = by_arch["x64"]
    assert x64.scope == "machine"
    assert x64.switches == {"Silent": "/quiet", "Custom": "/norestart"}
    assert x64.dependencies == DEPS
    arm = by_arch["arm64"]
    assert arm.scope == "user"
    assert arm.dependencies == {}


def test_manifest_parser_rejects_bad_dependencies():
    docs = list(__import__("yaml").safe_load_all(
        MULTIARCH_MANIFEST.replace("- usb-driver", "- 42")
    ))
    from wingetty_import.manifest import ManifestError
    with pytest.raises(ManifestError):
        parse_manifest_documents(docs)


def _add_installer_full(client, identifier, version):
    return client.post(
        f"/api/package/{identifier}/add_installer",
        data={
            "installer-version": version,
            "installer-architecture": "x64",
            "installer-installer_type": "exe",
            "installer-installer_scope": "machine",
            "installer-file": (io.BytesIO(EXE_BYTES), "app.exe"),
            "Silent": "/quiet",
            "Custom": "/norestart",
            "dependencies": json.dumps(DEPS),
        },
        content_type="multipart/form-data",
    )


def test_add_installer_persists_switches_and_dependencies(admin_client, app):
    _add_package(admin_client)
    _add_version(admin_client, "Test.App", "1.0")
    resp = _add_installer_full(admin_client, "Test.App", "1.0")
    assert resp.status_code == 302

    with app.app_context():
        installer = Installer.query.one()
        switches = {s.parameter: s.value for s in installer.switches}
        assert switches["Silent"] == "/quiet"
        assert switches["Custom"] == "/norestart"
        assert installer.dependencies == DEPS

    # Roundtrip: the emitted winget manifest carries both back to clients.
    resp = admin_client.get("/wg/packageManifests/Test.App")
    entry = resp.get_json()["Data"]["Versions"][0]["Installers"][0]
    assert entry["InstallerSwitches"]["Silent"] == "/quiet"
    assert entry["InstallerSwitches"]["Custom"] == "/norestart"
    assert entry["Dependencies"] == DEPS


def test_add_installer_rejects_invalid_dependencies(admin_client):
    _add_package(admin_client)
    _add_version(admin_client, "Test.App", "1.0")
    resp = admin_client.post(
        "/api/package/Test.App/add_installer",
        data={
            "installer-version": "1.0",
            "installer-architecture": "x64",
            "installer-installer_type": "exe",
            "installer-installer_scope": "machine",
            "installer-file": (io.BytesIO(EXE_BYTES), "app.exe"),
            "dependencies": json.dumps({"Bogus": [1]}),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    assert "invalid dependencies" in resp.get_json()["error"]


def test_redact_url_strips_credentials():
    assert redact_url("https://user:secret@nexus.internal/a.zip") == \
        "https://nexus.internal/a.zip"
    assert redact_url("https://nexus.internal/a.zip") == \
        "https://nexus.internal/a.zip"


def test_safe_extract_rejects_traversal(tmp_path):
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../../etc/pwned", "x")
    with pytest.raises(ArtifactError):
        safe_extract(str(archive), str(tmp_path / "out"))


def test_safe_extract_rejects_tar_symlink(tmp_path):
    payload = tmp_path / "f.txt"
    payload.write_text("x")
    archive = tmp_path / "evil.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        tf.add(payload, arcname="f.txt")
        info = tarfile.TarInfo("link")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        tf.addfile(info)
    with pytest.raises(ArtifactError):
        safe_extract(str(archive), str(tmp_path / "out"))


def test_safe_extract_rejects_unknown_type(tmp_path):
    archive = tmp_path / "a.rar"
    archive.write_bytes(b"nope")
    with pytest.raises(ArtifactError):
        safe_extract(str(archive), str(tmp_path / "out"))


def test_safe_extract_happy_path_zip(tmp_path):
    archive = tmp_path / "drop.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("Vendor.Tool/app.exe", EXE_BYTES)
        zf.writestr("Vendor.Tool/manifest.yaml", MULTIARCH_MANIFEST)
    out = tmp_path / "out"
    os.makedirs(out)
    count = safe_extract(str(archive), str(out))
    assert count == 2
    assert (out / "Vendor.Tool" / "app.exe").read_bytes() == EXE_BYTES


# --- fetch_artifact: corruption, caps, HTTP auth ---------------------------

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from wingetty_import.artifact import fetch_artifact


def _serve(directory, expected_auth=None):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if expected_auth is not None:
                if self.headers.get("Authorization") != expected_auth:
                    self.send_response(401)
                    self.end_headers()
                    return
            path = self.path.lstrip("/") or "index"
            target = os.path.join(directory, path)
            if not os.path.isfile(target):
                self.send_response(404)
                self.end_headers()
                return
            data = open(target, "rb").read()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_fetch_artifact_over_http_with_auth(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "drop.zip").write_bytes(b"PK\x03\x04 fake")
    server = _serve(str(src), expected_auth="Basic dXNlcjpzZWNyZXQ=")
    try:
        dest = tmp_path / "out.zip"
        written = fetch_artifact(
            f"http://user:secret@127.0.0.1:{server.server_port}/drop.zip",
            str(dest),
        )
        assert written == len(b"PK\x03\x04 fake")
        assert dest.read_bytes() == b"PK\x03\x04 fake"
    finally:
        server.shutdown()


def test_fetch_artifact_wrong_auth_raises_without_credentials(tmp_path):
    server = _serve(str(tmp_path), expected_auth="Basic dXNlcjpzZWNyZXQ=")
    try:
        with pytest.raises(ArtifactError) as exc:
            fetch_artifact(
                f"http://user:wrongpass@127.0.0.1:{server.server_port}/drop.zip",
                str(tmp_path / "out.zip"),
            )
        assert "wrongpass" not in str(exc.value)
        assert "secret" not in str(exc.value)
    finally:
        server.shutdown()


def test_fetch_artifact_enforces_size_cap(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "big.zip").write_bytes(b"x" * 2048)
    server = _serve(str(src))
    try:
        with pytest.raises(ArtifactError):
            fetch_artifact(
                f"http://127.0.0.1:{server.server_port}/big.zip",
                str(tmp_path / "out.zip"),
                max_bytes=1024,
            )
    finally:
        server.shutdown()


def test_safe_extract_rejects_corrupt_zip(tmp_path):
    archive = tmp_path / "corrupt.zip"
    archive.write_bytes(b"PK\x03\x04" + b"\x00" * 100)
    with pytest.raises((ArtifactError, zipfile.BadZipFile)):
        safe_extract(str(archive), str(tmp_path / "out"))


def test_safe_extract_rejects_corrupt_tgz(tmp_path):
    archive = tmp_path / "corrupt.tar.gz"
    archive.write_bytes(b"\x1f\x8b" + b"\x00" * 100)
    with pytest.raises((ArtifactError, tarfile.TarError, EOFError, OSError)):
        safe_extract(str(archive), str(tmp_path / "out"))
