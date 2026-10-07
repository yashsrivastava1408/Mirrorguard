"""Fixtures every test can use."""

import shutil

import pytest

from mirrorguard.benchmark.repository import BenchmarkRepository
from mirrorguard.db import Database
from mirrorguard.library.loader import DATA_DIR, load_library


@pytest.fixture(scope="session")
def library():
    return load_library()


@pytest.fixture
def data_copy(tmp_path):
    """A private copy of the real test material that a test can break on purpose."""
    target = tmp_path / "data"
    shutil.copytree(DATA_DIR, target)
    return target


@pytest.fixture
async def database(tmp_path):
    """An empty database in a temporary file."""
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await db.create_tables()
    yield db
    await db.dispose()


@pytest.fixture
async def repository(database):
    return BenchmarkRepository(database)
