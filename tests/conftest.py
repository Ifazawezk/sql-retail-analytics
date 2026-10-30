import sqlite3

import pytest

import seed


@pytest.fixture(scope="session")
def db_path(tmp_path_factory):
    """Build the sample database once per test session in a temp folder."""
    path = tmp_path_factory.mktemp("data") / "retail.db"
    seed.build_database(path)
    return path


@pytest.fixture
def conn(db_path):
    connection = sqlite3.connect(db_path)
    yield connection
    connection.close()
