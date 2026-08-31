import sqlite3

import pytest

from skibot import db


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    db.apply_migrations(c)
    yield c
    c.close()
