"""SDK tests against the real FastAPI app via httpx.ASGITransport.

No mocks: requests go through the full HTTP/ASGI stack (middleware,
routers, DB on a temp SQLite file) exactly as they would over the wire.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Test environment must be set BEFORE importing the app (env is read at
# import time by app.db.session, app.auth.jwt, etc.).
_tmp_root = Path(tempfile.mkdtemp(prefix="sentinel-sdk-tests-"))
_db_file = _tmp_root / "test.db"
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_db_file}")
os.environ.setdefault("JWT_SECRET", "sdk-test-secret")
os.environ.setdefault("LLM_API_KEY", "dummy")  # no real LLM calls in tests
# Copy rules into a scratch dir so lifecycle tests never touch the repo tree.
_rules_dir = _tmp_root / "rules"
if not _rules_dir.exists():
    shutil.copytree(REPO_ROOT / "rules", _rules_dir)
os.environ.setdefault("RULES_DIR", str(_rules_dir))
os.environ.setdefault("RATE_LIMIT", "100000")  # per-test rate limiting tested separately

for p in (str(REPO_ROOT / "sentinel-api"), str(REPO_ROOT / "sentinel-agents")):
    if p not in sys.path:
        sys.path.insert(0, p)

import httpx  # noqa: E402

from app.db.session import init_db  # noqa: E402
from app.main import app  # noqa: E402

from sentinel_sdk import SentinelClient  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
async def _init_db():
    await init_db()
    yield


@pytest.fixture
async def client():
    """Unauthenticated SDK client wired to the in-process ASGI app."""
    async with SentinelClient(
        "http://testserver",
        transport=httpx.ASGITransport(app=app),
        retries=1,  # determinism: tests that care about retry set their own
    ) as c:
        yield c


@pytest.fixture
async def admin_client(client):
    """Authenticated SDK client (login over the wire, admin role)."""
    await client.login("admin", "admin")
    return client
