import io

from app import db
from app.models import Package, Setting


def _seed(admin_client):
    admin_client.post(
        "/api/add_package",
        data={
            "name": "Catalog App",
            "publisher": "CatalogPublisher",
            "identifier": "Catalog.App",
        },
    )
    admin_client.post(
        "/api/package/Catalog.App/add_version",
        data={"installer-version": "2.1"},
    )
    admin_client.post(
        "/api/package/Catalog.App/add_installer",
        data={
            "installer-version": "2.1",
            "installer-architecture": "x64",
            "installer-installer_type": "exe",
            "installer-installer_scope": "machine",
            "installer-file": (io.BytesIO(b"MZ catalog"), "app.exe"),
        },
        content_type="multipart/form-data",
    )


def test_catalog_open_without_login(app, admin_client):
    _seed(admin_client)
    anonymous = app.test_client()
    resp = anonymous.get("/catalog/")
    assert resp.status_code == 200
    assert b"winget source add" in resp.data
    assert b"catalogData" in resp.data


def test_catalog_packages_json(client, admin_client):
    _seed(admin_client)
    resp = client.get("/catalog/packages")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 1
    package = data["packages"][0]
    assert package["identifier"] == "Catalog.App"
    assert package["latest_version"] == "2.1"
    assert package["versions"] == ["2.1"]


def test_catalog_search_filters(client, admin_client):
    _seed(admin_client)
    resp = client.get("/catalog/packages?search=nomatch")
    assert resp.get_json()["total"] == 0
    resp = client.get("/catalog/packages?search=catalog")
    assert resp.get_json()["total"] == 1


def test_catalog_excludes_packages_without_installers(client, admin_client):
    _seed(admin_client)
    admin_client.post(
        "/api/add_package",
        data={"name": "Empty", "publisher": "Empty", "identifier": "Empty.App"},
    )
    resp = client.get("/catalog/packages")
    assert resp.get_json()["total"] == 1


def test_catalog_disabled_returns_404(client, admin_client, app):
    _seed(admin_client)
    with app.app_context():
        setting = Setting.get("catalog_enabled")
        setting.set_value(False)
        db.session.commit()

    assert client.get("/catalog/").status_code == 404
    assert client.get("/catalog/packages").status_code == 404


def test_catalog_require_login(admin_client, app):
    _seed(admin_client)
    with app.app_context():
        setting = Setting.get("catalog_require_login")
        setting.set_value(True)
        db.session.commit()

    anonymous = app.test_client()  # admin_client is logged in on the shared client
    resp = anonymous.get("/catalog/")
    assert resp.status_code == 302  # redirected to login
    assert anonymous.get("/catalog/packages").status_code == 401
    assert admin_client.get("/catalog/").status_code == 200


def test_catalog_protocol_link_rendered(client, admin_client):
    _seed(admin_client)
    resp = client.get("/catalog/")
    assert b"wingetty" in resp.data  # scheme passed to the page
    assert b"protocolUrl" in resp.data
