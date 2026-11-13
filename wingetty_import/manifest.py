"""Parsing of the YAML manifests produced by ``winget download``.

``winget download --id <id> -d <dir>`` writes the installer file plus a
generated YAML manifest next to it. The generated manifest keeps the
original vendor URL in ``InstallerUrl``; WinGetty ignores that URL on import
and serves the uploaded file itself, so the URL is only used here to find
the matching installer file on disk.

The parser is intentionally tolerant: it accepts the merged (singleton)
manifests that ``winget download`` emits as well as community-repository
style multi-document manifests (separate version / defaultLocale /
installer documents).
"""

import os
import urllib.parse
from dataclasses import dataclass, field

import yaml

MANIFEST_EXTENSIONS = (".yaml", ".yml")


class ManifestError(Exception):
    """Raised when a YAML file cannot be understood as a winget manifest."""


@dataclass
class ManifestInstaller:
    architecture: str
    installer_type: str
    sha256: str
    url: str = ""
    scope: str = "machine"
    switches: dict = field(default_factory=dict)
    dependencies: dict = field(default_factory=dict)
    nested_installer_type: str = ""
    nested_installer_files: list = field(default_factory=list)

    @property
    def filename(self):
        """Best-effort installer file name derived from the vendor URL."""
        if not self.url:
            return ""
        path = urllib.parse.urlparse(self.url).path
        return os.path.basename(urllib.parse.unquote(path))


@dataclass
class ImportPackage:
    identifier: str = ""
    version: str = ""
    name: str = ""
    publisher: str = ""
    locale: str = "en-US"
    short_description: str = ""
    installers: list = field(default_factory=list)

    def validate(self):
        if not self.identifier:
            raise ManifestError("manifest has no PackageIdentifier")
        if not self.version:
            raise ManifestError(
                f"manifest for {self.identifier} has no PackageVersion"
            )
        if not self.installers:
            raise ManifestError(
                f"manifest for {self.identifier} {self.version} has no Installers"
            )
        for installer in self.installers:
            if not installer.architecture:
                raise ManifestError(
                    f"{self.identifier} {self.version}: installer without Architecture"
                )
            if not installer.installer_type:
                raise ManifestError(
                    f"{self.identifier} {self.version}: installer without InstallerType"
                )
            if not installer.sha256:
                raise ManifestError(
                    f"{self.identifier} {self.version}: installer without InstallerSha256"
                )


def _apply_locale(pkg: ImportPackage, locale_doc: dict):
    if locale_doc.get("PackageLocale"):
        pkg.locale = str(locale_doc["PackageLocale"])
    if locale_doc.get("Publisher"):
        pkg.publisher = str(locale_doc["Publisher"])
    if locale_doc.get("PackageName"):
        pkg.name = str(locale_doc["PackageName"])
    if locale_doc.get("ShortDescription"):
        pkg.short_description = str(locale_doc["ShortDescription"])


def _parse_installer(data: dict) -> ManifestInstaller:
    switches = data.get("InstallerSwitches") or {}
    switches = {str(k): str(v) for k, v in switches.items() if v is not None}

    nested_files = []
    for nested in data.get("NestedInstallerFiles") or []:
        if isinstance(nested, dict) and nested.get("RelativeFilePath"):
            nested_files.append(
                {
                    "relative_file_path": str(nested["RelativeFilePath"]),
                    "portable_command_alias": str(
                        nested.get("PortableCommandAlias") or ""
                    ),
                }
            )

    scope = str(data.get("Scope") or "machine").lower()
    if scope not in ("user", "machine"):
        # winget manifests only know user/machine; anything else maps to
        # machine-wide, which is the common case for managed fleets.
        scope = "machine"

    dependencies = data.get("Dependencies")
    if dependencies is not None:
        from wingetty_import.dependencies_schema import (
            DependenciesError,
            validate_dependencies,
        )

        try:
            dependencies = validate_dependencies(dependencies)
        except DependenciesError as e:
            raise ManifestError(f"invalid Dependencies: {e}")

    return ManifestInstaller(
        architecture=str(data.get("Architecture") or "").lower(),
        installer_type=str(data.get("InstallerType") or "").lower(),
        sha256=str(data.get("InstallerSha256") or "").lower(),
        url=str(data.get("InstallerUrl") or ""),
        scope=scope,
        switches=switches,
        dependencies=dependencies or {},
        nested_installer_type=str(data.get("NestedInstallerType") or "").lower(),
        nested_installer_files=nested_files,
    )


def parse_manifest_documents(docs) -> ImportPackage:
    """Merge one or more YAML documents into a single ImportPackage."""
    pkg = ImportPackage()
    saw_manifest = False
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        manifest_type = str(doc.get("ManifestType") or "").lower()
        if manifest_type:
            saw_manifest = True

        if doc.get("PackageIdentifier"):
            pkg.identifier = str(doc["PackageIdentifier"])
            saw_manifest = True
        if doc.get("PackageVersion"):
            pkg.version = str(doc["PackageVersion"])

        if manifest_type == "defaultlocale":
            _apply_locale(pkg, doc)
        elif isinstance(doc.get("DefaultLocale"), dict):
            _apply_locale(pkg, doc["DefaultLocale"])
        elif manifest_type in ("merged", "singleton"):
            # Merged manifests may also carry the locale fields inline.
            _apply_locale(pkg, doc)

        for installer_doc in doc.get("Installers") or []:
            if isinstance(installer_doc, dict):
                pkg.installers.append(_parse_installer(installer_doc))

    if not saw_manifest:
        raise ManifestError("not a winget manifest")
    if not pkg.name:
        pkg.name = pkg.identifier
    if not pkg.publisher:
        pkg.publisher = pkg.identifier.split(".")[0] if pkg.identifier else ""
    pkg.validate()
    return pkg


def parse_manifest_file(path) -> ImportPackage:
    """Parse a single YAML file (any number of documents)."""
    try:
        with open(path, encoding="utf-8-sig") as handle:
            docs = list(yaml.safe_load_all(handle))
    except yaml.YAMLError as e:
        raise ManifestError(f"invalid YAML in {path}: {e}")
    return parse_manifest_documents(docs)
