import os
import tempfile

import pytest
from fastapi.testclient import TestClient

# Point the SQLite data dir at a throwaway, fast (tmpfs) location before app.config
# is imported. Overlayfs fsync in some sandboxes makes schema setup very slow.
_FALLBACK = tempfile.mkdtemp(prefix="ladderbill-test-")
_TEST_ROOT = "/dev/shm/ladderbill-test" if os.path.isdir("/dev/shm") else _FALLBACK
os.makedirs(_TEST_ROOT, exist_ok=True)
os.environ["DATA_DIR"] = _TEST_ROOT

from app import seed  # noqa: E402
from app.db import DB_PATH, connect  # noqa: E402
from app.main import app  # noqa: E402

PERIOD = "2026-08"


def _reset_db():
    if DB_PATH.exists():
        DB_PATH.unlink()
    seed.init_db()


@pytest.fixture(scope="session")
def client():
    _reset_db()
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _fresh_db():
    _reset_db()
    yield
