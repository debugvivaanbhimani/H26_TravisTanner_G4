"""Rebuild report.html from an existing capsule folder (no analysis, no AI calls).

usage: python -m depexit.rerender capsule_folder
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .report_html import render_html


def main(argv=None):
    args = argv if argv is not None else sys.argv[1:]
    folder = Path(args[0] if args else "capsule")
    doc = json.loads((folder / "capsule.json").read_text(encoding="utf-8"))
    patches = {p.stem: p.read_text(encoding="utf-8")
               for p in (folder / "patches").glob("*.patch") if p.stem != "combined"}
    (folder / "report.html").write_text(render_html({**doc, "__patches": patches}), encoding="utf-8")
    print(f"Rebuilt {folder / 'report.html'}")


if __name__ == "__main__":
    main()
