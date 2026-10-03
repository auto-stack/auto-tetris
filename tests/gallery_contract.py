#!/usr/bin/env python3
"""Audit the static desktop/gallery contract for Plan 005.

The current gallery generator scans one ``examples/ui`` directory.  Tetris is
registered as a product app under ``apps/036-tetris`` and therefore needs an
explicit 05-games gallery registration before that acceptance row can pass.
This audit makes the gap reproducible instead of treating a manifest entry as
gallery evidence.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


APP_ROOT = Path(__file__).resolve().parents[1]
OS_ROOT = APP_ROOT.parents[1]
MANIFEST = OS_ROOT / "apps.manifest"


def auto_lang_root() -> Path:
    configured = os.environ.get("AUTO_LANG_ROOT")
    if configured:
        return Path(configured)
    # ``OS_ROOT.parents[2]`` is outside the Windows drive for the normal
    # auto-os checkout and raises IndexError.  Keep resolution bounded to the
    # documented sibling and explicit fallback paths.
    for candidate in (OS_ROOT.parent / "auto-lang", Path("D:/autostack/auto-lang")):
        if candidate.is_dir():
            return candidate
    return Path("D:/autostack/auto-lang")


AUTO_LANG_ROOT = auto_lang_root()


def gallery_root() -> Path:
    configured = os.environ.get("AUTO_GALLERY_APPS")
    if configured:
        return Path(configured)
    sibling = AUTO_LANG_ROOT / "examples" / "ui"
    if sibling.is_dir():
        return sibling
    return OS_ROOT / "examples" / "ui"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="emit machine-readable findings")
    args = parser.parse_args()

    findings: list[dict[str, str]] = []
    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        findings.append({"id": "manifest", "status": "blocked", "detail": str(exc)})
        manifest = {"apps": []}

    entry = next((item for item in manifest.get("apps", []) if item.get("id") == "tetris"), None)
    findings.append(
        {
            "id": "manifest.tetris",
            "status": "supported" if entry else "blocked",
            "detail": "apps.manifest registers tetris" if entry else "apps.manifest has no tetris entry",
        }
    )

    pac = APP_ROOT / "pac.at"
    pac_text = pac.read_text(encoding="utf-8") if pac.is_file() else ""
    required = ('category: "game"', 'desktop: "true"')
    findings.append(
        {
            "id": "pac.desktop-game",
            "status": "supported" if all(token in pac_text for token in required) else "blocked",
            "detail": "pac.at declares category=game and desktop=true" if all(token in pac_text for token in required) else "pac.at is missing game/desktop metadata",
        }
    )

    root = gallery_root()
    has_tetris = (root / "036-tetris").is_dir() or (root / "tetris").is_dir()
    findings.append(
        {
            "id": "gallery.tetris",
            "status": "supported" if has_tetris else "blocked",
            "detail": f"gallery scan root contains tetris ({root})" if has_tetris else f"tetris is outside gallery scan root ({root}); product app is {APP_ROOT}",
        }
    )

    # 05-games is a Plan 005 acceptance category.  Keep this check explicit so
    # a future generator change can close it with a concrete source artifact.
    generator = AUTO_LANG_ROOT / "crates" / "auto-man" / "src" / "vue.rs"
    generator_text = generator.read_text(encoding="utf-8") if generator.is_file() else ""
    has_category = "05-games" in generator_text
    findings.append(
        {
            "id": "gallery.05-games",
            "status": "supported" if has_category else "blocked",
            "detail": "gallery generator declares 05-games" if has_category else "no 05-games category in current gallery generator; it falls back to 04-systems",
        }
    )

    if args.json:
        print(json.dumps({"root": str(root), "findings": findings}, ensure_ascii=False, indent=2))
    else:
        for finding in findings:
            print(f"{finding['id']}: {finding['status']} — {finding['detail']}")
    return 0 if all(item["status"] == "supported" for item in findings) else 2


if __name__ == "__main__":
    raise SystemExit(main())
