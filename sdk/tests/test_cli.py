"""CLI tests: python -m app.cli driving the real app via an ASGI-injected SDK client.

The CLI builds its own SentinelClient; we wrap the class so every instance
gets an ASGITransport bound to the real FastAPI app. Everything else —
arg parsing, config resolution, output rendering, error paths — is real.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
for p in (str(REPO_ROOT / "sentinel-api"),):
    if p not in sys.path:
        sys.path.insert(0, p)

import app.cli as cli  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from sentinel_sdk import SentinelClient  # noqa: E402


@pytest.fixture
def asgi_client_class(monkeypatch):
    """Patch cli.SentinelClient so instances talk to the in-process app."""

    class ASGISentinelClient(SentinelClient):
        def __init__(self, base_url="http://testserver", **kwargs):
            super().__init__(base_url, transport=httpx.ASGITransport(app=fastapi_app), **kwargs)

    monkeypatch.setattr(cli, "SentinelClient", ASGISentinelClient)
    return ASGISentinelClient


def run_cli(monkeypatch, capsys, argv, env=None, home=None):
    """Invoke cli.main() with argv; return (exit_code, stdout, stderr)."""
    env = env or {}
    old_env = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    if home:
        monkeypatch.setattr(cli, "CONFIG_DIR", home / ".sentinel")
        monkeypatch.setattr(cli, "CONFIG_FILE", home / ".sentinel" / "config.toml")
        # also purge url/token from real env so config precedence is testable
        os.environ.pop("SENTINEL_API_URL", None)
        os.environ.pop("SENTINEL_TOKEN", None)
    monkeypatch.setattr(sys, "argv", ["sentinel"] + argv)
    code = 0
    try:
        cli.main()
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
    out, err = capsys.readouterr()
    for k, v in old_env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    return code, out, err


# ----------------------------------------------------------------------
# health / login / config
# ----------------------------------------------------------------------


def test_health(asgi_client_class, capsys, monkeypatch):
    code, out, err = run_cli(monkeypatch, capsys, ["health"])
    assert code == 0
    assert "Status: healthy" in out
    assert "Version:" in out


def test_config_set_url_and_token(tmp_path, asgi_client_class, capsys, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    code, out, _ = run_cli(monkeypatch, capsys, ["config", "set-url", "http://testserver"], home=home)
    assert code == 0
    cfg = (home / ".sentinel" / "config.toml").read_text()
    assert 'api_url = "http://testserver"' in cfg

    code, out, _ = run_cli(monkeypatch, capsys, ["config", "set-token", "secret-token"], home=home)
    assert code == 0
    cfg_file = home / ".sentinel" / "config.toml"
    assert 'token = "secret-token"' in cfg_file.read_text()
    if os.name != "nt":
        assert (cfg_file.stat().st_mode & 0o777) == 0o600
    else:
        acl = subprocess.run(
            ["icacls", str(cfg_file)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        assert "(F)" in acl
        assert "(I)" not in acl

    # show masks the token
    code, out, _ = run_cli(monkeypatch, capsys, ["config", "show"], home=home)
    assert code == 0
    assert "secret-token" not in out
    assert "secret-t" in out  # masked prefix


def test_token_precedence_flag_over_env_over_config(tmp_path, asgi_client_class, monkeypatch):
    home = tmp_path / "home2"
    (home / ".sentinel").mkdir(parents=True)
    (home / ".sentinel" / "config.toml").write_text('api_url = "http://cfg"\ntoken = "cfg-token"\n')
    monkeypatch.setattr(cli, "CONFIG_FILE", home / ".sentinel" / "config.toml")

    class Args:
        api_url = None
        token = None

    cfg = cli.load_config()
    assert cli.resolve_token(Args, cfg) == "cfg-token"
    monkeypatch.setenv("SENTINEL_TOKEN", "env-token")
    assert cli.resolve_token(Args, cfg) == "env-token"
    Args.token = "flag-token"
    assert cli.resolve_token(Args, cfg) == "flag-token"
    assert cli.resolve_api_url(Args, cfg) == "http://cfg"
    monkeypatch.setenv("SENTINEL_API_URL", "http://env")
    assert cli.resolve_api_url(Args, cfg) == "http://env"
    Args.api_url = "http://flag"
    assert cli.resolve_api_url(Args, cfg) == "http://flag"


def test_login_saves_token(tmp_path, asgi_client_class, capsys, monkeypatch):
    home = tmp_path / "home3"
    home.mkdir()
    code, out, err = run_cli(
        monkeypatch, capsys,
        ["login", "--username", "admin", "--password", "admin"],
        home=home,
    )
    assert code == 0, err
    assert "Logged in as admin" in out
    assert 'token = "eyJ' in (home / ".sentinel" / "config.toml").read_text()


def test_login_bad_password_friendly_error(tmp_path, asgi_client_class, capsys, monkeypatch):
    home = tmp_path / "home4"
    home.mkdir()
    code, out, err = run_cli(
        monkeypatch, capsys,
        ["login", "--username", "admin", "--password", "nope"],
        home=home,
    )
    assert code == 1
    assert "Error:" in err
    assert "Traceback" not in err  # no stack dumps


def test_protected_command_without_token_friendly_error(tmp_path, asgi_client_class, capsys, monkeypatch):
    home = tmp_path / "home5"
    home.mkdir()
    code, out, err = run_cli(monkeypatch, capsys, ["stats"], home=home)
    assert code == 2
    assert "not authenticated" in err
    assert "Traceback" not in err


# ----------------------------------------------------------------------
# analyze / rules / stats
# ----------------------------------------------------------------------


def login_then(home):
    """Write a config file containing a real JWT obtained over the ASGI wire."""
    cfg_dir = home / ".sentinel"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    import asyncio

    async def _login():
        async with SentinelClient(
            "http://testserver", transport=httpx.ASGITransport(app=fastapi_app)
        ) as c:
            t = await c.login("admin", "admin")
            return t.access_token

    token = asyncio.run(_login())
    (cfg_dir / "config.toml").write_text(
        'api_url = "http://testserver"\ntoken = "{}"\n'.format(token)
    )
    return None


def test_analyze_sample_log(tmp_path, asgi_client_class, capsys, monkeypatch):
    home = tmp_path / "home6"
    home.mkdir()
    login_then(home)
    sample = REPO_ROOT / "examples" / "logs" / "mimikatz_detection.json"
    code, out, err = run_cli(monkeypatch, capsys, ["analyze", str(sample)], home=home)
    assert code == 0, err
    assert "malicious:      True" in out
    assert "skipped_llm:    True" in out

    # --json variant (strip in-process library noise: in a real deployment the
    # "Warning: sentinel_core..." print happens server-side, not in the CLI)
    code, out, err = run_cli(monkeypatch, capsys, ["--json", "analyze", str(sample)], home=home)
    assert code == 0, err
    data = json.loads(out[out.index("{"):])
    assert data["verdict"]["malicious"] is True


def test_analyze_missing_file_friendly(tmp_path, asgi_client_class, capsys, monkeypatch):
    home = tmp_path / "home7"
    home.mkdir()
    login_then(home)
    code, out, err = run_cli(monkeypatch, capsys, ["analyze", "/no/such/file.json"], home=home)
    assert code == 1
    assert err.startswith("Error: cannot read log file")
    assert "Traceback" not in err


def test_rules_list_and_get(tmp_path, asgi_client_class, capsys, monkeypatch):
    home = tmp_path / "home8"
    home.mkdir()
    login_then(home)
    code, out, err = run_cli(monkeypatch, capsys, ["rules", "list"], home=home)
    assert code == 0, err
    assert "Total rules:" in out
    first_line = [ln for ln in out.splitlines() if ln.strip().startswith("[")][0]
    rule_id = first_line.split("]")[1].strip().split(":")[0]

    code, out, err = run_cli(monkeypatch, capsys, ["--json", "rules", "get", rule_id], home=home)
    assert code == 0, err
    data = json.loads(out)
    assert data["id"] == rule_id


def test_stats_json(tmp_path, asgi_client_class, capsys, monkeypatch):
    home = tmp_path / "home9"
    home.mkdir()
    login_then(home)
    code, out, err = run_cli(monkeypatch, capsys, ["--json", "stats"], home=home)
    assert code == 0, err
    data = json.loads(out)
    assert "total_events" in data


def test_import_wait(tmp_path, asgi_client_class, capsys, monkeypatch):
    home = tmp_path / "home10"
    home.mkdir()
    login_then(home)
    jsonl = tmp_path / "cli-batch.jsonl"
    jsonl.write_text('{"EventID": 4688, "Image": "powershell.exe"}\n{"EventID": 4625}\n')
    code, out, err = run_cli(
        monkeypatch, capsys,
        ["import", str(jsonl), "--wait", "--interval", "0.05", "--poll-timeout", "30"],
        home=home,
    )
    assert code == 0, err
    assert "import task" in out
    assert "completed: 2/2 processed" in out
