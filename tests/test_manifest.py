import textwrap

import pytest

from wingetty_import.manifest import (
    ManifestError,
    parse_manifest_file,
)

MERGED_MANIFEST = textwrap.dedent(
    """
    PackageIdentifier: Contoso.App
    PackageVersion: 1.2.3
    DefaultLocale:
      PackageLocale: en-US
      Publisher: Contoso Ltd
      PackageName: Contoso App
      ShortDescription: Contoso demo application
    Installers:
    - Architecture: x64
      InstallerType: exe
      InstallerUrl: https://vendor.example.com/downloads/ContosoApp-1.2.3-x64.exe
      InstallerSha256: AAAA1111
      Scope: machine
      InstallerSwitches:
        Silent: /S
        Custom: /quiet
    - Architecture: x86
      InstallerType: msi
      InstallerUrl: https://vendor.example.com/downloads/ContosoApp-1.2.3-x86.msi
      InstallerSha256: BBBB2222
    ManifestType: merged
    ManifestVersion: 1.5.0
    """
)

COMMUNITY_MANIFEST = textwrap.dedent(
    """
    PackageIdentifier: Example.Tool
    PackageVersion: 2.0
    ManifestType: version
    ManifestVersion: 1.5.0
    ---
    PackageIdentifier: Example.Tool
    PackageVersion: 2.0
    PackageLocale: en-US
    Publisher: Example
    PackageName: Example Tool
    ShortDescription: Example tool
    ManifestType: defaultLocale
    ManifestVersion: 1.5.0
    ---
    PackageIdentifier: Example.Tool
    PackageVersion: 2.0
    Installers:
    - Architecture: arm64
      InstallerType: zip
      InstallerUrl: https://example.com/tool-2.0-arm64.zip
      InstallerSha256: CCCC3333
      NestedInstallerType: portable
      NestedInstallerFiles:
      - RelativeFilePath: tool.exe
        PortableCommandAlias: tool
    ManifestType: installer
    ManifestVersion: 1.5.0
    """
)


def test_parse_merged_manifest(tmp_path):
    path = tmp_path / "Contoso.App.yaml"
    path.write_text(MERGED_MANIFEST)
    pkg = parse_manifest_file(str(path))

    assert pkg.identifier == "Contoso.App"
    assert pkg.version == "1.2.3"
    assert pkg.name == "Contoso App"
    assert pkg.publisher == "Contoso Ltd"
    assert pkg.short_description == "Contoso demo application"
    assert len(pkg.installers) == 2

    x64 = pkg.installers[0]
    assert x64.architecture == "x64"
    assert x64.installer_type == "exe"
    assert x64.scope == "machine"
    assert x64.sha256 == "aaaa1111"  # normalized for comparison
    assert x64.filename == "ContosoApp-1.2.3-x64.exe"
    assert x64.switches == {"Silent": "/S", "Custom": "/quiet"}

    x86 = pkg.installers[1]
    assert x86.scope == "machine"  # default when Scope is omitted


def test_parse_community_multidoc(tmp_path):
    path = tmp_path / "Example.Tool.yaml"
    path.write_text(COMMUNITY_MANIFEST)
    pkg = parse_manifest_file(str(path))

    assert pkg.identifier == "Example.Tool"
    assert pkg.version == "2.0"
    assert pkg.name == "Example Tool"
    assert pkg.publisher == "Example"
    assert len(pkg.installers) == 1

    installer = pkg.installers[0]
    assert installer.architecture == "arm64"
    assert installer.nested_installer_type == "portable"
    assert installer.nested_installer_files == [
        {"relative_file_path": "tool.exe", "portable_command_alias": "tool"}
    ]


def test_rejects_non_manifest(tmp_path):
    path = tmp_path / "random.yaml"
    path.write_text("just: some yaml\n")
    with pytest.raises(ManifestError):
        parse_manifest_file(str(path))


def test_rejects_manifest_without_identifier(tmp_path):
    path = tmp_path / "broken.yaml"
    path.write_text("PackageVersion: 1.0\nInstallers: []\nManifestType: merged\n")
    with pytest.raises(ManifestError):
        parse_manifest_file(str(path))
