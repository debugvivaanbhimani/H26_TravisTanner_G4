"""Deterministic risk indicators. Combines manifest data, source usage, live PyPI
metadata and the baseline execution into one inventory. Every indicator carries
an id, so the AI's later claims can be checked against real evidence.
"""
from __future__ import annotations

from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name

from .pypi import versions_satisfying

STALE_DAYS = 3 * 365
OLD_PIN_DAYS = 3 * 365
TEST_TOOLS = {"pytest", "nose", "nose2", "tox", "coverage", "pytest-cov", "mock", "flake8",
              "black", "ruff", "mypy", "pylint", "isort"}


def module_dist_map(pkg_dists: dict[str, list[str]]) -> tuple[dict, dict]:
    mod_to_dist, dist_to_mods = {}, {}
    for mod, dists in pkg_dists.items():
        for d in dists:
            cd = canonicalize_name(d)
            mod_to_dist.setdefault(mod, cd)
            dist_to_mods.setdefault(cd, set()).add(mod)
    return mod_to_dist, {k: sorted(v) for k, v in dist_to_mods.items()}


def build_inventory(manifests: dict, usage: dict, baseline: dict,
                    variants: list[dict]) -> dict[str, dict]:
    mod_to_dist, dist_to_mods = module_dist_map(baseline.get("packages_distributions", {}))
    inv: dict[str, dict] = {}

    def entry(name):
        return inv.setdefault(name, {"name": name, "declared": [], "modules": [],
                                     "usage": [], "installed_version": None,
                                     "indicators": []})

    for d in manifests["declared"]:
        entry(d["name"])["declared"].append(d)

    for mod, recs in usage["by_module"].items():
        dist = mod_to_dist.get(mod, canonicalize_name(mod))
        e = entry(dist)
        if mod not in e["modules"]:
            e["modules"].append(mod)
        e["usage"].extend(recs)

    freeze = {canonicalize_name(k): v for k, v in baseline.get("freeze", {}).items()}
    for name, e in inv.items():
        e["installed_version"] = freeze.get(name)
        if not e["modules"]:
            e["modules"] = dist_to_mods.get(name, [])
    return inv


def _add(e, kind, severity, detail, source):
    e["indicators"].append({"id": f"{e['name']}:{kind}:{len(e['indicators']) + 1}",
                            "kind": kind, "severity": severity, "detail": detail,
                            "source": source})


def _supports(py: str, requires_python: str | None, classifiers: list[str]) -> bool | None:
    if requires_python:
        try:
            return py in SpecifierSet(requires_python) or f"{py}.0" in SpecifierSet(requires_python)
        except Exception:
            return None
    if classifiers:
        return None if py in classifiers else False
    return None


def compute_indicators(inv: dict[str, dict], manifests: dict, pypi: dict[str, dict],
                       baseline: dict, variants: list[dict], target_pythons=("3.12", "3.13")):
    commented = {c["name"]: c for c in manifests.get("commented_out", [])}
    for name, e in inv.items():
        meta = pypi.get(name, {})
        e["pypi"] = {k: v for k, v in meta.items() if k != "all_versions"}
        decl = e["declared"]
        usage_kinds = {u["kind"] for u in e["usage"]}
        src_files = sorted({u["file"] for u in e["usage"]})
        runtime_use = [f for f in src_files if not f.startswith(("tests/", "test/"))]

        # --- manifest-level --------------------------------------------------
        if not decl and e["usage"]:
            _add(e, "undeclared_dependency", "high",
                 f"Imported in {', '.join(src_files)} but not declared in any manifest; "
                 f"only present transitively (installed {e['installed_version'] or 'NOT installed'}).",
                 "manifests+ast")
        if decl and not e["usage"] and name not in TEST_TOOLS:
            mods = ", ".join(e["modules"]) or "unknown module"
            _add(e, "declared_but_unused", "low",
                 f"Declared in {', '.join(sorted({d['file'] for d in decl}))} but no source file imports it ({mods}).",
                 "manifests+ast")
        unpinned = [d for d in decl if not d["specifier"]]
        if unpinned:
            _add(e, "unpinned", "low",
                 f"No version constraint in {', '.join(d['file'] for d in unpinned)} — builds are not reproducible.",
                 "manifests")
        specs = {(d["file"], d["specifier"]) for d in decl if d["group"] in ("runtime", "dev")}
        if len({s for _, s in specs}) > 1 and meta.get("all_versions"):
            sets = [versions_satisfying(meta["all_versions"], s) for _, s in specs]
            common = set.intersection(*sets) if sets else set()
            desc = "; ".join(f"{f}: '{s or '(any)'}'" for f, s in sorted(specs))
            if not common:
                _add(e, "manifest_conflict", "high",
                     f"Manifests disagree and NO released version satisfies all of them — {desc}.",
                     "manifests+pypi")
            else:
                _add(e, "manifest_mismatch", "medium",
                     f"Manifests declare different constraints — {desc}.", "manifests")
        if name in commented:
            _add(e, "commented_out_requirement", "low",
                 f"Commented-out requirement '{commented[name]['raw']}' in {commented[name]['file']}:{commented[name]['line']}.",
                 "manifests")

        # --- source-level ----------------------------------------------------
        if "private_api" in usage_kinds:
            locs = [f"{u['file']}:{u['line']} ({u['symbol']})" for u in e["usage"] if u["kind"] == "private_api"]
            _add(e, "private_api_usage", "high",
                 f"Uses non-public API that can change without notice: {'; '.join(sorted(set(locs)))}.", "ast")
        if "monkeypatch" in usage_kinds:
            locs = [f"{u['file']}:{u['line']} ({u['symbol']})" for u in e["usage"] if u["kind"] == "monkeypatch"]
            _add(e, "monkeypatching", "high",
                 f"Repository overwrites library internals at runtime: {'; '.join(sorted(set(locs)))}.", "ast")

        # --- registry-level --------------------------------------------------
        if meta.get("found") is False:
            _add(e, "not_on_pypi", "medium", "Package not found on PyPI.", "pypi")
        inst = meta.get("installed") or {}
        if meta.get("found"):
            lr = meta.get("last_release_days")
            if lr is not None and lr > STALE_DAYS:
                _add(e, "no_recent_releases", "high" if lr > 2 * STALE_DAYS else "medium",
                     f"Last release on PyPI was {lr} days ago (latest {meta.get('latest_version')} on {meta.get('latest_released')}).",
                     "pypi")
            if any("Inactive" in c for c in meta.get("dev_status", [])):
                _add(e, "marked_inactive", "high", f"PyPI classifier: {meta['dev_status']}.", "pypi")
            gh = meta.get("github") or {}
            if gh.get("archived"):
                _add(e, "repo_archived", "high", f"Source repository {gh['repo']} is archived on GitHub.", "github")
            summ = (meta.get("summary") or "").lower()
            if any(w in summ for w in ("deprecated", "unmaintained", "no longer maintained", "obsolete")):
                _add(e, "self_described_deprecated", "high", f"PyPI summary: \"{meta.get('summary')}\".", "pypi")
            if inst:
                if inst.get("age_days") and inst["age_days"] > OLD_PIN_DAYS and inst.get("releases_behind"):
                    _add(e, "old_pinned_version", "medium",
                         f"Installed {inst['version']} was released {inst['released']} ({inst['age_days']} days ago); "
                         f"{inst['releases_behind']} newer releases exist, latest {meta.get('latest_version')}.", "pypi")
                elif inst.get("major_behind", 0) >= 1:
                    _add(e, "major_versions_behind", "medium",
                         f"Installed {inst['version']} is {inst['major_behind']} major version(s) behind latest {meta.get('latest_version')}.",
                         "pypi")
                if inst.get("yanked"):
                    _add(e, "yanked_version", "high", f"Installed version {inst['version']} is yanked on PyPI.", "pypi")
                for py in target_pythons:
                    sup = _supports(py, inst.get("requires_python"), inst.get("python_classifiers", []))
                    if sup is False:
                        _add(e, "python_support_undeclared", "medium",
                             f"Installed {inst['version']} does not declare support for Python {py} "
                             f"(requires_python={inst.get('requires_python')!r}, classifiers={inst.get('python_classifiers')}).",
                             "pypi")
                        break

        # --- execution-level (baseline) --------------------------------------
        for mod in e["modules"]:
            pr = baseline.get("import_probe", {}).get(mod)
            if pr and not pr["ok"]:
                _add(e, "import_fails", "high",
                     f"`import {mod}` fails in a clean Python {baseline['python']} env: {pr['error']}", "execution:baseline")
            if pr:
                dep = [w for w in pr.get("warnings", []) if "Deprecat" in w]
                if dep:
                    _add(e, "deprecation_warning_on_import", "medium",
                         f"`import {mod}` emits: {dep[0][:300]}", "execution:baseline")
            fails = baseline.get("failure_modules", {}).get(mod)
            if fails:
                _add(e, "breaks_tests", "high",
                     f"{len(fails)} baseline test(s) fail with a traceback inside `{mod}`: {', '.join(fails)}.",
                     "execution:baseline")
            warn_hits = [w for w in baseline.get("warnings", []) if f"/{mod}/" in w or f" {mod} " in w
                         or (runtime_use and any(f in w for f in runtime_use) and mod in w)]
            if warn_hits:
                _add(e, "deprecation_warning_in_tests", "medium",
                     f"Test run warning: {warn_hits[0][:300]}", "execution:baseline")
        for var in variants:
            for mod in e["modules"]:
                base_fails = set(baseline.get("failure_modules", {}).get(mod, []))
                fails = [f for f in var.get("failure_modules", {}).get(mod, []) if f not in base_fails]
                if fails:
                    _add(e, "breaks_under_alternate_manifest", "high",
                         f"When installed from {var['label']}, {len(fails)} test(s) fail inside `{mod}`: {', '.join(fails)}.",
                         f"execution:{var['label']}")
            vfree = {canonicalize_name(k): v for k, v in var.get("freeze", {}).items()}
            if name in vfree and e["installed_version"] and vfree[name] != e["installed_version"]:
                _add(e, "manifest_resolves_differently", "medium",
                     f"requirements files install {e['installed_version']}, {var['label']} installs {vfree[name]}.",
                     f"execution:{var['label']}")

        sev = [i["severity"] for i in e["indicators"]]
        e["observed_risk"] = ("high" if "high" in sev else "medium" if "medium" in sev
                              else "low" if sev else "none")
    return inv
