# Added 2026-11-13 (urlcallapp/WinGetty fork): winget Dependencies schema validation.
"""Validation of the winget manifest ``Dependencies`` object.

Accepted shape (a subset of the winget 1.x manifest schema):

.. code-block:: yaml

    Dependencies:
      PackageDependencies:
        - PackageIdentifier: Some.Package        # required, non-empty string
          MinimumVersion: 1.2.3                  # optional string
      ExternalDependencies:
        - some-runtime                           # list of non-empty strings

Unknown keys are rejected so malformed input cannot round-trip into the
manifests winget clients consume.
"""

_ALLOWED_TOP_KEYS = {"PackageDependencies", "ExternalDependencies"}
_ALLOWED_DEP_KEYS = {"PackageIdentifier", "MinimumVersion"}


class DependenciesError(ValueError):
    """Raised when a Dependencies object does not match the schema."""


def validate_dependencies(data):
    """Validate *data* against the Dependencies schema.

    Returns the data unchanged when valid (callers store/emit the original
    object). Raises DependenciesError otherwise.
    """
    if not isinstance(data, dict) or not data:
        raise DependenciesError("Dependencies must be a non-empty object")
    unknown = set(data) - _ALLOWED_TOP_KEYS
    if unknown:
        raise DependenciesError(f"Dependencies: unknown keys {sorted(unknown)}")

    package_deps = data.get("PackageDependencies")
    if package_deps is not None:
        if not isinstance(package_deps, list) or not package_deps:
            raise DependenciesError("PackageDependencies must be a non-empty list")
        for entry in package_deps:
            if not isinstance(entry, dict):
                raise DependenciesError("PackageDependencies entries must be objects")
            unknown = set(entry) - _ALLOWED_DEP_KEYS
            if unknown:
                raise DependenciesError(
                    f"PackageDependencies entry: unknown keys {sorted(unknown)}"
                )
            identifier = entry.get("PackageIdentifier")
            if not isinstance(identifier, str) or not identifier.strip():
                raise DependenciesError(
                    "PackageDependencies entries need a non-empty PackageIdentifier"
                )
            minimum = entry.get("MinimumVersion")
            if minimum is not None and not isinstance(minimum, str):
                raise DependenciesError("MinimumVersion must be a string")

    external_deps = data.get("ExternalDependencies")
    if external_deps is not None:
        if not isinstance(external_deps, list) or not external_deps:
            raise DependenciesError("ExternalDependencies must be a non-empty list")
        for entry in external_deps:
            if not isinstance(entry, str) or not entry.strip():
                raise DependenciesError(
                    "ExternalDependencies entries must be non-empty strings"
                )

    return data
