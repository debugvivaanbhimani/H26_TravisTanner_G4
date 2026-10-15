"""Sandboxed execution. Builds an isolated Python environment for a copy of the
repository, installs dependencies, probes imports and runs the test suite.

Everything this module returns was VERIFIED by actually executing it.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from .scanner import SKIP_DIRS
from .util import log, run_cmd, sha256_text, strip_output

PROBE_SCRIPT = r'''
import importlib, importlib.metadata as md, json, sys, warnings
mods = json.loads(sys.argv[1])
res = {"packages_distributions": {k: v for k, v in md.packages_distributions().items()},
       "imports": {}}
for m in mods:
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        try:
            importlib.import_module(m)
            res["imports"][m] = {"ok": True, "warnings": [f"{x.category.__name__}: {x.message}" for x in w][:5]}
        except BaseException as e:
            res["imports"][m] = {"ok": False, "error": f"{type(e).__name__}: {e}",
                                 "warnings": [f"{x.category.__name__}: {x.message}" for x in w][:5]}
print("@@PROBE@@" + json.dumps(res))
'''


def uv_bin() -> str:
    b = shutil.which("uv")
    if not b:
        raise SystemExit("`uv` is required (pip install uv). It also downloads Python 3.12 if needed.")
    return b


def copy_repo(src: Path, dest: Path) -> Path:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns(*SKIP_DIRS, "*.pyc"))
    return dest


def _parse_junit(path: Path) -> dict[str, dict]:
    out = {}
    if not path.exists():
        return out
    root = ET.parse(path).getroot()
    for tc in root.iter("testcase"):
        tid = f"{tc.get('classname')}::{tc.get('name')}"
        status, message, detail = "passed", "", ""
        for tag in ("failure", "error", "skipped"):
            el = tc.find(tag)
            if el is not None:
                status = {"failure": "failed", "error": "error", "skipped": "skipped"}[tag]
                message = (el.get("message") or "")[:500]
                detail = (el.text or "")[-2500:]
                break
        out[tid] = {"status": status, "message": message, "detail": detail,
                    "time_s": float(tc.get("time") or 0)}
    return out


SITE_RE = re.compile(r"site-packages[/\\]([A-Za-z0-9_]+)")


def _attribute_failures(tests: dict) -> dict[str, list[str]]:
    """Map third-party top-level module -> failing tests whose traceback runs through it."""
    by_mod: dict[str, list[str]] = {}
    for tid, t in tests.items():
        if t["status"] in ("failed", "error"):
            # blame the library where the error ORIGINATES (deepest frame),
            # not every library the traceback passes through
            mods = [m for m in SITE_RE.findall(t["detail"] + "\n" + t["message"])
                    if m not in ("_pytest", "pluggy", "pytest")]
            if mods:
                by_mod.setdefault(mods[-1], []).append(tid)
    return by_mod


def _warnings_summary(text: str) -> list[str]:
    if "warnings summary" not in text:
        return []
    section = text.split("warnings summary", 1)[1].split("-- Docs:", 1)[0]
    return [l.strip() for l in section.splitlines() if "Warning" in l][:20]


def run_suite(repo_copy: Path, label: str, install_files: list[str],
              probe_modules: list[str], python: str = "3.12",
              extra_requirements: list[str] | None = None,
              test_paths: list[str] | None = None) -> dict:
    """Create venv, install, probe imports, run pytest. Returns a VERIFIED record."""
    uv = uv_bin()
    venv = repo_copy.parent / f"{repo_copy.name}.venv"
    if venv.exists():
        shutil.rmtree(venv)
    py = str(venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
    steps = []
    log(f"[{label}] creating Python {python} environment")
    r = run_cmd([uv, "venv", "-q", "-p", python, str(venv)])
    steps.append(strip_output(r))
    result = {"label": label, "python": python, "steps": steps, "install_ok": False,
              "tests": {}, "summary": {}}
    if r["exit_code"] != 0:
        result["error"] = "could not create environment"
        return result

    cmd = [uv, "pip", "install", "-p", py]
    for f in install_files:
        cmd += ["-r", f]
    cmd += (extra_requirements or [])
    log(f"[{label}] installing dependencies")
    r = run_cmd(cmd, cwd=str(repo_copy), timeout=900)
    steps.append(strip_output(r))
    result["install_ok"] = r["exit_code"] == 0
    if not result["install_ok"]:
        result["error"] = "dependency installation failed"
        result["install_error"] = (r["stderr"] or r["stdout"])[-3000:]
        return result

    # make sure a test runner exists even if the repo forgot to declare one
    chk = run_cmd([py, "-c", "import pytest"])
    if chk["exit_code"] != 0:
        r = run_cmd([uv, "pip", "install", "-p", py, "pytest"])
        steps.append(strip_output(r))
        result["pytest_injected"] = True

    fr = run_cmd([uv, "pip", "freeze", "-p", py])
    freeze = fr["stdout"]
    result["freeze"] = dict(
        line.split("==", 1) for line in freeze.splitlines() if "==" in line)
    result["environment_sha256"] = sha256_text(freeze)

    pr = run_cmd([py, "-c", PROBE_SCRIPT, json.dumps(probe_modules)],
                 cwd=str(repo_copy), env={"PYTHONPATH": str(repo_copy)})
    probe = {}
    if "@@PROBE@@" in pr["stdout"]:
        probe = json.loads(pr["stdout"].split("@@PROBE@@", 1)[1])
    result["import_probe"] = probe.get("imports", {})
    result["packages_distributions"] = probe.get("packages_distributions", {})

    junit = repo_copy.parent / f"{repo_copy.name}.junit.xml"
    if junit.exists():
        junit.unlink()  # never let a previous run's results leak into this one
    cmd = [py, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-W", "default",
           f"--junitxml={junit}"] + (test_paths or [])
    log(f"[{label}] running test suite")
    r = run_cmd(cmd, cwd=str(repo_copy), env={"PYTHONPATH": str(repo_copy)}, timeout=900)
    steps.append(strip_output(r, 8000))
    tests = _parse_junit(junit)
    result["tests"] = tests
    counts = {"passed": 0, "failed": 0, "error": 0, "skipped": 0}
    for t in tests.values():
        counts[t["status"]] += 1
    counts["total"] = len(tests)
    counts["pytest_exit_code"] = r["exit_code"]
    result["summary"] = counts
    result["failure_modules"] = _attribute_failures(tests)
    result["warnings"] = _warnings_summary(r["stdout"])
    log(f"[{label}] tests: {counts['passed']} passed, {counts['failed'] + counts['error']} failed")
    return result


def compare_runs(base: dict, cand: dict) -> dict:
    """Per-test comparison of two runs. VERIFIED."""
    bt, ct = base.get("tests", {}), cand.get("tests", {})
    ok = lambda s: s in ("passed", "skipped")
    rows = {"fixed": [], "regressed": [], "still_passing": [], "still_failing": [],
            "new_tests": [], "removed_tests": []}
    for tid in sorted(set(bt) | set(ct)):
        if tid not in bt:
            rows["new_tests"].append({"test": tid, "status": ct[tid]["status"],
                                      "message": ct[tid]["message"]})
        elif tid not in ct:
            rows["removed_tests"].append({"test": tid})
        elif ok(bt[tid]["status"]) and ok(ct[tid]["status"]):
            rows["still_passing"].append(tid)
        elif not ok(bt[tid]["status"]) and ok(ct[tid]["status"]):
            rows["fixed"].append(tid)
        elif ok(bt[tid]["status"]) and not ok(ct[tid]["status"]):
            rows["regressed"].append({"test": tid, "message": ct[tid]["message"]})
        else:
            rows["still_failing"].append({"test": tid, "message": ct[tid]["message"]})
    rows["install_ok"] = {"original": base.get("install_ok"), "candidate": cand.get("install_ok")}
    rows["verdict"] = _verdict(rows, cand)
    return rows


def _verdict(rows: dict, cand: dict) -> str:
    if not cand.get("install_ok"):
        return "candidate_install_failed"
    # pytest exit codes: 0 ok, 1 test failures, 5 no tests; 2/3/4 = interrupted, internal or
    # usage/collection error (e.g. conftest import failure) -> the suite did not really run
    if not cand.get("tests") or cand.get("summary", {}).get("pytest_exit_code") not in (0, 1, 5):
        return "tests_did_not_run"
    new_fail = [t for t in rows["new_tests"] if t["status"] in ("failed", "error")]
    if rows["regressed"] or new_fail:
        return "regressions"
    if rows["still_failing"]:
        return "no_regressions_but_preexisting_failures"
    return "all_tests_pass"
