import pytest

from witness.config import settings


@pytest.fixture(autouse=True)
def temp_cache_dir(tmp_path, monkeypatch):
    # live runs save to the cache: tests must never write into backend/data/cached
    monkeypatch.setattr(settings, "CACHE_DIR", str(tmp_path / "cached"))
