import pytest
from flask import Flask

from monitorforge_core.db import db


@pytest.fixture()
def app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "execution_options": {"schema_translate_map": {"core": None, "meta": None}}
    }
    db.init_app(app)

    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture()
def session(app):
    with app.app_context():
        yield db.session
