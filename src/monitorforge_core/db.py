"""Shared SQLAlchemy handle.

A consuming Flask app calls ``db.init_app(app)`` against its own app
instance. Models register themselves against this same ``db`` on import.
"""

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
