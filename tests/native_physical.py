#!/usr/bin/env python3
"""Drive the real Windows window for the Plan 005 input acceptance gate.

This is intentionally separate from the AutoUI MCP driver.  MCP sends a
logical ``press`` action, while this driver sends Windows key-down and key-up
events to the foreground native window.  A missing or hidden window is an
explicit blocked result; it is never reported as a skipped pass.

Example::

    python tests/native_physical.py --mcp-url http://127.0.0.1:9247/mcp \
        --long-press-ms 600 --blur --evidence tests/evidence/native-input.json
"""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.request


if sys.platform == "win32":
    user32 = ctypes.WinDLL("user32", use_last_error=True)

    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    user32.EnumWindows.argtypes = [EnumWindowsProc, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.GetForegroundWindow.restype = wintypes.HWND

    ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

    user32.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
    user32.AllowSetForegroundWindow.restype = wintypes.BOOL
    user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ULONG_PTR]
    user32.keybd_event.restype = None

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD),
        ]

    class INPUT_UNION(ctypes.Union):
        # INPUT.cbSize is 40 bytes on 64-bit Windows. Including all three
        # union arms preserves the required MOUSEINPUT alignment even though
        # this driver only emits keyboard events.
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", INPUT_UNION)]

    user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    user32.SendInput.restype = wintypes.UINT


VK = {
    "ArrowLeft": 0x25,
    "ArrowUp": 0x26,
    "ArrowRight": 0x27,
    "ArrowDown": 0x28,
    "Space": 0x20,
    "P": 0x50,
    "Escape": 0x1B,
}
EXTENDED = {"ArrowLeft", "ArrowUp", "ArrowRight", "ArrowDown"}


def window_inventory(title: str) -> list[dict[str, object]]:
    if sys.platform != "win32":
        return []
    found: list[dict[str, object]] = []

    @EnumWindowsProc
    def callback(hwnd: int, _lparam: int) -> bool:
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        caption = buffer.value
        if title.casefold() not in caption.casefold():
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        found.append(
            {
                "hwnd": int(hwnd),
                "title": caption,
                "visible": bool(user32.IsWindowVisible(hwnd)),
                "pid": int(pid.value),
            }
        )
        return True

    user32.EnumWindows(callback, 0)
    return found


def other_visible_window(target_hwnd: int) -> int | None:
    if sys.platform != "win32":
        return None
    result: list[int] = []

    @EnumWindowsProc
    def callback(hwnd: int, _lparam: int) -> bool:
        if int(hwnd) == target_hwnd or not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            result.append(int(hwnd))
            return False
        return True

    user32.EnumWindows(callback, 0)
    return result[0] if result else None


def send_key(key: str, down: bool) -> None:
    if key not in VK:
        raise ValueError(f"unsupported physical key: {key}")
    flags = 0
    if key in EXTENDED:
        flags |= 0x0001  # KEYEVENTF_EXTENDEDKEY
    if not down:
        flags |= 0x0002  # KEYEVENTF_KEYUP
    event = INPUT(type=1, ki=KEYBDINPUT(wVk=VK[key], wScan=0, dwFlags=flags, time=0, dwExtraInfo=0))
    sent = user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))
    if sent != 1:
        error = ctypes.get_last_error()
        raise OSError(error, f"SendInput failed for {key} ({'down' if down else 'up'})")


def focus_window(hwnd: int) -> bool:
    """Transfer foreground focus despite Windows' foreground-lock timeout."""

    if sys.platform != "win32":
        return False
    # A benign Alt tap grants the current process a foreground-transfer
    # opportunity. AllowSetForegroundWindow then makes the intended target
    # explicit; this is the same user-visible focus transition as clicking it.
    user32.AllowSetForegroundWindow(0xFFFFFFFF)
    user32.keybd_event(0x12, 0, 0, 0)  # VK_MENU down
    user32.keybd_event(0x12, 0, 0x0002, 0)  # VK_MENU up
    return bool(user32.SetForegroundWindow(hwnd))


def mcp_snapshot(url: str | None) -> str | None:
    if not url:
        return None
    payload = json.dumps(
        {"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "autoui_snapshot", "arguments": {}}, "id": 1}
    ).encode("utf-8")
    request = urllib.request.Request(url, payload, {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        data = json.load(response)
    if "error" in data:
        raise RuntimeError(data["error"])
    return "\n".join(item.get("text", "") for item in data.get("result", {}).get("content", []))


def mcp_start_if_ready(url: str | None, snapshot: str | None) -> str | None:
    """Start the game through its rendered Dialog button before physical input."""

    if not url or not snapshot or "准备好了吗" not in snapshot:
        return snapshot
    match = re.search(r'button #(\S+) "开始游戏"', snapshot)
    if not match:
        return snapshot
    payload = json.dumps(
        {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "autoui_action",
                "arguments": {"element_id": match.group(1), "action": "press"},
            },
            "id": 1,
        }
    ).encode("utf-8")
    request = urllib.request.Request(url, payload, {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10):
        pass
    time.sleep(0.2)
    return mcp_snapshot(url)


def run(args: argparse.Namespace) -> int:
    if sys.platform != "win32":
        print("BLOCKED: native physical input requires Windows", file=sys.stderr)
        return 2

    matches = window_inventory(args.title)
    visible = [item for item in matches if item["visible"]]
    if not visible:
        hidden = ", ".join(f"{item['title']} (hidden)" for item in matches) or "none"
        print(f"BLOCKED: no visible native window matching {args.title!r}; matches: {hidden}", file=sys.stderr)
        return 2

    target = int(visible[0]["hwnd"])
    if not user32.ShowWindow(target, 9):  # SW_RESTORE; harmless for an ordinary window
        pass
    if not focus_window(target):
        print(f"BLOCKED: SetForegroundWindow failed for hwnd {target}", file=sys.stderr)
        return 2
    time.sleep(0.15)
    if int(user32.GetForegroundWindow()) != target:
        print(f"BLOCKED: hwnd {target} did not become foreground", file=sys.stderr)
        return 2

    events: list[dict[str, object]] = []
    try:
        before = mcp_snapshot(args.mcp_url)
        before = mcp_start_if_ready(args.mcp_url, before)
    except Exception as exc:  # pragma: no cover - depends on external MCP host
        print(f"BLOCKED: AutoUI MCP snapshot failed before input: {exc}", file=sys.stderr)
        return 2
    for index, key in enumerate(args.keys):
        started = time.time()
        send_key(key, True)
        try:
            if index == 0 and args.long_press_ms:
                time.sleep(args.long_press_ms / 1000)
        finally:
            send_key(key, False)
        events.append({"key": key, "down_up": True, "held_ms": round((time.time() - started) * 1000)})
        if index == 0 and args.blur:
            other = other_visible_window(target)
            if other is None or not focus_window(other):
                print("BLOCKED: no second visible window available for blur/失焦", file=sys.stderr)
                return 2
            time.sleep(0.15)
            events.append({"blur": True, "foreground_hwnd": int(user32.GetForegroundWindow())})
            focus_window(target)
            time.sleep(0.15)
    try:
        after = mcp_snapshot(args.mcp_url)
    except Exception as exc:  # pragma: no cover - depends on external MCP host
        print(f"BLOCKED: AutoUI MCP snapshot failed after input: {exc}", file=sys.stderr)
        return 2

    evidence = {
        "window": visible[0],
        "keys": events,
        "mcp_before": before,
        "mcp_after": after,
    }
    if args.evidence:
        path = Path(args.evidence)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(path)
    print(f"Native physical input OK: hwnd={target}, keys={','.join(args.keys)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", default=os.environ.get("TETRIS_WINDOW_TITLE", "俄罗斯方块"))
    parser.add_argument("--mcp-url", default=os.environ.get("AUTOUI_MCP_URL"))
    parser.add_argument("--long-press-ms", type=int, default=500)
    parser.add_argument("--blur", action="store_true", help="focus another window after the first key")
    parser.add_argument("--evidence", help="write JSON evidence to this path")
    parser.add_argument(
        "keys",
        nargs="*",
        default=["ArrowLeft", "ArrowRight", "ArrowDown", "Space", "P"],
        help="keys to send in order",
    )
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
