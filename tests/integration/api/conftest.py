"""Fixtures for tests that call the API."""

import pytest

from tests.support.api import make_harness


@pytest.fixture
async def harness(tmp_path):
    h = await make_harness(tmp_path)
    yield h
    await h.client.aclose()
    await h.services.stop()
