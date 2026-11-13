# Modification notices (AGPL-3.0 section 5(a))

WinGetty is licensed under the GNU Affero General Public License v3.0
(see LICENSE.md). Original work copyright Thilo Jaeggi and contributors;
all original copyright and license notices are preserved unchanged.

This repository (urlcallapp/WinGetty) contains modifications to the
upstream project thilojaeggi/WinGetty.

## 2026-11-13 - urlcallapp fork

New components added:

- `wingetty_import/` - automated importer for `winget download` output:
  parses merged and community multi-document YAML manifests, uploads
  installers with sha256 verification, idempotent re-runs, JSON report,
  CLI with `--local`, `--server`, `--watch`, `--dry-run`, `--report`.
- `app/catalog_routes.py`, `app/templates/catalog.j2` - public end-user
  app catalog at `/catalog` with search, version modal, copy-command and
  install buttons; admin toggles `catalog_enabled`,
  `catalog_require_login`, `catalog_source_name`,
  `catalog_protocol_enabled` in `app/settings.py`.
- `client/` - Windows PowerShell helpers that register a safe
  `wingetty://` URL protocol (validated package identifier, pinned source,
  user confirmation, fixed winget arguments; no arbitrary command passing).
- `app/source_routes.py`, `app/templates/source.j2` - prominent AGPL
  source offer served by the running instance, including an air-gap-ready
  downloadable corresponding-source archive.
- `scripts/build-source-archive.sh` - builds the corresponding-source
  tarball served at `/source/archive` (run automatically by the Dockerfile).
- `tests/`, `.github/workflows/tests.yml`, `requirements-dev.txt` - test
  suite and CI.
- `docs/` - GitHub Pages landing page with video and static catalog demo.

Upstream files modified (each carries a dated header notice):

- `app/models.py` - packaging-based version parsing (LooseVersion removed,
  Python 3.12 compatibility), `date_added` default fixed.
- `app/api_routes.py` - installer lookup scoped to the owning package
  version (wrong-package attachment fixed), `file or external_url and
  version` precedence fixed, 409 on duplicate add, InstallerError handling,
  debug print removed.
- `app/forms.py` - empty select choices no longer block package/version
  creation without installers.
- `app/utils.py` - InstallerError propagation, nested empty-string handling.
- `app/winget_routes.py` - partial/case-insensitive manifest search,
  correct 204 response bodies.
- `app/permissions.py` - role_id None handling.
- `app/__init__.py` - catalog and source blueprint registration.
- `app/settings.py` - catalog settings added.
- `app/templates/nav.j2` - catalog navigation link.
- `app/templates/footer.j2` - source-offer link.
- `Dockerfile` - copies `wingetty_import/`, builds source archive.
- `README.md` - documentation for the new components.
