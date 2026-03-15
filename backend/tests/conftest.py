from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Dict, Generator

import pytest
from fastapi.testclient import TestClient

_TEMP_ROOT = Path(tempfile.mkdtemp(prefix="reviewpro-tests-"))
os.environ["REVIEWPRO_DATABASE_URL"] = "sqlite:///{}".format((_TEMP_ROOT / "reviewpro_test.db").as_posix())
os.environ["REVIEWPRO_STORAGE_DIR"] = str(_TEMP_ROOT / "storage")
os.environ["REVIEWPRO_LLM_API_KEY"] = ""

from app.config import get_settings

get_settings.cache_clear()


@pytest.fixture(scope="session")
def test_environment() -> Generator[Dict[str, str], None, None]:
    yield {"root": str(_TEMP_ROOT)}
    get_settings.cache_clear()
    os.environ.pop("REVIEWPRO_DATABASE_URL", None)
    os.environ.pop("REVIEWPRO_STORAGE_DIR", None)
    os.environ.pop("REVIEWPRO_LLM_API_KEY", None)


@pytest.fixture()
def client(test_environment: Dict[str, str]) -> Generator[TestClient, None, None]:
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
