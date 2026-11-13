# Added 2026-11-13 (urlcallapp/WinGetty fork): AGPL-3.0 source offer routes.
"""Prominent source-code offer, served by the running instance itself.

WinGetty is licensed AGPL-3.0. Operators who modify the software and let
users interact with it over a network must offer those users the
corresponding source. A link to a public git host is not enough for
air-gapped deployments (users cannot reach the internet), so this blueprint
lets the running server hand out the source archive directly:

* ``GET /source`` renders the offer page (license, copyright, dated
  modification notices, download links).
* ``GET /source/archive`` streams the corresponding-source tarball when the
  operator packaged one (the Dockerfile does this automatically; see
  ``scripts/build-source-archive.sh`` for manual/VM deployments).

The page is public on purpose: the offer must reach every user interacting
with the service, including users of the public catalog who have no login.
"""

import os

from flask import Blueprint, current_app, abort, render_template, send_file

source = Blueprint("source", __name__)

DEFAULT_REPOSITORY_URL = "https://github.com/urlcallapp/WinGetty"
DEFAULT_UPSTREAM_URL = "https://github.com/thilojaeggi/WinGetty"


def _archive_path():
    configured = current_app.config.get("SOURCE_ARCHIVE_PATH")
    if configured:
        return configured
    repo_root = os.path.abspath(os.path.join(current_app.root_path, os.pardir))
    return os.path.join(repo_root, "source-archive", "wingetty-source.tar.gz")


def _repository_url():
    return current_app.config.get("SOURCE_REPOSITORY_URL", DEFAULT_REPOSITORY_URL)


def _upstream_url():
    return current_app.config.get("UPSTREAM_REPOSITORY_URL", DEFAULT_UPSTREAM_URL)


@source.get("/")
def index():
    archive = _archive_path()
    return render_template(
        "source.j2",
        archive_available=os.path.isfile(archive),
        repository_url=_repository_url(),
        upstream_url=_upstream_url(),
    )


@source.get("/archive")
def archive():
    archive = _archive_path()
    if not os.path.isfile(archive):
        abort(404)
    return send_file(
        archive,
        as_attachment=True,
        download_name="wingetty-source.tar.gz",
        mimetype="application/gzip",
    )
