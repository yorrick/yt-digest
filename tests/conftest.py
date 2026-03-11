# tests/conftest.py
import pytest
from yt_digest.db import Database


@pytest.fixture
def db(tmp_path):
    """In-memory-like DB using a temp file for tests."""
    db_path = tmp_path / "test.db"
    database = Database(str(db_path))
    database.init()
    return database
