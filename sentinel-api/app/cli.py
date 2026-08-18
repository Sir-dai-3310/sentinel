"""Sentinel CLI - Command-line interface."""

import argparse
import asyncio
import json
import os
import sys

import httpx


class SentinelCLI:
    """Sentinel command-line client."""

    def __init__(self, api_url: str, token: str):
        self.api_url = api_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def analyze(self, log_file: str) -> dict:
        """Analyze a log file."""
        with open(log_file, "r") as f:
            log = json.load(f)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_url}/api/v1/analyze",
                json={"log": log},
                headers=self.headers,
                timeout=60,
            )
            response.raise_for_status()
            return response.json()

    async def list_rules(self) -> dict:
        """List all rules."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_url}/api/v1/rules",
                headers=self.headers,
                timeout=30,
            )
            response.raise_for_status()
            return response.json()

    async def get_stats(self) -> dict:
        """Get system statistics."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_url}/api/v1/stats",
                headers=self.headers,
                timeout=30,
            )
            response.raise_for_status()
            return response.json()

    async def health(self) -> dict:
        """Check API health."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_url}/api/v1/health",
                timeout=10,
            )
            response.raise_for_status()
            return response.json()


def main():
    parser = argparse.ArgumentParser(
        description="Sentinel CLI - AI-powered security log analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  sentinel analyze suspicious.json
  sentinel rules list
  sentinel stats
  sentinel health
        """,
    )

    parser.add_argument(
        "--api-url",
        default=os.getenv("SENTINEL_API_URL", "http://localhost:8000"),
        help="Sentinel API URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("SENTINEL_TOKEN", ""),
        help="JWT authentication token",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # analyze command
    analyze_parser = subparsers.add_parser("analyze", help="Analyze a log file")
    analyze_parser.add_argument("file", help="Path to JSON log file")

    # rules command
    rules_parser = subparsers.add_parser("rules", help="Manage rules")
    rules_parser.add_subparsers(dest="rules_action")

    # stats command
    subparsers.add_parser("stats", help="Show system statistics")

    # health command
    subparsers.add_parser("health", help="Check API health")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    cli = SentinelCLI(args.api_url, args.token)

    async def run():
        if args.command == "analyze":
            result = await cli.analyze(args.file)
            print(json.dumps(result, indent=2, ensure_ascii=False))

        elif args.command == "rules":
            result = await cli.list_rules()
            print(f"Total rules: {result['total']}")
            for rule in result["rules"]:
                print(f"  [{rule['level']}] {rule['id']}: {rule['title']}")

        elif args.command == "stats":
            result = await cli.get_stats()
            print(json.dumps(result, indent=2))

        elif args.command == "health":
            result = await cli.health()
            print(f"Status: {result['status']}")
            print(f"Version: {result['version']}")
            for name, status in result.get("services", {}).items():
                print(f"  {name}: {status}")

    asyncio.run(run())


if __name__ == "__main__":
    main()
