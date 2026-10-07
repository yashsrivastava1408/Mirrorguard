import shutil

import pytest

from mirrorguard.loader import DATA_DIR, load_library


@pytest.fixture(scope="session")
def library():
    return load_library()


@pytest.fixture
def data_copy(tmp_path):
    """A private copy of the real test material that a test can break on purpose."""
    target = tmp_path / "data"
    shutil.copytree(DATA_DIR, target)
    return target
