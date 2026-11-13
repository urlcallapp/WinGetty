"""Core import logic shared by the local and API backends.

The import is idempotent: installers that already exist for the same
package / version / architecture / scope are skipped, so the same drop
folder (or an artifact store synced into one) can be re-imported on a
schedule without creating duplicates. Every run produces a structured
report of what was added, skipped and what failed.
"""

import hashlib
import json
import os
import shutil

from .manifest import (
    MANIFEST_EXTENSIONS,
    ImportPackage,
    ManifestError,
    parse_manifest_documents,
    parse_manifest_file,
)

# Switches WinGetty knows how to store; anything else in the manifest is
# dropped with a note rather than failing the import.
SUPPORTED_SWITCHES = (
    "Silent",
    "SilentWithProgress",
    "Interactive",
    "InstallLocation",
    "Log",
    "Upgrade",
    "Custom",
)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scan_drop_dir(drop_dir):
    """Group YAML manifests in drop_dir into (ImportPackage, file map) pairs.

    Every directory is scanned independently: all YAML documents in one
    directory that share a PackageIdentifier + PackageVersion are merged,
    which covers both the one-YAML-per-installer output of ``winget
    download`` and community-style multi-file manifests.
    """
    groups = {}  # (identifier.lower(), version) -> {"pkg": ImportPackage, "dir": str}
    errors = []

    for root, _dirs, files in os.walk(drop_dir):
        docs = []
        manifest_files = [
            f for f in files if f.lower().endswith(MANIFEST_EXTENSIONS)
        ]
        for name in sorted(manifest_files):
            path = os.path.join(root, name)
            try:
                pkg = parse_manifest_file(path)
                docs.append((path, pkg))
            except ManifestError as e:
                errors.append(
                    {"file": path, "status": "error", "detail": str(e)}
                )

        for _path, pkg in docs:
            key = (pkg.identifier.lower(), pkg.version)
            if key in groups:
                existing = groups[key]["pkg"]
                existing.installers.extend(pkg.installers)
                if not existing.name and pkg.name:
                    existing.name = pkg.name
                if not existing.publisher and pkg.publisher:
                    existing.publisher = pkg.publisher
                if not existing.short_description and pkg.short_description:
                    existing.short_description = pkg.short_description
            else:
                groups[key] = {"pkg": pkg, "dir": root}

    items = []
    for group in groups.values():
        pkg = group["pkg"]
        file_map = resolve_installer_files(pkg, group["dir"])
        items.append((pkg, file_map))
    return items, errors


def resolve_installer_files(pkg: ImportPackage, directory):
    """Match every manifest installer to a file on disk.

    Matching is by InstallerUrl file name first; if that file is missing,
    fall back to any non-YAML file in the directory whose SHA256 equals the
    InstallerSha256 from the manifest. The hash is verified either way.
    """
    candidates = [
        f
        for f in os.listdir(directory)
        if os.path.isfile(os.path.join(directory, f))
        and not f.lower().endswith(MANIFEST_EXTENSIONS)
    ]
    resolved = {}
    for index, installer in enumerate(pkg.installers):
        path = None
        if installer.filename and installer.filename in candidates:
            path = os.path.join(directory, installer.filename)
        else:
            for name in candidates:
                candidate = os.path.join(directory, name)
                if sha256_file(candidate) == installer.sha256:
                    path = candidate
                    break
        resolved[index] = path
    return resolved


class LocalBackend:
    """Write directly through the WinGetty models (run on the WinGetty host)."""

    def __init__(self):
        from app import create_app, db  # noqa: F401 - imported lazily

        self.app = create_app()
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.db = db

    def close(self):
        self.app_context.pop()

    def get_package(self, identifier):
        # Note: Package.to_dict() is not used here - it builds external URLs,
        # which fails outside a request context without SERVER_NAME.
        from app.models import Package

        package = Package.query.filter_by(identifier=identifier).first()
        if package is None:
            return None
        return {
            "identifier": package.identifier,
            "versions": [
                {
                    "version_code": version.version_code,
                    "installers": [
                        {"architecture": i.architecture, "scope": i.scope}
                        for i in version.installers
                    ],
                }
                for version in package.versions
            ],
        }

    def create_package(self, pkg: ImportPackage):
        from app.models import Package

        package = Package(
            identifier=pkg.identifier, name=pkg.name, publisher=pkg.publisher
        )
        self.db.session.add(package)
        self.db.session.commit()

    def create_version(self, pkg: ImportPackage):
        from app.models import PackageVersion

        version = PackageVersion(
            identifier=pkg.identifier,
            version_code=pkg.version,
            default_locale=pkg.locale,
            package_locale=pkg.locale,
            short_description=pkg.short_description or pkg.name,
        )
        self.db.session.add(version)
        self.db.session.commit()

    def create_installer(self, pkg: ImportPackage, installer, file_path):
        from app.models import (
            Installer,
            InstallerSwitch,
            NestedInstallerFile,
            PackageVersion,
        )
        from app.utils import basedir

        version = PackageVersion.query.filter_by(
            identifier=pkg.identifier, version_code=pkg.version
        ).first()

        source_name = os.path.basename(file_path)
        extension = (
            source_name.rsplit(".", 1)[1]
            if "." in source_name
            else installer.installer_type
        )
        file_name = f"{installer.scope}.{extension}"

        target_dir = os.path.join(
            basedir,
            "packages",
            pkg.publisher,
            pkg.identifier,
            pkg.version,
            installer.architecture,
        )
        os.makedirs(target_dir, exist_ok=True)
        target_path = os.path.join(target_dir, file_name)
        if os.path.exists(target_path):
            os.remove(target_path)
        shutil.copyfile(file_path, target_path)

        digest = sha256_file(target_path)
        if digest != installer.sha256:
            os.remove(target_path)
            raise ManifestError(
                f"hash mismatch for {source_name}: manifest {installer.sha256}, "
                f"actual {digest}"
            )

        record = Installer(
            version_id=version.id,
            architecture=installer.architecture,
            installer_type=installer.installer_type,
            file_name=file_name,
            external_url=None,
            installer_sha256=digest,
            scope=installer.scope,
        )
        self.db.session.add(record)
        self.db.session.flush()

        for parameter, value in installer.switches.items():
            if parameter in SUPPORTED_SWITCHES:
                self.db.session.add(
                    InstallerSwitch(
                        installer_id=record.id, parameter=parameter, value=value
                    )
                )

        if installer.dependencies:
            record.dependencies = installer.dependencies

        if installer.nested_installer_type:
            record.nested_installer_type = installer.nested_installer_type
            for nested in installer.nested_installer_files:
                self.db.session.add(
                    NestedInstallerFile(
                        installer_id=record.id,
                        relative_file_path=nested["relative_file_path"],
                        portable_command_alias=nested["portable_command_alias"],
                    )
                )

        self.db.session.commit()


class ApiBackend:
    """Drive the WinGetty REST API (run from any machine that can reach it)."""

    def __init__(self, base_url, username, password, verify_tls=True):
        import requests

        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.verify = verify_tls
        self._login(username, password)

    def _login(self, username, password):
        resp = self.session.post(
            f"{self.base_url}/login",
            data={
                "emailorusername": username,
                "password": password,
                "remember": "y",
            },
            allow_redirects=True,
        )
        resp.raise_for_status()
        whoami = self.session.get(f"{self.base_url}/api/whoami")
        if whoami.status_code != 200:
            raise PermissionError(
                f"Login to {self.base_url} as {username} failed "
                f"(whoami returned {whoami.status_code})"
            )

    def get_package(self, identifier):
        resp = self.session.get(f"{self.base_url}/api/package/{identifier}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def create_package(self, pkg: ImportPackage):
        resp = self.session.post(
            f"{self.base_url}/api/add_package",
            data={
                "name": pkg.name,
                "publisher": pkg.publisher,
                "identifier": pkg.identifier,
            },
        )
        if resp.status_code == 409:
            return  # created concurrently; treat as existing
        resp.raise_for_status()

    def create_version(self, pkg: ImportPackage):
        resp = self.session.post(
            f"{self.base_url}/api/package/{pkg.identifier}/add_version",
            data={"installer-version": pkg.version},
        )
        if resp.status_code == 409:
            return
        resp.raise_for_status()

    def create_installer(self, pkg: ImportPackage, installer, file_path):
        data = {
            "installer-version": pkg.version,
            "installer-architecture": installer.architecture,
            "installer-installer_type": installer.installer_type,
            "installer-installer_scope": installer.scope,
        }
        for parameter, value in installer.switches.items():
            if parameter in SUPPORTED_SWITCHES:
                data[parameter] = value
        if installer.dependencies:
            data["dependencies"] = json.dumps(installer.dependencies)
        if installer.nested_installer_type:
            data["installer-nestedinstallertype"] = installer.nested_installer_type
            if installer.nested_installer_files:
                data["installer-nestedinstallerpath"] = installer.nested_installer_files[
                    0
                ]["relative_file_path"]

        with open(file_path, "rb") as handle:
            resp = self.session.post(
                f"{self.base_url}/api/package/{pkg.identifier}/add_installer",
                data=data,
                files={"installer-file": (os.path.basename(file_path), handle)},
                allow_redirects=False,
            )
        if resp.status_code == 409:
            raise ManifestError(
                "installer already exists (server rejected duplicate)"
            )
        if resp.status_code not in (200, 302):
            raise ManifestError(
                f"server rejected installer: {resp.status_code} {resp.text[:200]}"
            )


def _installer_exists(package_dict, version_code, installer):
    for version in package_dict.get("versions", []):
        if version.get("version_code") != version_code:
            continue
        for existing in version.get("installers", []):
            if (
                existing.get("architecture") == installer.architecture
                and existing.get("scope") == installer.scope
            ):
                return True
    return False


def run_import(drop_dir, backend, dry_run=False, report_path=None):
    """Import everything found under drop_dir. Returns the report dict."""
    report = {
        "drop_dir": os.path.abspath(drop_dir),
        "dry_run": dry_run,
        "summary": {"added": 0, "skipped": 0, "errors": 0},
        "items": [],
    }

    items, scan_errors = scan_drop_dir(drop_dir)
    report["items"].extend(scan_errors)

    for pkg, file_map in items:
        for index, installer in enumerate(pkg.installers):
            label = f"{pkg.identifier} {pkg.version} {installer.architecture}/{installer.scope}"
            entry = {
                "identifier": pkg.identifier,
                "version": pkg.version,
                "architecture": installer.architecture,
                "scope": installer.scope,
            }
            file_path = file_map.get(index)
            if file_path is None:
                entry.update(
                    status="error",
                    detail="no local installer file matched the manifest "
                    "(checked InstallerUrl file name and SHA256)",
                )
                report["items"].append(entry)
                continue

            actual_hash = sha256_file(file_path)
            if actual_hash != installer.sha256:
                entry.update(
                    status="error",
                    detail=f"hash mismatch: manifest {installer.sha256}, actual {actual_hash}",
                )
                report["items"].append(entry)
                continue

            existing = backend.get_package(pkg.identifier)
            if existing and _installer_exists(existing, pkg.version, installer):
                entry.update(status="skipped", detail="already present")
                report["items"].append(entry)
                continue

            if dry_run:
                entry.update(status="added", detail="dry run", file=file_path)
                report["items"].append(entry)
                continue

            try:
                if existing is None:
                    backend.create_package(pkg)
                if existing is None or not any(
                    v.get("version_code") == pkg.version
                    for v in existing.get("versions", [])
                ):
                    backend.create_version(pkg)
                backend.create_installer(pkg, installer, file_path)
            except Exception as e:  # report and continue with the next one
                entry.update(status="error", detail=str(e))
                report["items"].append(entry)
                continue

            entry.update(status="added", file=file_path)
            report["items"].append(entry)

    for item in report["items"]:
        key = {
            "added": "added",
            "skipped": "skipped",
            "error": "errors",
        }[item["status"]]
        report["summary"][key] += 1

    if report_path:
        with open(report_path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)

    return report


def print_summary(report):
    summary = report["summary"]
    print(
        f"Import of {report['drop_dir']}: "
        f"{summary['added']} added, {summary['skipped']} skipped, "
        f"{summary['errors']} errors"
    )
    for item in report["items"]:
        if item["status"] == "error":
            label = (
                f"{item.get('identifier', item.get('file', '?'))} "
                f"{item.get('version', '')}"
            ).strip()
            print(f"  ERROR {label}: {item['detail']}")
