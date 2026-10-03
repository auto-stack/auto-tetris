#!/usr/bin/env python3
"""Read-only VM MCP structure smoke for Plan 005.

Set AUTOUI_MCP_URL to an already running ``auto run -r vm`` MCP endpoint.
"""

import json
import os
import re
import sys
import urllib.request


def call(url, method, arguments):
    payload = json.dumps({
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": method, "arguments": arguments},
        "id": 1,
    }).encode()
    request = urllib.request.Request(url, payload, {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        data = json.load(response)
    if "error" in data:
        raise RuntimeError(data["error"])
    return "\n".join(item.get("text", "") for item in data.get("result", {}).get("content", []))


def main():
    url = os.environ.get("AUTOUI_MCP_URL")
    if not url:
        print("AUTOUI_MCP_URL not set; VM MCP smoke skipped")
        return 0
    snapshot = call(url, "autoui_snapshot", {})
    for expected in ("俄罗斯方块", "玩法说明", "暂停 P", "硬降"):
        if expected not in snapshot:
            print(f"missing {expected!r} in VM snapshot", file=sys.stderr)
            return 1
    if not re.search(r"(得分|最高纪录|下一个)", snapshot):
        print("score panel missing in VM snapshot", file=sys.stderr)
        return 1
    print("Tetris VM MCP snapshot OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
