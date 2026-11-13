from flask import (
    Blueprint,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user
from sqlalchemy import or_

from app.models import Package, PackageVersion, Setting, version_sort_key

catalog = Blueprint("catalog", __name__)


def _setting(key, default=None):
    setting = Setting.get(key)
    return setting.get_value() if setting is not None else default


def _catalog_enabled():
    return bool(_setting("catalog_enabled", True))


def _login_required_for_catalog():
    return bool(_setting("catalog_require_login", False))


@catalog.get("/")
def index():
    if not _catalog_enabled():
        abort(404)
    if _login_required_for_catalog() and not current_user.is_authenticated:
        return redirect(url_for("auth.login"))
    return render_template(
        "catalog.j2",
        repo_name=_setting("repo_name", "WinGetty"),
        source_name=_setting("catalog_source_name", "WinGetty"),
        protocol_enabled=_setting("catalog_protocol_enabled", True),
        protocol_scheme="wingetty",
    )


@catalog.get("/packages")
def packages():
    if not _catalog_enabled():
        abort(404)
    if _login_required_for_catalog() and not current_user.is_authenticated:
        return jsonify({"error": "authentication required"}), 401

    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("limit", 24, type=int), 100)
    search_query = request.args.get("search", "", type=str).strip()

    query = Package.query.filter(
        Package.versions.any(PackageVersion.installers.any())
    )
    if search_query:
        like = f"%{search_query}%"
        query = query.filter(
            or_(
                Package.name.ilike(like),
                Package.identifier.ilike(like),
                Package.publisher.ilike(like),
            )
        )

    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    items = []
    for package in paginated.items:
        versions = [v for v in package.versions if v.installers]
        versions.sort(key=lambda v: version_sort_key(v.version_code), reverse=True)
        latest = versions[0]
        items.append(
            {
                "identifier": package.identifier,
                "name": package.name,
                "publisher": package.publisher,
                "description": latest.short_description or package.name,
                "latest_version": latest.version_code,
                "versions": [v.version_code for v in versions],
                "download_count": package.download_count,
            }
        )

    return jsonify(
        {
            "packages": items,
            "total": paginated.total,
            "pages": paginated.pages,
            "current_page": paginated.page,
        }
    )
