"""Bulk log import tests — JSONL/CSV upload, background processing, polling.

The import router reads/writes ImportTask rows via the module-level
``async_session``. Tests swap that factory for an in-memory SQLite session so
the whole flow runs against a real database.
"""

import asyncio
import io
import json

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.jwt import create_access_token
from app.db.models import Base
from app.main import app
from app.routers import logs as logs_router

TOKEN = create_access_token("import_tester", tenant_id="default")
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


@pytest_asyncio.fixture
async def sqlite_session(monkeypatch):
    """Point the logs router at an in-memory SQLite DB."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(logs_router, "async_session", factory)
    yield factory
    await engine.dispose()


def _post_import(client, content: bytes, filename: str):
    return client.post(
        "/api/v1/logs/import",
        files={"file": (filename, io.BytesIO(content), "application/octet-stream")},
        headers=HEADERS,
    )


def _wait_completed(client, task_id: str, timeout_s: float = 10.0):
    """Poll the status endpoint until the task leaves pending/processing."""
    import time

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        resp = client.get(f"/api/v1/logs/import/{task_id}", headers=HEADERS)
        body = resp.json()
        if body["status"] in ("completed", "failed"):
            return body
        time.sleep(0.05)
    raise AssertionError(f"task {task_id} did not finish in time")


@pytest.mark.asyncio
async def test_jsonl_import_counts(sqlite_session):
    """Upload a small JSONL with one bad line; counters must reflect it."""
    client = TestClient(app)
    lines = [
        json.dumps({"EventID": 1, "Image": "powershell.exe", "CommandLine": "powershell -enc abc"}),
        json.dumps({"EventID": 2, "Image": "mimikatz.exe", "CommandLine": "mimikatz sekurlsa::"}),
        "{not valid json",  # -> failed
        json.dumps({"EventID": 3, "Image": "cmd.exe", "CommandLine": "dir"}),
    ]
    payload = "\n".join(lines).encode()

    resp = _post_import(client, payload, "events.jsonl")
    assert resp.status_code == 202, resp.text
    task_id = resp.json()["task_id"]
    assert resp.json()["status"] == "pending"

    final = _wait_completed(client, task_id)
    assert final["status"] == "completed"
    assert final["total"] == 4
    assert final["failed"] == 1          # the malformed line
    assert final["processed"] == 3       # 3 valid dicts analyzed


@pytest.mark.asyncio
async def test_csv_import_counts(sqlite_session):
    """Upload a CSV; all well-formed rows processed, none failed."""
    client = TestClient(app)
    csv_text = (
        "EventID,Image,CommandLine\n"
        "1,powershell.exe,powershell -enc abc\n"
        "2,cmd.exe,dir\n"
    )
    resp = _post_import(client, csv_text.encode(), "events.csv")
    assert resp.status_code == 202, resp.text
    task_id = resp.json()["task_id"]

    final = _wait_completed(client, task_id)
    assert final["status"] == "completed"
    assert final["total"] == 2
    assert final["failed"] == 0
    assert final["processed"] == 2


@pytest.mark.asyncio
async def test_unknown_task_returns_404(sqlite_session):
    client = TestClient(app)
    resp = client.get("/api/v1/logs/import/doesnotexist", headers=HEADERS)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_import_requires_auth(sqlite_session):
    client = TestClient(app)
    resp = client.post(
        "/api/v1/logs/import",
        files={"file": ("x.jsonl", io.BytesIO(b"{}"), "application/octet-stream")},
    )
    assert resp.status_code == 401


class TestFormatDetection:
    def test_by_extension(self):
        assert logs_router._detect_format("a.csv", "") == "csv"
        assert logs_router._detect_format("a.jsonl", "") == "jsonl"
        assert logs_router._detect_format("a.ndjson", "") == "jsonl"

    def test_by_content_sniff(self):
        assert logs_router._detect_format("noext", '{"a":1}') == "jsonl"
        assert logs_router._detect_format("noext", "a,b,c") == "csv"


class TestRowParsing:
    def test_jsonl_mixed(self):
        rows, failures = logs_router._parse_rows(
            '{"a":1}\nnot json\n[1,2]\n{"b":2}\n', "jsonl"
        )
        assert rows == [{"a": 1}, {"b": 2}]
        assert failures == 2  # bad json + non-dict

    def test_csv_basic(self):
        rows, failures = logs_router._parse_rows("x,y\n1,2\n3,4\n", "csv")
        assert rows == [{"x": "1", "y": "2"}, {"x": "3", "y": "4"}]
        assert failures == 0
