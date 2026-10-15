"""Shared helpers: command execution with evidence capture, logging, hashing."""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

_T0 = time.time()


def log(msg: str) -> None:
    elapsed = time.time() - _T0
    print(f"[{elapsed:6.1f}s] {msg}", file=sys.stderr, flush=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def tail(text: str, max_chars: int = 6000) -> str:
    if len(text) <= max_chars:
        return text
    return "...[truncated]...\n" + text[-max_chars:]


def run_cmd(cmd: list[str], cwd: str | None = None, env: dict | None = None,
            timeout: int = 600) -> dict:
    """Run a command and return a full evidence record of what happened.

    Every record keeps the exact command, the working directory, the exit code,
    the time it took and the (tail of the) output, so a judge can re-run it.
    """
    started = now_iso()
    t = time.time()
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    try:
        proc = subprocess.run(cmd, cwd=cwd, env=full_env, capture_output=True,
                              text=True, timeout=timeout)
        code, out, err = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        code = -1
        out = exc.stdout if isinstance(exc.stdout, str) else ""
        err = f"TIMEOUT after {timeout}s"
    except FileNotFoundError as exc:
        code, out, err = -2, "", f"command not found: {exc}"
    return {
        "command": " ".join(cmd),
        "cwd": cwd,
        "started_at": started,
        "duration_s": round(time.time() - t, 2),
        "exit_code": code,
        "stdout": out,
        "stderr": err,
    }


def strip_output(record: dict, max_chars: int = 4000) -> dict:
    """Copy of a run record with output trimmed, for storing in the capsule."""
    r = dict(record)
    r["stdout"] = tail(r.get("stdout") or "", max_chars)
    r["stderr"] = tail(r.get("stderr") or "", max_chars)
    return r


def load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader so the tool needs no extra dependency."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))
