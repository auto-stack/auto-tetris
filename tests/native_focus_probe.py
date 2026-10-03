#!/usr/bin/env python3
"""Repeatable physical-input probe for Plan 005's focus/hold gate.

The probe uses the real Windows user32 window and AutoUI MCP only for state
inspection. It deliberately exits with status 2 when focus loss does not
pause the app, keeping that missing lifecycle capability visible to review.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import time
import urllib.request
from pathlib import Path


HERE = Path(__file__).resolve().parent
DRIVER_PATH = HERE / "native_physical.py"
spec = importlib.util.spec_from_file_location("native_physical", DRIVER_PATH)
if spec is None or spec.loader is None:  # pragma: no cover
    raise RuntimeError(f"cannot load {DRIVER_PATH}")
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


def mcp_call(url: str, name: str, arguments: dict | None = None) -> str:
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments or {}},
        "id": 1,
    }
    request = urllib.request.Request(
        url, json.dumps(payload).encode("utf-8"), {"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        result = json.load(response)
    return "\n".join(item.get("text", "") for item in result.get("result", {}).get("content", []))


def state(url: str) -> dict[str, object]:
    raw = mcp_call(url, "autoui_state")
    values: dict[str, object] = {}
    for key in ("phase", "px", "py", "rotation", "score", "seed"):
        match = re.search(rf"\n  {key}: (.+?) \(", raw)
        if match:
            value: object = match.group(1).strip().strip('"')
            try:
                value = int(value)
            except ValueError:
                pass
            values[key] = value
    return values


def start_if_ready(url: str, current: dict[str, object]) -> dict[str, object]:
    """Start a fresh VM session through the rendered start button when needed."""

    if current.get("phase") != "ready":
        return current
    snapshot = mcp_call(url, "autoui_snapshot")
    match = re.search(r'button #(\S+) "开始游戏"', snapshot)
    if not match:
        raise RuntimeError("ready VM state has no rendered 开始游戏 button")
    mcp_call(
        url,
        "autoui_action",
        {"element_id": match.group(1), "action": "press"},
    )
    time.sleep(0.2)
    return state(url)


def run(args: argparse.Namespace) -> int:
    if sys.platform != "win32":
        print("BLOCKED: native focus probe requires Windows", file=sys.stderr)
        return 2
    matches = driver.window_inventory(args.title)
    visible = [item for item in matches if item["visible"]]
    if not visible:
        print(f"BLOCKED: no visible window matching {args.title!r}", file=sys.stderr)
        return 2
    target = int(visible[0]["hwnd"])
    if not driver.focus_window(target):
        print(f"BLOCKED: cannot focus hwnd {target}", file=sys.stderr)
        return 2
    time.sleep(0.2)
    before = state(args.mcp_url)
    before = start_if_ready(args.mcp_url, before)
    if before.get("phase") == "paused":
        mcp_call(args.mcp_url, "autoui_keyboard", {"key": "P"})
        time.sleep(0.25)
        before = state(args.mcp_url)

    driver.send_key(args.key, True)
    time.sleep(args.initial_delay_ms / 1000)
    repeats = 0
    deadline = time.monotonic() + args.hold_ms / 1000
    while time.monotonic() < deadline:
        driver.send_key(args.key, True)
        repeats += 1
        time.sleep(args.repeat_interval_ms / 1000)
    driver.send_key(args.key, False)
    time.sleep(0.2)
    after_release = state(args.mcp_url)

    other = driver.other_visible_window(target)
    blurred = bool(other and driver.focus_window(other))
    if blurred:
        time.sleep(args.blur_wait_ms / 1000)
    after_blur = state(args.mcp_url)

    driver.focus_window(target)
    time.sleep(0.15)
    control_before = state(args.mcp_url)
    if control_before.get("phase") == "playing":
        mcp_call(args.mcp_url, "autoui_keyboard", {"key": "P"})
        time.sleep(0.25)
    control_after = state(args.mcp_url)

    evidence = {
        "window": matches,
        "before": before,
        "hold": {
            "key": args.key,
            "key_down_packets": repeats + 1,
            "repeat_packets": repeats,
            "keyup": True,
            "duration_ms": args.initial_delay_ms + args.hold_ms,
        },
        "after_release": after_release,
        "blur": {
            "performed": blurred,
            "other_hwnd": other,
            "after": after_blur,
            "expected_phase": "paused",
        },
        "control_pause": {"before": control_before, "after": control_after},
    }
    if args.evidence:
        path = Path(args.evidence)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    if not blurred:
        print("BLOCKED: no second visible window available for focus-loss test", file=sys.stderr)
        return 2
    if after_blur.get("phase") != "paused":
        print(
            f"BLOCKED: focus loss left phase={after_blur.get('phase')!r}; expected 'paused'",
            file=sys.stderr,
        )
        return 2
    print("Native focus/hold probe OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", default="俄罗斯方块")
    parser.add_argument("--mcp-url", required=True)
    parser.add_argument("--key", default="ArrowLeft")
    parser.add_argument("--initial-delay-ms", type=int, default=150)
    parser.add_argument("--hold-ms", type=int, default=600)
    parser.add_argument("--repeat-interval-ms", type=int, default=120)
    parser.add_argument("--blur-wait-ms", type=int, default=350)
    parser.add_argument("--evidence")
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
