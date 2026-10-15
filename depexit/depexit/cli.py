"""DepExit — Dependency Exit Capsule generator powered by Gemma 4.

usage:
  python -m depexit <repo path or git URL> [--out capsule] [--only a,b] [--max-fix 2]
                    [--workers 3] [--python 3.12] [--no-ai]
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tomllib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from packaging.utils import canonicalize_name

from . import __version__, analysis, capsule, executor, migrate, pypi, risk, scanner
from .util import load_dotenv, log, now_iso, run_cmd


def resolve_repo(target: str, work: Path) -> tuple[Path, dict]:
    info = {"input": target}
    if target.startswith(("http://", "https://", "git@")):
        dest = work / "source"
        if dest.exists():
            shutil.rmtree(dest)
        r = run_cmd(["git", "clone", "--depth", "1", target, str(dest)], timeout=300)
        if r["exit_code"] != 0:
            raise SystemExit(f"git clone failed: {r['stderr']}")
        repo = dest
    else:
        repo = Path(target).resolve()
        if not repo.is_dir():
            raise SystemExit(f"not a directory: {target}")
    sha = run_cmd(["git", "rev-parse", "HEAD"], cwd=str(repo))
    info["commit"] = sha["stdout"].strip() if sha["exit_code"] == 0 else None
    url = run_cmd(["git", "config", "--get", "remote.origin.url"], cwd=str(repo))
    info["remote"] = url["stdout"].strip() if url["exit_code"] == 0 else None
    return repo, info


def main(argv=None):
    load_dotenv()
    ap = argparse.ArgumentParser(prog="depexit", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repo")
    ap.add_argument("--out", default="capsule_out")
    ap.add_argument("--work", default=".depexit_work")
    ap.add_argument("--python", default="3.12")
    ap.add_argument("--only", default="", help="comma-separated dependency names to migrate")
    ap.add_argument("--max-fix", type=int, default=2, help="AI fix attempts per dependency")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--model", default=None, help="override GEMMA_MODEL")
    ap.add_argument("--no-ai", action="store_true", help="observed evidence only (no Gemma)")
    ap.add_argument("--ai-cache", action="store_true",
                    help="save Gemma answers to .depexit_ai_cache and re-use them on re-runs (development; flagged in the capsule)")
    ap.add_argument("--no-migrate", action="store_true", help="analyse + recommend, skip execution of replacements")
    args = ap.parse_args(argv)

    started = now_iso()
    work = Path(args.work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    for old in list(work.glob("mig_*")) + [work / "baseline", work / "baseline_pyproject", work / "combined"]:
        if old.is_dir():
            shutil.rmtree(old)   # fresh sandboxes every run: no stale evidence
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    repo, repo_info = resolve_repo(args.repo, work)
    log(f"Repository: {repo} @ {repo_info.get('commit')}")

    # ---------------- 1. OBSERVE: static inspection ---------------------------
    manifests = scanner.scan_manifests(repo)
    usage = scanner.scan_usage(repo)
    log(f"Manifests: {manifests['files']}; {len(manifests['declared'])} declarations; "
        f"{len(usage['by_module'])} third-party modules imported")

    req_files = [f for f in manifests["files"] if f.endswith(".txt")]
    install_files = list(req_files)
    probe_modules = sorted(set(usage["by_module"]) |
                           {d["name"].replace("-", "_") for d in manifests["declared"]})

    # ---------------- 2. VERIFY: baseline execution ---------------------------
    base_repo = executor.copy_repo(repo, work / "baseline" / "repo")
    if not install_files:
        # no requirements*.txt: derive one from pyproject so the same flow works
        deps = [d["raw"] for d in manifests["declared"] if d["group"] == "runtime"]
        (base_repo / ".depexit_requirements.txt").write_text("\n".join(deps) + "\n")
        install_files = [".depexit_requirements.txt"]
    baseline = executor.run_suite(base_repo, "baseline/original", install_files,
                                  probe_modules, args.python)

    variants = []
    pp_runtime = [d for d in manifests["declared"] if d["file"] == "pyproject.toml" and d["group"] == "runtime"]
    req_runtime = {(d["name"], d["specifier"]) for d in manifests["declared"]
                   if d["file"].endswith(".txt") and d["group"] == "runtime"}
    if pp_runtime and req_files and {(d["name"], d["specifier"]) for d in pp_runtime} != req_runtime:
        log("pyproject.toml and requirements disagree — running an alternate-manifest baseline")
        var_repo = executor.copy_repo(repo, work / "baseline_pyproject" / "repo")
        (var_repo / ".depexit_pyproject_reqs.txt").write_text("\n".join(d["raw"] for d in pp_runtime) + "\n")
        dev_files = [f for f in req_files if scanner._group_for(f) == "dev"]
        variants.append(executor.run_suite(var_repo, "pyproject.toml", [".depexit_pyproject_reqs.txt"] + dev_files,
                                           probe_modules, args.python))

    # ---------------- 3. OBSERVE: registry metadata + risk indicators ---------
    inv = risk.build_inventory(manifests, usage, baseline, variants)
    log(f"Querying PyPI for {len(inv)} dependencies")
    meta = pypi.fetch_many({n: e["installed_version"] for n, e in inv.items()})
    risk.compute_indicators(inv, manifests, meta, baseline, variants,
                            target_pythons=(args.python,) + (("3.13",) if args.python == "3.12" else ()))
    flagged = {n: e for n, e in inv.items() if e["indicators"]}
    log(f"Observed risk: {sum(e['observed_risk'] == 'high' for e in inv.values())} high, "
        f"{sum(e['observed_risk'] == 'medium' for e in inv.values())} medium, "
        f"{sum(e['observed_risk'] == 'low' for e in inv.values())} low")

    ctx = {"repo": repo, "work": work, "python": args.python, "baseline": baseline,
           "install_files": install_files, "probe_modules": probe_modules,
           "manifest_files": manifests["files"]}

    ai, ai_checks, migrations, combined, gemma = {}, {}, {}, None, None
    if not args.no_ai:
        import os
        from .gemma import Gemma
        if args.ai_cache:
            os.environ["DEPEXIT_AI_CACHE"] = str(Path(".depexit_ai_cache").resolve())
        gemma = Gemma(model=args.model)
        log(f"AI model: {gemma.model} via {gemma.label}")
        # ---------------- 4. AI: triage + grounding check ---------------------
        only = {canonicalize_name(x) for x in args.only.split(",") if x.strip()}
        to_triage = {n: e for n, e in flagged.items() if not only or n in only}
        if only:
            log(f"--only: AI analysis limited to {', '.join(sorted(to_triage)) or '(none matched)'}; "
                "other dependencies keep their observed evidence")
        ai = analysis.triage(gemma, to_triage, {
            "repo": repo_info.get("remote") or repo.name, "pythons": f"{args.python}/3.13",
            "manifest_files": ", ".join(manifests["files"]),
            "requires_python": manifests.get("requires_python")})
        for n in to_triage:
            if n in ai:
                ai_checks[n] = analysis.verify_ai_claims(inv[n], ai[n])

        # ---------------- 5. VERIFY: migrate + fix loop ------------------------
        todo = [n for n in sorted(flagged) if n in ai and (ai[n].get("action") or "keep") != "keep"
                and (not only or n in only)]
        if not args.no_migrate and todo:
            log(f"Migrating & verifying: {', '.join(todo)}")
            with ThreadPoolExecutor(args.workers) as ex:
                futs = {n: ex.submit(migrate.migrate_dependency, gemma, inv[n], ai[n], ctx, args.max_fix)
                        for n in todo}
                for n, f in futs.items():
                    try:
                        migrations[n] = f.result()
                    except Exception as exc:  # keep going; record the failure honestly
                        migrations[n] = {"dependency": n, "status": "error", "error": repr(exc)}
            combined = migrate.combined_migration(migrations, ctx)

    # ---------------- 6. Capsule ------------------------------------------------
    paths = capsule.write_all(out, {
        "tool": {"name": "depexit", "version": __version__},
        "started_at": started, "finished_at": now_iso(),
        "python_target": args.python, "host_python": sys.version.split()[0],
        "repository": repo_info, "manifests": manifests,
        "usage_parse_errors": usage["parse_errors"],
        "baseline": migrate._slim(baseline), "variants": [migrate._slim(v) for v in variants],
        "inventory": inv, "ai": ai, "ai_checks": ai_checks,
        "migrations": migrations, "combined": combined,
        "model": gemma.describe() if gemma else None,
        "ai_transcript": gemma.transcript if gemma else [],
    })
    log("Capsule written:")
    for p in paths:
        log(f"  {p}")


if __name__ == "__main__":
    main()
