"""Run a task's unit tests inside its own directory."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run_tests(work_dir: Path, timeout: float = 20) -> tuple[int, str]:
    scripts = sorted(work_dir.glob("test_*.py"))
    if not scripts:
        return 1, "no test_*.py"
    script = scripts[0]
    completed = subprocess.run(
        [sys.executable, script.name],
        cwd=work_dir,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    return completed.returncode, output[-4000:]
