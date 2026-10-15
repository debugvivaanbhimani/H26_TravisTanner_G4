"""Live package metadata from the PyPI JSON API (and optionally GitHub). OBSERVED."""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests
from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version

PYPI = "https://pypi.org/pypi/{name}/json"
PYPI_VER = "https://pypi.org/pypi/{name}/{version}/json"
_session = requests.Session()
_session.headers["User-Agent"] = "depexit/0.1 (dependency exit capsule tool)"


def _get(url: str):
    try:
        r = _session.get(url, timeout=20)
        if r.status_code == 200:
            return r.json()
    except requests.RequestException:
        pass
    return None


def _parse_dt(s: str | None):
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _days_since(dt) -> int | None:
    if not dt:
        return None
    return (datetime.now(timezone.utc) - dt).days


def _release_dates(data: dict) -> dict[str, datetime]:
    out = {}
    for ver, files in (data.get("releases") or {}).items():
        times = [_parse_dt(f.get("upload_time_iso_8601")) for f in files]
        times = [t for t in times if t]
        if times:
            out[ver] = min(times)
    return out


def _versions(data: dict) -> list[Version]:
    vs = []
    for v, files in (data.get("releases") or {}).items():
        if not files:
            continue
        try:
            vs.append(Version(v))
        except InvalidVersion:
            pass
    return sorted(vs)


def github_repo_status(project_urls: dict) -> dict | None:
    """Archived / last-push info for the project's GitHub repo, if reachable."""
    if os.environ.get("DEPEXIT_NO_GITHUB"):
        return None
    url = None
    for v in (project_urls or {}).values():
        if v and "github.com/" in v:
            url = v
            break
    if not url:
        return None
    parts = url.split("github.com/")[1].strip("/").split("/")
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1].removesuffix(".git")
    headers = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    try:
        r = _session.get(f"https://api.github.com/repos/{owner}/{repo}", headers=headers, timeout=15)
        if r.status_code != 200:
            return {"repo": f"{owner}/{repo}", "error": f"HTTP {r.status_code}"}
        j = r.json()
        return {"repo": f"{owner}/{repo}", "archived": j.get("archived"),
                "pushed_at": j.get("pushed_at"),
                "days_since_push": _days_since(_parse_dt(j.get("pushed_at"))),
                "open_issues": j.get("open_issues_count"),
                "source_url": f"https://github.com/{owner}/{repo}"}
    except requests.RequestException as exc:
        return {"repo": f"{owner}/{repo}", "error": str(exc)}


def fetch_package(name: str, installed_version: str | None) -> dict:
    data = _get(PYPI.format(name=name))
    if not data:
        return {"name": name, "found": False, "source_url": PYPI.format(name=name)}
    info = data.get("info", {})
    dates = _release_dates(data)
    versions = _versions(data)
    stable = [v for v in versions if not v.is_prerelease]
    latest = str(stable[-1]) if stable else info.get("version")
    latest_dt = dates.get(latest)
    last_any_dt = max(dates.values()) if dates else None

    inst = {}
    if installed_version:
        vdata = _get(PYPI_VER.format(name=name, version=installed_version))
        vinfo = (vdata or {}).get("info", {})
        inst_dt = dates.get(installed_version)
        yanked = any(f.get("yanked") for f in (data.get("releases") or {}).get(installed_version, []))
        inst = {
            "version": installed_version,
            "released": inst_dt.date().isoformat() if inst_dt else None,
            "age_days": _days_since(inst_dt),
            "requires_python": vinfo.get("requires_python"),
            "python_classifiers": sorted(c.split("::")[-1].strip() for c in vinfo.get("classifiers", [])
                                         if c.startswith("Programming Language :: Python :: 3.")),
            "yanked": yanked,
        }
        try:
            iv = Version(installed_version)
            inst["releases_behind"] = len([v for v in stable if v > iv])
            inst["major_behind"] = (stable[-1].major - iv.major) if stable else 0
        except InvalidVersion:
            pass

    return {
        "name": name,
        "found": True,
        "summary": info.get("summary"),
        "latest_version": latest,
        "latest_released": latest_dt.date().isoformat() if latest_dt else None,
        "last_release_days": _days_since(last_any_dt),
        "dev_status": [c for c in info.get("classifiers", []) if c.startswith("Development Status")],
        "requires_python_latest": info.get("requires_python"),
        "installed": inst,
        "all_versions": [str(v) for v in versions],
        "project_urls": info.get("project_urls") or {},
        "github": github_repo_status(info.get("project_urls") or {}),
        "source_url": f"https://pypi.org/project/{name}/",
    }


def fetch_many(names_versions: dict[str, str | None], workers: int = 8) -> dict[str, dict]:
    with ThreadPoolExecutor(workers) as ex:
        futs = {n: ex.submit(fetch_package, n, v) for n, v in names_versions.items()}
        return {n: f.result() for n, f in futs.items()}


def versions_satisfying(all_versions: list[str], spec: str) -> set[str]:
    ss = SpecifierSet(spec or "")
    out = set()
    for v in all_versions:
        try:
            if Version(v) in ss:
                out.add(v)
        except InvalidVersion:
            pass
    return out
