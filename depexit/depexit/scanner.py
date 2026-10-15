"""Static, deterministic repository inspection. Everything here is OBSERVED.

* Parses every dependency manifest (requirements*.txt, pyproject.toml, setup.cfg).
* Walks the Python AST of every source file to find exactly where and how each
  third-party module is used: imports, attribute access, calls, private-API use
  and monkey-patching.

No AI is involved in this module.
"""
from __future__ import annotations

import ast
import configparser
import os
import re
import sys
import tomllib
from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

SKIP_DIRS = {".git", ".venv", "venv", "env", "build", "dist", "node_modules",
             "__pycache__", ".tox", ".nox", ".mypy_cache", ".pytest_cache",
             "site-packages", ".eggs"}
STDLIB = set(sys.stdlib_module_names)


# --------------------------------------------------------------------------- #
# Manifests
# --------------------------------------------------------------------------- #

def _group_for(filename: str) -> str:
    low = filename.lower()
    if any(k in low for k in ("dev", "test", "lint", "doc")):
        return "dev"
    return "runtime"


def _parse_req_line(raw: str):
    try:
        return Requirement(raw)
    except InvalidRequirement:
        return None


def find_requirement_files(repo: Path) -> list[Path]:
    files = sorted(repo.glob("requirements*.txt")) + sorted(repo.glob("requirements/*.txt"))
    return [f for f in files if f.is_file()]


def parse_requirements_file(path: Path, repo: Path) -> tuple[list[dict], list[dict]]:
    declared, commented = [], []
    rel = str(path.relative_to(repo))
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        text = line.strip()
        if not text:
            continue
        if text.startswith("#"):
            body = text.lstrip("#").strip()
            req = _parse_req_line(body) if re.match(r"^[A-Za-z0-9_.\-]+\s*([=<>!~]=|$)", body) else None
            if req:
                commented.append({"name": canonicalize_name(req.name), "raw": body,
                                  "file": rel, "line": lineno})
            continue
        if text.startswith("-"):
            continue  # pip options / nested -r files are listed separately
        text = text.split(" #")[0].strip()
        req = _parse_req_line(text)
        if not req:
            continue
        declared.append({
            "name": canonicalize_name(req.name),
            "raw": text,
            "specifier": str(req.specifier),
            "pinned": any(s.operator in ("==", "===") for s in req.specifier),
            "file": rel,
            "line": lineno,
            "group": _group_for(path.name),
        })
    return declared, commented


def _line_of(text: str, needle: str) -> int | None:
    for i, line in enumerate(text.splitlines(), 1):
        if needle in line:
            return i
    return None


def parse_pyproject(path: Path, repo: Path) -> list[dict]:
    raw_text = path.read_text(encoding="utf-8")
    data = tomllib.loads(raw_text)
    rel = str(path.relative_to(repo))
    out = []

    def add(items, group):
        for item in items or []:
            req = _parse_req_line(item)
            if not req:
                continue
            out.append({
                "name": canonicalize_name(req.name),
                "raw": item,
                "specifier": str(req.specifier),
                "pinned": any(s.operator in ("==", "===") for s in req.specifier),
                "file": rel,
                "line": _line_of(raw_text, f'"{item}"'),
                "group": group,
            })

    project = data.get("project", {})
    add(project.get("dependencies"), "runtime")
    for extra, items in (project.get("optional-dependencies") or {}).items():
        add(items, f"extra:{extra}")
    add(data.get("build-system", {}).get("requires"), "build")
    return out


def parse_setup_cfg(path: Path, repo: Path) -> list[dict]:
    cfg = configparser.ConfigParser()
    cfg.read(path, encoding="utf-8")
    rel = str(path.relative_to(repo))
    out = []
    if cfg.has_option("options", "install_requires"):
        for item in cfg.get("options", "install_requires").splitlines():
            item = item.strip()
            req = _parse_req_line(item) if item else None
            if req:
                out.append({"name": canonicalize_name(req.name), "raw": item,
                            "specifier": str(req.specifier),
                            "pinned": any(s.operator == "==" for s in req.specifier),
                            "file": rel, "line": None, "group": "runtime"})
    return out


def scan_manifests(repo: Path) -> dict:
    declared, commented, files = [], [], []
    for f in find_requirement_files(repo):
        d, c = parse_requirements_file(f, repo)
        declared += d
        commented += c
        files.append(str(f.relative_to(repo)))
    pp = repo / "pyproject.toml"
    if pp.exists():
        declared += parse_pyproject(pp, repo)
        files.append("pyproject.toml")
    sc = repo / "setup.cfg"
    if sc.exists():
        declared += parse_setup_cfg(sc, repo)
        files.append("setup.cfg")
    py_req = None
    if pp.exists():
        py_req = tomllib.loads(pp.read_text(encoding="utf-8")).get("project", {}).get("requires-python")
    return {"files": files, "declared": declared, "commented_out": commented,
            "requires_python": py_req,
            "has_setup_py": (repo / "setup.py").exists()}


# --------------------------------------------------------------------------- #
# Source usage (AST)
# --------------------------------------------------------------------------- #

def iter_py_files(repo: Path):
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for f in files:
            if f.endswith(".py"):
                yield Path(root) / f


def local_top_modules(repo: Path) -> set[str]:
    names = set()
    for p in repo.iterdir():
        if p.is_dir() and (p / "__init__.py").exists():
            names.add(p.name)
        elif p.suffix == ".py":
            names.add(p.stem)
    for sub in ("src",):
        sp = repo / sub
        if sp.is_dir():
            for p in sp.iterdir():
                if p.is_dir():
                    names.add(p.name)
    names.update({"tests", "test", "conftest"})
    return names


def _dotted(node) -> list[str] | None:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return list(reversed(parts))
    return None


def _is_private(path: str) -> bool:
    return any(seg.startswith("_") and not (seg.startswith("__") and seg.endswith("__"))
               for seg in path.split("."))


class _UsageVisitor(ast.NodeVisitor):
    def __init__(self, rel: str, lines: list[str], local: set[str]):
        self.rel, self.lines, self.local = rel, lines, local
        self.bindings: dict[str, str] = {}   # local name -> dotted path
        self.records: list[dict] = []
        self._seen: set = set()

    def _code(self, lineno):
        return self.lines[lineno - 1].strip() if 0 < lineno <= len(self.lines) else ""

    def _kind_of_module(self, top: str) -> str:
        if top in STDLIB:
            return "stdlib"
        if top in self.local:
            return "local"
        return "third_party"

    def _add(self, top, kind, symbol, lineno):
        key = (top, kind, symbol, lineno)
        if key in self._seen:
            return
        self._seen.add(key)
        self.records.append({"module": top, "file": self.rel, "line": lineno,
                             "kind": kind, "symbol": symbol,
                             "code": self._code(lineno)})

    def visit_Import(self, node):
        for alias in node.names:
            top = alias.name.split(".")[0]
            if self._kind_of_module(top) != "third_party":
                continue
            bound = alias.asname or top
            self.bindings[bound] = alias.name if alias.asname else top
            self._add(top, "import", alias.name, node.lineno)
            if _is_private(alias.name):
                self._add(top, "private_api", alias.name, node.lineno)

    def visit_ImportFrom(self, node):
        if node.level or not node.module:
            return
        top = node.module.split(".")[0]
        if self._kind_of_module(top) != "third_party":
            return
        for alias in node.names:
            full = f"{node.module}.{alias.name}"
            self.bindings[alias.asname or alias.name] = full
            self._add(top, "import", full, node.lineno)
            if _is_private(full):
                self._add(top, "private_api", full, node.lineno)

    def _resolve(self, node) -> str | None:
        parts = _dotted(node)
        if not parts or parts[0] not in self.bindings:
            return None
        return ".".join([self.bindings[parts[0]]] + parts[1:])

    def visit_Attribute(self, node):
        path = self._resolve(node)
        if path and isinstance(node.ctx, ast.Load):
            top = path.split(".")[0]
            self._add(top, "attribute", path, node.lineno)
            if _is_private(path):
                self._add(top, "private_api", path, node.lineno)
        self.generic_visit(node)

    def visit_Call(self, node):
        path = self._resolve(node.func)
        if path:
            self._add(path.split(".")[0], "call", path, node.lineno)
        self.generic_visit(node)

    def _check_store(self, target, lineno):
        if isinstance(target, ast.Attribute):
            path = self._resolve(target)
            if path:
                self._add(path.split(".")[0], "monkeypatch", path, lineno)

    def visit_Assign(self, node):
        for t in node.targets:
            self._check_store(t, node.lineno)
        self.generic_visit(node)

    def visit_AugAssign(self, node):
        self._check_store(node.target, node.lineno)
        self.generic_visit(node)

    def visit_Name(self, node):
        # bare use of a from-imported name, e.g. user_cache_dir("x")
        if isinstance(node.ctx, ast.Load) and node.id in self.bindings:
            path = self.bindings[node.id]
            if "." in path:
                self._add(path.split(".")[0], "reference", path, node.lineno)


def scan_usage(repo: Path) -> dict:
    local = local_top_modules(repo)
    by_module: dict[str, list[dict]] = {}
    parse_errors = []
    for f in iter_py_files(repo):
        rel = str(f.relative_to(repo))
        src = f.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(src)
        except SyntaxError as exc:
            parse_errors.append({"file": rel, "error": str(exc)})
            continue
        v = _UsageVisitor(rel, src.splitlines(), local)
        v.visit(tree)
        for r in v.records:
            by_module.setdefault(r["module"], []).append(r)
    for recs in by_module.values():
        recs.sort(key=lambda r: (r["file"], r["line"]))
    return {"by_module": by_module, "parse_errors": parse_errors,
            "local_modules": sorted(local)}


def read_files(repo: Path, rel_paths) -> dict[str, str]:
    out = {}
    for rel in sorted(set(rel_paths)):
        p = repo / rel
        if p.is_file():
            out[rel] = p.read_text(encoding="utf-8", errors="replace")
    return out
