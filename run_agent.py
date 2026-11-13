"""Entry point. Organizers call: python /app/run_agent.py --tasks-dir /data/tasks"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from harness.runner import run


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Solve contest tasks inside a token budget.")
    parser.add_argument("--tasks-dir", default=os.environ.get("TASKS", ""), help="Directory of task folders.")
    parser.add_argument("--budget", type=int, default=None, help="Output-equivalent token budget. Defaults to $BUDGET.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if not args.tasks_dir:
        print("pass --tasks-dir or set TASKS", file=sys.stderr)
        return 2
    asyncio.run(run(Path(args.tasks_dir), args.budget))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
