"""Migration + self-healing fix loop.

For each dependency the AI wants to change:
  1. Gemma writes concrete file edits and a behavioural-equivalence test.
  2. The equivalence test is executed against the ORIGINAL code + dependency.
  3. Edits are applied to a fresh copy and the full suite runs against the REPLACEMENT.
  4. If anything regresses, the real failure output goes back to Gemma for a fix,
     up to N attempts.
Every attempt, edit and test result is recorded.
"""
from __future__ import annotations

import difflib
import json
from pathlib import Path

from . import executor
from .gemma import Gemma
from .scanner import read_files
from .util import log

EDIT_PROMPT = """You are migrating the Python repository below on Python {python}.

DEPENDENCY: {name}
AI PLAN (from an earlier analysis step): {plan}

OBSERVED USAGE of this dependency in the repository:
{usage}

BASELINE TEST RESULTS with the original dependency: {baseline_summary}
Baseline failures related to this dependency:
{baseline_failures}

FILES (current content):
{files}

TASK
1. Produce the minimal file edits that carry out the plan. Edit EVERY manifest that declares
   the dependency (requirements*.txt AND pyproject.toml) so they stay consistent. Change source
   code only where the replacement needs it. Do not touch unrelated code. Do not delete tests.
2. Write ONE pytest file named "{test_path}" that checks the repository's OWN behaviour which
   depends on {name} (call the repo's functions, not the library directly). These tests must pass
   on the ORIGINAL code and must keep passing after the migration — they prove behaviour is
   preserved. Use only the standard library, pytest, and the repository's own modules. Use the
   tmp_path / monkeypatch fixtures; never touch the network or the real home directory.

Each edit is an exact search/replace on one file. "search" must be copied EXACTLY from the file
content above (including indentation) and must occur exactly once. To create a new file use
"search": "".

Return JSON: {{"edits": [{{"file": "...", "search": "...", "replace": "..."}}],
"equivalence_test": {{"path": "{test_path}", "content": "..."}},
"explanation": "..."}}
"""

FIX_PROMPT = """Your previous migration of dependency {name} was applied and executed. It did
NOT pass verification. Here is what actually happened (real output):

{problem}

FILES (current content, after your previous edits):
{files}

Return ONLY additional exact search/replace edits (against the CURRENT content above) that fix
the problem without weakening or deleting tests. You may also return an updated equivalence test
if it was itself wrong, but it must still test the repository's behaviour.

Return JSON: {{"edits": [{{"file": "...", "search": "...", "replace": "..."}}],
"equivalence_test": null or {{"path": "{test_path}", "content": "..."}},
"explanation": "..."}}
"""


def apply_edits(repo: Path, edits: list[dict]) -> list[dict]:
    results = []
    for e in edits or []:
        rel = e.get("file", "")
        p = (repo / rel).resolve()
        if not str(p).startswith(str(repo.resolve())) or not rel:
            results.append({**_short(e), "applied": False, "reason": "path outside repository"})
            continue
        search, replace = e.get("search", ""), e.get("replace", "")
        if not p.exists():
            if search == "":
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(replace, encoding="utf-8")
                results.append({**_short(e), "applied": True, "created": True})
            else:
                results.append({**_short(e), "applied": False, "reason": "file not found"})
            continue
        text = p.read_text(encoding="utf-8")
        if search == "":
            p.write_text(text + ("" if text.endswith("\n") else "\n") + replace, encoding="utf-8")
            results.append({**_short(e), "applied": True, "appended": True})
            continue
        n = text.count(search)
        if n == 1:
            p.write_text(text.replace(search, replace, 1), encoding="utf-8")
            results.append({**_short(e), "applied": True})
            continue
        # tolerate trailing-whitespace differences only
        norm = lambda s: "\n".join(l.rstrip() for l in s.splitlines())
        if norm(text).count(norm(search)) == 1:
            p.write_text(norm(text).replace(norm(search), replace, 1) + "\n", encoding="utf-8")
            results.append({**_short(e), "applied": True, "whitespace_normalised": True})
        else:
            results.append({**_short(e), "applied": False,
                            "reason": f"search text found {n} times (needs exactly 1)"})
    return results


def _short(e):
    return {"file": e.get("file"), "search": (e.get("search") or "")[:400],
            "replace": (e.get("replace") or "")[:400]}


def unified_diff(orig: Path, new: Path, files: list[str]) -> str:
    chunks = []
    for rel in sorted(set(files)):
        a = (orig / rel).read_text(encoding="utf-8").splitlines(True) if (orig / rel).exists() else []
        b = (new / rel).read_text(encoding="utf-8").splitlines(True) if (new / rel).exists() else []
        chunks.extend(difflib.unified_diff(a, b, f"a/{rel}", f"b/{rel}"))
    return "".join(chunks)


def _files_block(repo: Path, rels) -> str:
    files = read_files(repo, rels)
    return "\n\n".join(f"=== {k} ===\n{v}" for k, v in files.items())


def _problem_text(cand: dict, cmp: dict, eq_orig: dict | None, eq_test_path: str) -> str:
    lines = []
    if not cand.get("install_ok"):
        lines.append("Dependency installation FAILED:\n" + (cand.get("install_error") or "")[-2500:])
    for r in cmp.get("regressed", [])[:6]:
        d = cand["tests"].get(r["test"], {})
        lines.append(f"REGRESSION {r['test']}: {d.get('message')}\n{d.get('detail', '')[-1500:]}")
    for r in cmp.get("new_tests", []):
        if r["status"] in ("failed", "error"):
            d = cand["tests"].get(r["test"], {})
            lines.append(f"EQUIVALENCE TEST FAILED after migration {r['test']}: {d.get('message')}\n{d.get('detail', '')[-1500:]}")
    if cand.get("install_ok") and (cmp.get("verdict") == "tests_did_not_run"
                                   or cand.get("summary", {}).get("pytest_exit_code") not in (0, 1)):
        out = cand["steps"][-1].get("stdout", "") if cand.get("steps") else ""
        lines.append("The test suite could not run (collection/import error). pytest output:\n" + out[-3500:])
    if eq_orig is not None:
        bad = {k: v for k, v in eq_orig.get("tests", {}).items() if v["status"] in ("failed", "error")}
        for k, v in list(bad.items())[:4]:
            lines.append(f"EQUIVALENCE TEST FAILED ON THE ORIGINAL CODE (so the test itself is wrong) {k}: "
                         f"{v['message']}\n{v['detail'][-1200:]}")
    return "\n\n".join(lines) or "Unknown failure."


def migrate_dependency(gemma: Gemma, dep: dict, ai: dict, ctx: dict, max_fix: int = 2) -> dict:
    """Run the full verify loop for one dependency. Returns VERIFIED execution evidence."""
    name = dep["name"]
    src: Path = ctx["repo"]
    work: Path = ctx["work"] / f"mig_{name}"
    work.mkdir(parents=True, exist_ok=True)
    test_path = f"tests/test_depexit_{name.replace('-', '_')}.py"
    baseline = ctx["baseline"]

    related_files = {u["file"] for u in dep["usage"]} | set(ctx["manifest_files"])
    base_fail = [f"{t}: {baseline['tests'][t]['message']}"
                 for mod in dep["modules"] for t in baseline.get("failure_modules", {}).get(mod, [])]
    prompt = EDIT_PROMPT.format(
        python=ctx["python"], name=name,
        plan=json.dumps({k: ai.get(k) for k in ("action", "replacement", "migration_steps",
                                                 "expected_compatibility_gaps")}),
        usage="\n".join(f"{u['file']}:{u['line']} [{u['kind']}] {u['code']}" for u in dep["usage"]
                        if u["kind"] != "reference")[:4000] or "(not imported anywhere)",
        baseline_summary=json.dumps(baseline.get("summary")),
        baseline_failures="\n".join(base_fail) or "(none)",
        files=_files_block(src, related_files), test_path=test_path)

    record = {"dependency": name, "attempts": [], "status": "failed"}
    log(f"[{name}] asking Gemma for migration edits")
    try:
        resp = gemma.generate_json(prompt, purpose=f"migrate:{name}")
    except Exception as exc:
        record["error"] = f"AI step failed: {exc}"
        return record

    cand_repo = executor.copy_repo(src, work / "candidate")
    all_edits, eq_test = [], None
    for attempt in range(max_fix + 1):
        edits = resp.get("edits") or []
        applied = apply_edits(cand_repo, edits)
        all_edits += [e for e in edits]
        if resp.get("equivalence_test") and resp["equivalence_test"].get("content"):
            eq_test = resp["equivalence_test"]["content"]
            (cand_repo / test_path).parent.mkdir(parents=True, exist_ok=True)
            (cand_repo / test_path).write_text(eq_test, encoding="utf-8")

        # equivalence test against the ORIGINAL dependency/code
        eq_orig = None
        if eq_test and eq_test == record.get("_last_eq"):
            eq_orig = record["_last_eq_run"]
        elif eq_test:
            orig_repo = executor.copy_repo(src, work / f"original_eq_{attempt}")
            (orig_repo / test_path).parent.mkdir(parents=True, exist_ok=True)
            (orig_repo / test_path).write_text(eq_test, encoding="utf-8")
            eq_orig = executor.run_suite(orig_repo, f"{name}/original+equivalence-test#{attempt}",
                                         ctx["install_files"], dep["modules"], ctx["python"],
                                         test_paths=[test_path])
            record["_last_eq"], record["_last_eq_run"] = eq_test, eq_orig

        cand = executor.run_suite(cand_repo, f"{name}/candidate#{attempt}", ctx["install_files"],
                                  ctx["probe_modules"], ctx["python"])
        cmp = executor.compare_runs(baseline, cand)
        eq_ok_orig = eq_orig is None or (eq_orig.get("summary", {}).get("failed", 0)
                                         + eq_orig.get("summary", {}).get("error", 0) == 0
                                         and eq_orig.get("summary", {}).get("total", 0) > 0)
        record["attempts"].append({
            "attempt": attempt, "ai_explanation": resp.get("explanation"),
            "edits": applied, "candidate_run": _slim(cand), "comparison": cmp,
            "equivalence_on_original": _slim(eq_orig) if eq_orig else None,
            "equivalence_valid_on_original": eq_ok_orig,
        })
        passed = cmp["verdict"] in ("all_tests_pass", "no_regressions_but_preexisting_failures") and eq_ok_orig
        if passed:
            record["status"] = "verified"
            break
        if attempt == max_fix:
            record["status"] = "unresolved"
            break
        problem = _problem_text(cand, cmp, eq_orig, test_path)
        changed = {e.get("file") for e in all_edits if e.get("file")} | related_files | {test_path}
        log(f"[{name}] verification failed ({cmp['verdict']}); sending real errors back to Gemma (fix {attempt + 1}/{max_fix})")
        try:
            resp = gemma.generate_json(FIX_PROMPT.format(name=name, problem=problem[:9000],
                                                         files=_files_block(cand_repo, changed),
                                                         test_path=test_path),
                                       purpose=f"fix:{name}:{attempt + 1}")
        except Exception as exc:
            record["error"] = f"AI fix step failed: {exc}"
            record["status"] = "unresolved"
            break

    changed_files = sorted({e.get("file") for e in all_edits if e.get("file")} | {test_path})
    record["changed_files"] = changed_files
    record["diff"] = unified_diff(src, cand_repo, changed_files)
    record["final_edits"] = all_edits
    record["equivalence_test"] = {"path": test_path, "content": eq_test}
    record["candidate_repo"] = str(cand_repo)
    record.pop("_last_eq", None)
    record.pop("_last_eq_run", None)
    log(f"[{name}] result: {record['status']}")
    return record


def _slim(run: dict | None) -> dict | None:
    if not run:
        return None
    keep = ("label", "python", "install_ok", "summary", "environment_sha256", "error",
            "install_error", "failure_modules", "warnings")
    out = {k: run.get(k) for k in keep if k in run}
    out["tests"] = {k: {"status": v["status"], "message": v["message"]} for k, v in run.get("tests", {}).items()}
    out["commands"] = [{k: s[k] for k in ("command", "exit_code", "duration_s", "started_at")}
                       for s in run.get("steps", [])]
    out["import_probe"] = run.get("import_probe")
    out["freeze"] = run.get("freeze")
    return out


def combined_migration(dep_results: dict[str, dict], ctx: dict) -> dict:
    """Apply every verified migration together and run the whole suite once more."""
    src: Path = ctx["repo"]
    repo = executor.copy_repo(src, ctx["work"] / "combined" / "repo")
    applied, files = [], set()
    for name, r in sorted(dep_results.items()):
        if r.get("status") != "verified":
            continue
        res = apply_edits(repo, r.get("final_edits", []))
        applied.append({"dependency": name, "edits": res})
        files |= set(r.get("changed_files", []))
        eq = r.get("equivalence_test") or {}
        if eq.get("content"):
            (repo / eq["path"]).write_text(eq["content"], encoding="utf-8")
    if not applied:
        return {"status": "skipped", "reason": "no verified migrations to combine"}
    run = executor.run_suite(repo, "combined/all-verified-migrations", ctx["install_files"],
                             ctx["probe_modules"], ctx["python"])
    cmp = executor.compare_runs(ctx["baseline"], run)
    conflicts = [e for a in applied for e in a["edits"] if not e["applied"]]
    return {"status": "verified" if cmp["verdict"] in ("all_tests_pass",) and not conflicts
            else "partial", "applied": applied, "edit_conflicts": conflicts,
            "run": _slim(run), "comparison": cmp,
            "diff": unified_diff(src, repo, sorted(files)), "repo": str(repo)}
