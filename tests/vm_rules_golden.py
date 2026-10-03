#!/usr/bin/env python3
"""Run the Tetris rules golden through the VM AutoUI MCP fixture channel.

The Rust golden is generated from the same ``TetrisStore`` source.  This
runner seeds the VM store with the equivalent deterministic cases, dispatches
the normal handlers, and compares the observable state.  It never adds a
debug control to the application; the fixture tool is enabled only when the
VM process is started with ``AUTOUI_TEST_FIXTURES=1``.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request


SHAPES = [
    [0, 1, 1, 1, 2, 1, 3, 1], [2, 0, 2, 1, 2, 2, 2, 3],
    [0, 2, 1, 2, 2, 2, 3, 2], [1, 0, 1, 1, 1, 2, 1, 3],
    [1, 0, 2, 0, 1, 1, 2, 1], [1, 0, 2, 0, 1, 1, 2, 1],
    [1, 0, 2, 0, 1, 1, 2, 1], [1, 0, 2, 0, 1, 1, 2, 1],
    [1, 0, 0, 1, 1, 1, 2, 1], [1, 0, 1, 1, 2, 1, 1, 2],
    [0, 1, 1, 1, 2, 1, 1, 2], [1, 0, 0, 1, 1, 1, 1, 2],
    [1, 0, 2, 0, 0, 1, 1, 1], [1, 0, 1, 1, 2, 1, 2, 2],
    [1, 0, 2, 0, 0, 1, 1, 1], [1, 0, 1, 1, 2, 1, 2, 2],
    [0, 0, 1, 0, 1, 1, 2, 1], [2, 0, 1, 1, 2, 1, 1, 2],
    [0, 0, 1, 0, 1, 1, 2, 1], [2, 0, 1, 1, 2, 1, 1, 2],
    [0, 0, 0, 1, 1, 1, 2, 1], [1, 0, 2, 0, 1, 1, 1, 2],
    [0, 1, 1, 1, 2, 1, 2, 2], [1, 0, 1, 1, 0, 2, 1, 2],
    [2, 0, 0, 1, 1, 1, 2, 1], [1, 0, 1, 1, 1, 2, 2, 2],
    [0, 1, 1, 1, 2, 1, 0, 2], [0, 0, 1, 0, 1, 1, 1, 2],
]


class McpError(RuntimeError):
    pass


class Client:
    def __init__(self, url: str):
        self.url = url
        self.request_id = 1

    def call(self, name: str, arguments: dict | None = None) -> dict:
        request = urllib.request.Request(
            self.url,
            data=json.dumps({
                "jsonrpc": "2.0",
                "id": self.request_id,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments or {}},
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        self.request_id += 1
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError) as exc:
            raise McpError(f"MCP request failed for {name}: {exc}") from exc
        if "error" in payload:
            raise McpError(f"{name}: {payload['error']}")
        result = payload.get("result") or {}
        if result.get("isError"):
            raise McpError(f"{name}: {self.text(result)}")
        return result

    @staticmethod
    def text(result: dict) -> str:
        content = result.get("content") or []
        return "\n".join(
            block.get("text", "") for block in content if block.get("type") == "text"
        )

    def fixture(self, state: dict, trigger: str | None = None) -> dict:
        args = {"schema_version": 1, "state": state}
        if trigger:
            # TetrisStore is the state owner, but App is the public handler
            # route that forwards the message to the store in this app.
            args["trigger"] = {"widget": "App", "event": trigger, "input": None}
        result = self.call("autoui_fixture", args)
        raw = self.text(result).strip()
        structured = result.get("structuredContent")
        if isinstance(result.get("status"), str):
            # Current MCP servers return the fixture receipt directly as the
            # tool result, while older servers wrap JSON in content/text.
            value = result
        elif isinstance(structured, dict):
            value = structured
        else:
            try:
                value = json.loads(raw)
            except json.JSONDecodeError:
                raise McpError(f"autoui_fixture returned non-JSON: {raw}")
        if value.get("status") != "applied":
            raise McpError(f"autoui_fixture was not applied: {value}")
        return value

    def state(self, fields: list[str]) -> dict:
        result = self.call("autoui_state", {"fields": fields})
        text = self.text(result)
        values: dict[str, object] = {}
        pattern = re.compile(r"^\s+([^:]+): (.+) \(([^)]+)\)$")
        for line in text.splitlines():
            match = pattern.match(line)
            if not match:
                continue
            name, raw, kind = match.groups()
            try:
                if kind == "int":
                    values[name] = int(raw)
                elif kind == "bool":
                    values[name] = raw == "true"
                elif kind == "str":
                    values[name] = json.loads(raw)
                elif kind == "list":
                    values[name] = ast.literal_eval(raw)
                else:
                    values[name] = raw
            except (ValueError, SyntaxError) as exc:
                raise McpError(f"cannot parse state field {name}: {raw!r}") from exc
        missing = [field for field in fields if field not in values]
        if missing:
            raise McpError(f"state fields missing: {missing}; response was {text!r}")
        return values

    def wait_for(self, fields: list[str], predicate, timeout: float = 2.0) -> dict:
        """Wait for a queued handler trigger to become visible in state."""

        deadline = time.monotonic() + timeout
        latest: dict[str, object] = {}
        while time.monotonic() < deadline:
            latest = self.state(fields)
            if predicate(latest):
                return latest
            time.sleep(0.02)
        raise McpError(f"handler state did not converge: {latest}")

    def dispatch(self, event: str) -> None:
        """Queue an App handler and send one acknowledged no-op to flush it.

        The VM renderer acknowledges the fixture write before the following
        handler message is visible to ``autoui_state``.  A second fixture is
        therefore the deterministic message-boundary barrier.
        """

        self.fixture({"phase": "playing"}, event)
        self.fixture({"phase": "playing"})


def playing_state(**overrides: object) -> dict:
    state: dict[str, object] = {
        "board": [0] * 200,
        "piece": 2,
        "next_piece": 0,
        "seed": 17,
        "rotation": 0,
        "px": 3,
        "py": 0,
        "score": 0,
        "lines": 0,
        "level": 1,
        # Keep the live 20ms Tick loop from racing deterministic action cases.
        # The line-clear handler still restores the production gravity value.
        "gravity_ms": 1_000_000,
        "elapsed_ms": 0,
        "phase": "playing",
        "pending_lock": False,
    }
    state.update(overrides)
    return state


def check_opening(client: Client) -> None:
    client.fixture(playing_state())
    client.dispatch("MoveLeft")
    client.dispatch("Rotate")
    client.dispatch("SoftDrop")
    got = client.wait_for(["rotation", "px", "py", "score"], lambda s: s["rotation"] == 1 and s["px"] == 2 and s["py"] == 1 and s["score"] == 1)
    assert (got["rotation"], got["px"], got["py"], got["score"]) == (1, 2, 1, 1), got
    # Queue hard drop followed immediately by the normal lock Tick.  The
    # renderer may acknowledge a fixture before its handler is visible to
    # ``autoui_state``, so the final locked state is the stable comparison.
    client.fixture({"phase": "playing"}, "HardDrop")
    client.fixture({"phase": "playing"}, "Tick")
    got = client.wait_for(["piece", "next_piece", "lines", "score", "board"], lambda s: s["piece"] == 0 and s["next_piece"] == 2 and s["score"] == 33 and s["lines"] == 0)
    assert (got["piece"], got["next_piece"], got["lines"], got["score"]) == (0, 2, 0, 33), got
    assert sum(cell != 0 for cell in got["board"]) == 4, got


def check_rotations(client: Client) -> None:
    """Exercise every shape/rotation through the real collision handler.

    ``autoui_state`` intentionally renders nested VM values as ``<vmref>``;
    reading ``shapes`` directly would therefore only test the inspector's
    formatting.  Instead, place one obstacle on each expected occupied cell
    and ask the normal Rotate handler to enter that rotation.  Every expected
    cell must block the transition.  Since each shape has exactly four cells,
    this proves the complete four-cell coordinate set without adding a debug
    UI or changing the VM runtime.
    """
    for index, shape in enumerate(SHAPES):
        piece, target_rotation = divmod(index, 4)
        previous_rotation = (target_rotation + 3) % 4
        for offset in range(0, len(shape), 2):
            x, y = shape[offset], shape[offset + 1]
            board = [0] * 200
            world_x, world_y = 3 + x, y
            board[world_y * 10 + world_x] = 7
            client.fixture(playing_state(
                board=board,
                piece=piece,
                rotation=previous_rotation,
                px=3,
                py=0,
            ))
            client.dispatch("Rotate")
            got = client.wait_for(
                ["rotation"],
                lambda state, expected=previous_rotation: state["rotation"] == expected,
            )
            assert got["rotation"] == previous_rotation, (
                f"piece={piece} rotation={target_rotation} cell=({x},{y})",
                got,
            )


def check_line_clears(client: Client) -> None:
    for cleared in range(1, 5):
        board = [0] * 200
        for row in range(20 - cleared, 20):
            for col in range(9):
                board[row * 10 + col] = 1
        client.fixture(playing_state(
            board=board,
            piece=0,
            rotation=1,
            px=7,
            py=16,
            pending_lock=True,
        ), "Tick")
        got = client.wait_for(["lines", "score", "feedback", "board", "pending_lock"], lambda s, n=cleared: s["lines"] == n and s["pending_lock"] is False)
        expected_score = {1: 100, 2: 300, 3: 500, 4: 800}[cleared]
        assert got["lines"] == cleared, (cleared, got)
        assert got["score"] == expected_score, (cleared, got)
        assert got["feedback"] == f"消除 {cleared} 行", (cleared, got)
        assert all(cell == 0 for cell in got["board"][: cleared * 10]), (cleared, got)
        assert len(got["board"]) == 200, (cleared, got)
        assert got["pending_lock"] is False, (cleared, got)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mcp-url", default=os.environ.get("AUTOUI_MCP_URL"))
    args = parser.parse_args()
    if not args.mcp_url:
        print("BLOCKED: set AUTOUI_MCP_URL to a VM MCP endpoint", file=sys.stderr)
        return 2
    client = Client(args.mcp_url)
    try:
        check_opening(client)
        check_rotations(client)
        check_line_clears(client)
    except (AssertionError, McpError) as exc:
        print(f"BLOCKED: VM rules golden failed: {exc}", file=sys.stderr)
        return 2
    print("VM rules golden passed: opening/lock + 7x4 rotations + 1..4 line clears")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
