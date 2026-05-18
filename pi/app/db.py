import sqlite3
import os
from flask import current_app, g


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(
            current_app.config['DATABASE'],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys = ON')
    return g.db


def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_app(app):
    app.teardown_appcontext(close_db)
    schema = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'schema.sql')
    with app.app_context():
        db = get_db()
        with open(schema) as f:
            db.executescript(f.read())
        db.commit()
