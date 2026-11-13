import io
import os
import shutil
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

_TMPDIR = os.path.join(REPO_ROOT, ".pytest-tmp")
os.makedirs(_TMPDIR, exist_ok=True)

os.environ["WINGETTY_SQLALCHEMY_DATABASE_URI"] = (
    "sqlite:///" + os.path.join(_TMPDIR, "test.db").replace(os.sep, "/")
)
os.environ["WINGETTY_SECRET_KEY"] = "test-secret-key"

import flask  # noqa: E402

from app import create_app, db  # noqa: E402
from app.models import Role, User  # noqa: E402

# dynaconf's settings object does not survive repeated create_app() calls in
# one process (production runs exactly one app per process, tests do not).
# Snapshot the config keys while dynaconf is healthy and overlay them on
# every app config.
from config import settings as _dyna_settings  # noqa: E402

_CONFIG_SNAPSHOT = {
    key: getattr(_dyna_settings, key)
    for key in dir(_dyna_settings)
    if key.isupper()
}
_CONFIG_SNAPSHOT["SQLALCHEMY_DATABASE_URI"] = os.environ[
    "WINGETTY_SQLALCHEMY_DATABASE_URI"
]
_CONFIG_SNAPSHOT["SECRET_KEY"] = "test-secret-key"

_original_from_object = flask.Config.from_object


def _from_object_with_test_config(self, obj):
    _original_from_object(self, obj)
    for key, value in _CONFIG_SNAPSHOT.items():
        self[key] = value


flask.Config.from_object = _from_object_with_test_config

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin-password-123"  # noqa: S105 - test credential


def _precreate_schema():
    """Create the database schema before create_app touches the tables.

    create_app seeds roles/settings at startup, which requires the tables
    to exist already (normally handled by `flask db upgrade` in start.sh).
    """
    from flask import Flask

    pre = Flask("schema-precreate")
    pre.config["SQLALCHEMY_DATABASE_URI"] = os.environ[
        "WINGETTY_SQLALCHEMY_DATABASE_URI"
    ]
    pre.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(pre)
    import app.models  # noqa: F401 - register models on the metadata

    with pre.app_context():
        db.create_all()


@pytest.fixture()
def app():
    db_file = os.path.join(_TMPDIR, "test.db")
    if os.path.exists(db_file):
        os.remove(db_file)
    _precreate_schema()
    application = create_app()
    with application.app_context():
        admin_role = Role.query.filter_by(name="admin").first()
        admin = User(username="admin", email=ADMIN_EMAIL, role=admin_role)
        admin.set_password(ADMIN_PASSWORD)
        db.session.add(admin)
        db.session.commit()

    yield application

    # Drop installers written into the repo's packages/ dir by tests.
    packages_dir = os.path.join(REPO_ROOT, "app", "packages")
    if os.path.exists(packages_dir):
        shutil.rmtree(packages_dir)


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def admin_client(client):
    resp = client.post(
        "/login",
        data={"emailorusername": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 302)
    return client
