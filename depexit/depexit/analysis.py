"""AI triage: Gemma reads the OBSERVED evidence and proposes risk levels,
replacements and migration plans. Its output is then checked against reality
(grounding check + replacement existence check) before anyone trusts it.
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor

from .gemma import Gemma
from .pypi import fetch_package
from .util import log

TRIAGE_PROMPT = """You are a senior Python maintainer preparing dependency migrations for the
repository below. Target runtime: Python {pythons}.

You are given OBSERVED EVIDENCE for each dependency, collected by static analysis, the PyPI
API and a real test run. Each indicator has an id. Base every judgement on that evidence and
on your general knowledge of the Python ecosystem. Cite indicator ids you rely on. Never cite
an id that is not listed. If you rely on general knowledge not in the evidence, say so in
"knowledge_claims".

For EACH dependency, decide:
- risk_level: "high" | "medium" | "low" | "none"
- action: one of
    "replace"  (swap for a different package or the standard library),
    "upgrade"  (move to a newer major/minor of the same package, with code changes if needed),
    "remove"   (unused / unnecessary, delete the declaration),
    "declare"  (used but undeclared: add an explicit requirement),
    "pin"      (add/repair version constraints only),
    "keep"     (no change needed)
- replacement: {{"package": "<pypi name>" or "stdlib:<module>" or null, "version_spec": "<pep440 spec>" or null}}
- migration_steps: ordered, concrete steps referencing the real files/lines shown
- suggested_tests: behaviours that must stay identical after migration
- expected_compatibility_gaps: API/behaviour differences you expect between old and new
- confidence: 0.0-1.0

Prefer the smallest safe change. Prefer standard-library replacements when they exist for the
target Python. Keep manifests (requirements*.txt and pyproject.toml) consistent with each other.

Return a JSON object: {{"dependencies": [ {{"name": ..., "risk_level": ..., "risk_summary": ...,
"cited_indicators": [...], "action": ..., "replacement": {{...}}, "rationale": ...,
"migration_steps": [...], "suggested_tests": [...], "expected_compatibility_gaps": [...],
"knowledge_claims": [...], "confidence": ...}} ]}}

REPOSITORY: {repo}
MANIFEST FILES: {manifest_files}
requires-python: {requires_python}

EVIDENCE:
{evidence}
"""


def _usage_digest(usage: list[dict], limit: int = 20) -> list[str]:
    seen, out = set(), []
    for u in usage:
        if u["kind"] == "reference":
            continue
        key = (u["file"], u["line"], u["kind"])
        if key in seen:
            continue
        seen.add(key)
        out.append(f"{u['file']}:{u['line']} [{u['kind']}] {u['code']}")
        if len(out) >= limit:
            break
    return out


def evidence_for(dep: dict) -> dict:
    p = dep.get("pypi", {})
    return {
        "name": dep["name"],
        "declared": [f"{d['file']}:{d['line']} '{d['raw']}' ({d['group']})" for d in dep["declared"]],
        "installed_version": dep["installed_version"],
        "latest_version": p.get("latest_version"),
        "latest_released": p.get("latest_released"),
        "pypi_summary": p.get("summary"),
        "import_names": dep["modules"],
        "usage": _usage_digest(dep["usage"]),
        "indicators": [{"id": i["id"], "kind": i["kind"], "severity": i["severity"],
                        "detail": i["detail"]} for i in dep["indicators"]],
    }


def triage(gemma: Gemma, inventory: dict, ctx: dict, chunk: int = 8, workers: int = 2) -> dict[str, dict]:
    names = sorted(inventory)
    if not names:
        return {}
    chunks = [names[i:i + chunk] for i in range(0, len(names), chunk)]

    def run(group):
        ev = json.dumps([evidence_for(inventory[n]) for n in group], indent=1)
        prompt = TRIAGE_PROMPT.format(evidence=ev, **ctx)
        log(f"Gemma triage: {', '.join(group)}")
        res = gemma.generate_json(prompt, purpose=f"triage:{','.join(group)}")
        items = res.get("dependencies", res) if isinstance(res, dict) else res
        return {str(it.get("name", "")).lower(): it for it in items if isinstance(it, dict)}

    out = {}
    if getattr(gemma, "provider", "") == "ollama":
        workers = 1   # a local model answers one request at a time anyway
    with ThreadPoolExecutor(workers) as ex:
        for part in ex.map(run, chunks):
            out.update(part)
    missing = [n for n in names if n not in out]
    if missing:
        log(f"Gemma skipped {missing}; re-asking")
        out.update(run(missing))
    return out


def verify_ai_claims(dep: dict, ai: dict) -> dict:
    """Check the AI output against observed facts. Result is OBSERVED."""
    valid_ids = {i["id"] for i in dep["indicators"]}
    cited = ai.get("cited_indicators") or []
    checks = {
        "cited_indicator_ids_valid": [c for c in cited if c in valid_ids],
        "cited_indicator_ids_invalid": [c for c in cited if c not in valid_ids],
        "uncited_high_indicators": [i["id"] for i in dep["indicators"]
                                    if i["severity"] == "high" and i["id"] not in cited],
    }
    rep = (ai.get("replacement") or {}).get("package")
    if rep and rep.startswith("stdlib:"):
        mod = rep.split(":", 1)[1].split(".")[0]
        checks["replacement_exists"] = mod in sys.stdlib_module_names
        checks["replacement_check"] = f"'{mod}' {'is' if checks['replacement_exists'] else 'is NOT'} a standard-library module of Python {sys.version_info.major}.{sys.version_info.minor}"
    elif rep:
        meta = fetch_package(rep, None)
        checks["replacement_exists"] = bool(meta.get("found"))
        checks["replacement_check"] = (
            f"PyPI: {rep} latest {meta.get('latest_version')} released {meta.get('latest_released')}"
            if meta.get("found") else f"'{rep}' was NOT found on PyPI")
        checks["replacement_pypi"] = {k: meta.get(k) for k in
                                      ("latest_version", "latest_released", "last_release_days",
                                       "requires_python_latest", "source_url")}
    checks["grounded"] = not checks["cited_indicator_ids_invalid"] and checks.get("replacement_exists", True)
    return checks
