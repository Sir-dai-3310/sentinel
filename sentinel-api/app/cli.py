"""Sentinel CLI - full command-line interface built on the Sentinel SDK.

Backwards compatible entry point: ``python -m app.cli ...``

Configuration lives in ~/.sentinel/config.toml; token resolution order:
``--token`` > ``SENTINEL_TOKEN`` env > config file. Same for the API URL:
``--api-url`` > ``SENTINEL_API_URL`` env > config file > default.
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    from sentinel_sdk import SentinelClient, SentinelError, RateLimitError
except ImportError:  # pragma: no cover - environment issue, give a clear hint
    print(
        "Error: sentinel_sdk is not installed. Install it with:\n"
        "  pip install -e sdk/    # from the repo root",
        file=sys.stderr,
    )
    sys.exit(1)

CONFIG_DIR = Path.home() / ".sentinel"
CONFIG_FILE = CONFIG_DIR / "config.toml"
DEFAULT_API_URL = "http://localhost:8000"


# ----------------------------------------------------------------------
# config file (~/.sentinel/config.toml)
# ----------------------------------------------------------------------


def load_config() -> dict[str, Any]:
    """Load ~/.sentinel/config.toml (empty dict if absent/corrupt)."""
    if not CONFIG_FILE.exists():
        return {}
    try:
        import tomllib

        with open(CONFIG_FILE, "rb") as f:
            data = tomllib.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:  # corrupt config should never kill the CLI
        print(f"Warning: ignoring unreadable config {CONFIG_FILE}: {e}", file=sys.stderr)
        return {}


def save_config(cfg: dict[str, Any]) -> None:
    """Write config with 0600 permissions (it may hold a token)."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    lines = ["# Sentinel CLI configuration"]
    for key in ("api_url", "token"):
        value = cfg.get(key)
        if value:
            escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{key} = "{escaped}"')
    CONFIG_FILE.write_text("\n".join(lines) + "\n")
    CONFIG_FILE.chmod(0o600)


def resolve_api_url(args: argparse.Namespace, cfg: dict[str, Any]) -> str:
    """--api-url > SENTINEL_API_URL env > config file > default."""
    if args.api_url:
        return args.api_url
    env = os.getenv("SENTINEL_API_URL")
    if env:
        return env
    return cfg.get("api_url", DEFAULT_API_URL)


def resolve_token(args: argparse.Namespace, cfg: dict[str, Any]) -> str:
    """--token > SENTINEL_TOKEN env > config file."""
    if args.token:
        return args.token
    env = os.getenv("SENTINEL_TOKEN")
    if env:
        return env
    return cfg.get("token", "")


# ----------------------------------------------------------------------
# output helpers
# ----------------------------------------------------------------------


def emit(args: argparse.Namespace, data: Any, human: str | None = None) -> None:
    """Print --json as raw JSON, otherwise the human-friendly rendering."""
    if getattr(args, "json", False):
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
    elif human is not None:
        print(human)
    else:
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def die(message: str, code: int = 1) -> None:
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(code)


def require_token(token: str) -> None:
    if not token:
        die(
            "not authenticated. Run `python -m app.cli login` or set a token via "
            "--token / SENTINEL_TOKEN / `config set-token`.",
            code=2,
        )


def friendly_error(e: Exception) -> None:
    """Map SDK exceptions to one-line messages (never a stack trace)."""
    if isinstance(e, RateLimitError):
        wait = f" Retry after {e.retry_after}s." if e.retry_after else ""
        die(f"rate limit exceeded.{wait}", code=1)
    if isinstance(e, SentinelError):
        detail = e.detail if isinstance(e.detail, str) else ""
        suffix = f": {detail}" if detail and detail != str(e) else ""
        die(f"{e}{suffix}" if suffix else str(e), code=1)
    die(f"unexpected failure: {type(e).__name__}: {e}", code=1)


# ----------------------------------------------------------------------
# subcommand handlers (async)
# ----------------------------------------------------------------------


async def cmd_login(args, cfg) -> None:
    api_url = resolve_api_url(args, cfg)
    username = args.username or os.getenv("SENTINEL_USER") or "admin"
    password = args.password or os.getenv("SENTINEL_PASSWORD")
    if not password:
        import getpass

        password = getpass.getpass(f"Password for {username}@{api_url}: ")
    async with SentinelClient(api_url, timeout=args.timeout) as client:
        try:
            token = await client.login(username, password)
        except Exception as e:
            friendly_error(e)
    cfg["api_url"] = api_url
    cfg["token"] = token.access_token
    save_config(cfg)
    emit(
        args,
        {"api_url": api_url, "username": username, "token_saved": str(CONFIG_FILE)},
        human=f"✅ Logged in as {username} — token saved to {CONFIG_FILE}",
    )


async def cmd_analyze(args, cfg, client) -> None:
    try:
        with open(args.file, "r") as f:
            if args.file.endswith((".jsonl", ".ndjson")):
                logs = [json.loads(line) for line in f if line.strip()]
            else:
                logs = [json.load(f)]
    except (OSError, json.JSONDecodeError) as e:
        die(f"cannot read log file {args.file}: {e}")

    if len(logs) == 1:
        result = await client.analyze(logs[0])
        data = {
            "verdict": result.verdict,
            "rule_hits": result.rule_hits,
            "threat_intel": result.threat_intel,
            "agent_trace": result.agent_trace,
            "skipped_llm": result.skipped_llm,
            "metadata": result.metadata,
        }
        if args.json:
            emit(args, data)
            return
        verdict = result.verdict or {}
        print(f"malicious:      {verdict.get('malicious')}")
        print(f"danger_level:   {verdict.get('danger_level')}")
        print(f"reason:         {verdict.get('reason')}")
        for t in verdict.get("mitre_techniques") or []:
            print(f"mitre:          {t}")
        for a in verdict.get("recommended_actions") or []:
            print(f"action:         {a}")
        print(f"rule_hits:      {len(result.rule_hits)}")
        print(f"agent_trace:    {' -> '.join(result.agent_trace)}")
        print(f"skipped_llm:    {result.skipped_llm}")
    else:
        # JSONL: analyze each row through the batch endpoint for throughput.
        batch = await client.analyze_batch(logs)
        data = {
            "results": batch.results,
            "total": batch.total,
            "successful": batch.successful,
            "failed": batch.failed,
            "throughput_eps": batch.throughput_eps,
        }
        if args.json:
            emit(args, data)
            return
        print(f"total={batch.total} successful={batch.successful} "
              f"failed={batch.failed} throughput={batch.throughput_eps} eps")
        for i, r in enumerate(batch.results):
            v = r.get("verdict") or {}
            marker = "🔴" if v.get("malicious") else "🟢"
            print(f"  {marker} [{i}] malicious={v.get('malicious')} "
                  f"danger={v.get('danger_level')} {str(v.get('reason'))[:80]}")


async def cmd_rules(args, cfg, client) -> None:
    action = args.rules_action
    if action == "list":
        result = await client.list_rules()
        rules = [r.__dict__ for r in result.rules]
        if args.json:
            emit(args, {"total": result.total, "rules": rules})
            return
        print(f"Total rules: {result.total}")
        for r in result.rules:
            print(f"  [{r.level:8s}] {r.id}: {r.title}")
    elif action == "get":
        rule = await client.get_rule(args.id)
        emit(args, rule.to_dict(), human=json.dumps(rule.to_dict(), indent=2, ensure_ascii=False))
    elif action == "create":
        try:
            with open(args.file, "r") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            die(f"cannot read rule file {args.file}: {e}")
        result = await client.create_rule(payload)
        emit(args, result, human=f"✅ Rule created at {result.get('file_path')}")
    elif action == "update":
        try:
            with open(args.file, "r") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            die(f"cannot read rule file {args.file}: {e}")
        result = await client.update_rule(payload.get("id", ""), payload)
        emit(args, result, human=f"✅ Rule updated at {result.get('file_path')}")
    elif action == "delete":
        result = await client.delete_rule(args.id)
        emit(args, result, human=f"✅ Rule {args.id} deleted")
    elif action == "reload":
        result = await client.reload_rules()
        emit(args, result, human=f"✅ {result.get('count')} rules reloaded")
    else:
        die("usage: rules {list|get|create|update|delete|reload}", code=2)


async def cmd_stats(args, cfg, client) -> None:
    stats = await client.get_stats()
    data = {
        "total_events": stats.total_events,
        "alerts": stats.alerts,
        "critical": stats.critical,
        "accuracy": stats.accuracy,
    }
    if args.json:
        emit(args, data)
        return
    print(f"total_events: {stats.total_events}")
    print(f"alerts:       {stats.alerts}")
    print(f"critical:     {stats.critical}")
    print(f"accuracy:     {stats.accuracy}")


async def cmd_llm_costs(args, cfg, client) -> None:
    costs = await client.llm_costs()
    emit(args, costs)


async def cmd_health(args, cfg, client) -> None:
    health = await client.health()
    data = {"status": health.status, "version": health.version, "services": health.services}
    if args.json:
        emit(args, data)
        return
    print(f"Status: {health.status}")
    print(f"Version: {health.version}")
    for name, status in health.services.items():
        print(f"  {name}: {status}")


async def cmd_import(args, cfg, client) -> None:
    task = await client.import_logs(args.file)
    if args.json:
        emit(args, task.__dict__)
    else:
        print(f"import task {task.task_id}: {task.status}")
    if args.wait:
        try:
            final = await client.poll_import(
                task.task_id, wait=True, interval=args.interval, timeout=args.poll_timeout
            )
        except TimeoutError as e:
            die(str(e))
        if args.json:
            emit(args, final.__dict__)
        else:
            print(f"✅ {final.status}: {final.processed}/{final.total} processed, "
                  f"{final.failed} failed")


async def cmd_privacy(args, cfg, client) -> None:
    if args.privacy_action == "export":
        result = await client.export_privacy(args.subject)
        if args.json:
            emit(args, result)
        else:
            print(f"subject: {result['subject']}")
            print(f"record_count: {result['record_count']}")
            print(json.dumps(result["analysis_results"], indent=2, ensure_ascii=False))
    elif args.privacy_action == "delete":
        if not args.yes:
            confirm = input(f"Erase ALL data for subject '{args.subject}'? [y/N] ")
            if confirm.lower() not in ("y", "yes"):
                print("aborted.")
                return
        result = await client.delete_privacy(args.subject)
        emit(args, result, human=f"✅ erased {result.get('deleted_count')} records for {args.subject}")
    else:
        die("usage: privacy {export|delete} <subject>", code=2)


def cmd_config(args, cfg) -> None:
    if args.config_action == "set-url":
        cfg["api_url"] = args.value
        save_config(cfg)
        print(f"✅ api_url = {args.value} (saved to {CONFIG_FILE})")
    elif args.config_action == "set-token":
        cfg["token"] = args.value
        save_config(cfg)
        print(f"✅ token saved to {CONFIG_FILE} (mode 0600)")
    elif args.config_action == "show":
        shown = dict(cfg)
        if shown.get("token"):
            t = shown["token"]
            shown["token"] = t[:8] + "..." if len(t) > 8 else "***"
        print(json.dumps(shown, indent=2))
    elif args.config_action == "path":
        print(CONFIG_FILE)
    else:
        die("usage: config {set-url|set-token|show|path}", code=2)


# ----------------------------------------------------------------------
# argument parsing
# ----------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sentinel",
        description="Sentinel CLI - AI-powered security log analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  sentinel login --username admin --password admin
  sentinel analyze suspicious.json
  sentinel analyze batch.jsonl --json
  sentinel rules list
  sentinel rules get <rule-id> --json
  sentinel rules create rule.json
  sentinel import logs.jsonl --wait
  sentinel privacy export alice --json
  sentinel config set-url http://localhost:8000
        """,
    )
    parser.add_argument(
        "--api-url",
        default=None,
        help="Sentinel API URL (priority: flag > env SENTINEL_API_URL > config > default)",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Bearer token (priority: flag > env SENTINEL_TOKEN > config)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of human-friendly text",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Request timeout in seconds (default: 30)",
    )

    sub = parser.add_subparsers(dest="command", help="Available commands")

    p = sub.add_parser("login", help="Authenticate and save token to config")
    p.add_argument("--username", default=None)
    p.add_argument("--password", default=None)

    p = sub.add_parser("analyze", help="Analyze a log file (JSON or JSONL)")
    p.add_argument("file", help="Path to .json (single log) or .jsonl (batch)")

    p = sub.add_parser("rules", help="Manage Sigma rules")
    rules_sub = p.add_subparsers(dest="rules_action")
    rules_sub.add_parser("list", help="List all rules")
    g = rules_sub.add_parser("get", help="Get a rule by id")
    g.add_argument("id")
    c = rules_sub.add_parser("create", help="Create a rule from a JSON file")
    c.add_argument("file")
    u = rules_sub.add_parser("update", help="Update a rule from a JSON file")
    u.add_argument("file")
    d = rules_sub.add_parser("delete", help="Delete a rule by id")
    d.add_argument("id")
    rules_sub.add_parser("reload", help="Reload rules in the engine")

    sub.add_parser("stats", help="Show dashboard statistics")
    sub.add_parser("llm-costs", help="Show LLM usage/cost summary")
    sub.add_parser("health", help="Check API health")

    p = sub.add_parser("import", help="Bulk-import a JSONL/CSV file")
    p.add_argument("file")
    p.add_argument("--wait", action="store_true", help="Poll until the import completes")
    p.add_argument("--interval", type=float, default=1.0, help="Poll interval seconds")
    p.add_argument("--poll-timeout", type=float, default=300.0, help="Max seconds to poll")

    p = sub.add_parser("privacy", help="GDPR data-subject rights (admin)")
    priv_sub = p.add_subparsers(dest="privacy_action")
    e = priv_sub.add_parser("export", help="Export all data for a subject")
    e.add_argument("subject")
    d = priv_sub.add_parser("delete", help="Erase all data for a subject")
    d.add_argument("subject")
    d.add_argument("--yes", action="store_true", help="Skip confirmation prompt")

    p = sub.add_parser("config", help="Manage CLI configuration")
    cfg_sub = p.add_subparsers(dest="config_action")
    s = cfg_sub.add_parser("set-url", help="Set default API URL")
    s.add_argument("value")
    s = cfg_sub.add_parser("set-token", help="Store a bearer token")
    s.add_argument("value")
    cfg_sub.add_parser("show", help="Show current config (token masked)")
    cfg_sub.add_parser("path", help="Print config file path")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    cfg = load_config()

    if args.command == "config":
        cmd_config(args, cfg)
        return

    async def run() -> None:
        api_url = resolve_api_url(args, cfg)
        token = resolve_token(args, cfg)

        if args.command == "login":
            await cmd_login(args, cfg)
            return

        if args.command != "health":
            require_token(token)

        async with SentinelClient(api_url, token=token or None, timeout=args.timeout) as client:
            handlers = {
                "analyze": cmd_analyze,
                "rules": cmd_rules,
                "stats": cmd_stats,
                "llm-costs": cmd_llm_costs,
                "health": cmd_health,
                "import": cmd_import,
                "privacy": cmd_privacy,
            }
            handler = handlers.get(args.command)
            if handler is None:
                parser.print_help()
                sys.exit(2)
            try:
                await handler(args, cfg, client)
            except Exception as e:
                friendly_error(e)

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        die("interrupted", code=130)


if __name__ == "__main__":
    main()
