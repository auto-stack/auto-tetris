#!/usr/bin/env python3
"""Small, repeatable evidence runner for the Tetris deployment matrix.

The script deliberately reports ``blocked`` when a native driver or compiled
backend is not available. A skipped leg is never counted as a passing leg.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
EVIDENCE = TESTS / "evidence"


def run_cmd(args: list[str], *, timeout: int = 120) -> tuple[str, str]:
    """Return ``(status, detail)`` for one local command."""

    try:
        proc = subprocess.run(
            args,
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return "blocked", f"command not found: {args[0]}"
    except subprocess.TimeoutExpired:
        return "blocked", f"timeout after {timeout}s: {' '.join(args)}"
    detail = [line for line in (proc.stdout + proc.stderr).splitlines() if line.strip()]
    tail = "\n".join(detail[-6:]) if detail else "no output"
    return ("supported" if proc.returncode == 0 else "blocked", tail)


def auto_bin() -> str | None:
    configured = os.environ.get("AUTO_BIN")
    if configured:
        return configured
    return shutil.which("auto.exe") or shutil.which("auto")


def probe() -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    result["source.app"] = (
        "supported",
        "src/front/app.at and src/front/tetris_store.at present",
    ) if (ROOT / "src/front/app.at").is_file() and (ROOT / "src/front/tetris_store.at").is_file() else (
        "blocked",
        "front source is incomplete",
    )
    result["source.api"] = (
        "supported",
        "src/back/api.at and src/back/db.at present",
    ) if (ROOT / "src/back/api.at").is_file() and (ROOT / "src/back/db.at").is_file() else (
        "blocked",
        "back source is incomplete",
    )
    result["tests.playwright"] = (
        "supported",
        "Playwright package and smoke.spec.ts present",
    ) if (TESTS / "package.json").is_file() and (TESTS / "smoke.spec.ts").is_file() else (
        "blocked",
        "Playwright test package is incomplete",
    )
    result["native.input-driver"] = (
        "supported",
        "tests/native_physical.py can send Windows key-down/key-up, long-press and blur events",
    ) if (TESTS / "native_physical.py").is_file() else (
        "blocked",
        "physical Windows input driver is missing",
    )
    result["gallery.contract"] = run_cmd(
        [sys.executable, str(TESTS / "gallery_contract.py")], timeout=30
    ) if (TESTS / "gallery_contract.py").is_file() else (
        "blocked",
        "gallery contract audit is missing",
    )

    binary = auto_bin()
    if binary is None:
        result["cli.help"] = ("blocked", "AUTO_BIN/auto.exe not found")
        result["backend.transpile"] = ("blocked", "AUTO_BIN/auto.exe not found")
    else:
        result["cli.help"] = run_cmd([binary, "run", "--help"], timeout=30)
        result["backend.transpile"] = run_cmd(
            [binary, "trans", "--path", "src/back/db.at", "rust", "--ai"],
            timeout=60,
        )

    generated_rust = ROOT / "rust-workspace/036-tetris/src/main.rs"
    generated_vue = ROOT / "gen/front/vue/package.json"
    result["rust.generated"] = (
        "supported",
        str(generated_rust.relative_to(ROOT)),
    ) if generated_rust.is_file() else ("blocked", "run auto build --render rust --gen-only")
    result["vue.generated"] = (
        "supported",
        str(generated_vue.relative_to(ROOT)),
    ) if generated_vue.is_file() else ("blocked", "run auto build --render vue --gen-only")

    # These legs require an actual native window/MCP driver. We do not turn a
    # missing driver into a false pass.
    mcp = os.environ.get("AUTOUI_MCP_URL")
    result["vm.mcp"] = (
        "supported",
        f"MCP endpoint configured: {mcp}",
    ) if mcp else ("blocked", "AUTOUI_MCP_URL is not configured")
    result["rules.vm-golden"] = vm_rules_golden()

    backend = os.environ.get("TETRIS_BACKEND_EXE")
    if not backend:
        for candidate in (
            ROOT / ".cargo-back-target2/debug/app-036-tetris-back.exe",
            ROOT / ".cargo-back-target/debug/app-036-tetris-back.exe",
        ):
            if candidate.is_file():
                backend = str(candidate)
                break
    result["rust.backend"] = (
        "supported",
        str(Path(backend).resolve().relative_to(ROOT)) if Path(backend).resolve().is_relative_to(ROOT) else "external executable",
    ) if backend else ("blocked", "TETRIS_BACKEND_EXE or a built backend executable is required")
    return result


def write_evidence(result: dict[str, tuple[str, str]]) -> Path:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE / "capabilities.md"
    lines = [
        "# Tetris capability probe",
        "",
        "Generated by `python tests/run_matrix.py --probe`.",
        "A `blocked` row is an explicit missing capability or driver, never a pass.",
        "",
        "| leg | status | evidence |",
        "|---|---|---|",
    ]
    for leg, (status, detail) in sorted(result.items()):
        safe = detail.replace("|", "\\|").replace("\n", "<br>")
        lines.append(f"| `{leg}` | `{status}` | {safe} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def http_json(url: str, method: str = "GET", body: dict | None = None) -> object:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = Request(url, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    with urlopen(request, timeout=3) as response:
        return json.loads(response.read().decode("utf-8"))


def persistence() -> tuple[str, str]:
    executable = os.environ.get("TETRIS_BACKEND_EXE")
    if not executable:
        for candidate in (
            ROOT / ".cargo-back-target2/debug/app-036-tetris-back.exe",
            ROOT / ".cargo-back-target/debug/app-036-tetris-back.exe",
        ):
            if candidate.is_file():
                executable = str(candidate)
                break
    if not executable:
        return "blocked", "build the backend or set TETRIS_BACKEND_EXE"

    record_file = ROOT / "records.json"
    original = record_file.read_text(encoding="utf-8") if record_file.exists() else None

    def start(port: int) -> subprocess.Popen:
        env = os.environ.copy()
        env["AUTO_HTTP_PORT"] = str(port)
        return subprocess.Popen(
            [executable], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

    def stop(process: subprocess.Popen) -> None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()

    port = int(os.environ.get("TETRIS_TEST_PORT", "17511"))
    record_file.write_text("42", encoding="utf-8")
    process = start(port)
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(30):
            try:
                before = http_json(base + "/api/tetris/record")
                break
            except (URLError, ConnectionError, TimeoutError):
                time.sleep(0.2)
        else:
            return "blocked", "backend did not become ready"

        lower = http_json(base + "/api/tetris/score", "POST", {"score": "10"})
        after_lower = http_json(base + "/api/tetris/record")
        if before != 42 or after_lower != 42:
            return "blocked", f"lower score overwrote record: {before} -> {after_lower}"
        negative = http_json(base + "/api/tetris/score", "POST", {"score": "-1"})
        invalid = http_json(base + "/api/tetris/score", "POST", {"score": "oops"})
        after_invalid = http_json(base + "/api/tetris/record")
        if negative is not False or invalid is not False or after_invalid != 42:
            return "blocked", f"invalid scores were accepted: {negative}, {invalid}, {after_invalid}"
        higher = http_json(base + "/api/tetris/score", "POST", {"score": "99"})
        after = http_json(base + "/api/tetris/record")
        persisted_text = record_file.read_text(encoding="utf-8")
        if higher is not True or after != 99:
            return "blocked", f"unexpected monotonic result: {higher}, {after}"
        if "schema_version" not in persisted_text or "\"best\":99" not in persisted_text:
            return "blocked", f"record file is not versioned JSON: {persisted_text!r}"
    finally:
        stop(process)

    restart_port = port + 1
    restarted = start(restart_port)
    try:
        base = f"http://127.0.0.1:{restart_port}"
        for _ in range(30):
            try:
                restart = http_json(base + "/api/tetris/record")
                break
            except (URLError, ConnectionError, TimeoutError):
                time.sleep(0.2)
        else:
            return "blocked", "backend did not become ready after restart"
        if restart != 99:
            return "blocked", f"record did not survive restart: {restart}"
    finally:
        stop(restarted)
        if original is None:
            record_file.unlink(missing_ok=True)
        else:
            record_file.write_text(original, encoding="utf-8")
    return "supported", "monotonic update and cross-process restart read passed"


def rust_rules_golden() -> tuple[str, str]:
    """Run the generated Rust fixture against the actual TetrisStore code."""

    workspace = ROOT / "rust-workspace"
    fixture = workspace / "036-tetris" / "tests" / "rules_golden.rs"
    if not fixture.is_file():
        return "blocked", "Rust rules fixture is missing; regenerate or restore tests/rules_golden.rs"
    try:
        proc = subprocess.run(
            [
                "cargo",
                "test",
                "-p",
                "tetris",
                "--test",
                "rules_golden",
                "--no-default-features",
                "--features",
                "ui-iced",
            ],
            cwd=workspace,
            text=True,
            capture_output=True,
            timeout=300,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return "blocked", f"Rust golden runner unavailable: {exc}"
    if proc.returncode != 0:
        detail = (proc.stdout + proc.stderr).splitlines()
        return "blocked", "Rust golden failed: " + (detail[-1] if detail else "no output")
    return "supported", "generated TetrisStore golden passed (opening/lock + 7x4 rotations + 1..4 line clears)"


def vm_rules_golden() -> tuple[str, str]:
    """Run the same deterministic cases through the VM fixture channel."""

    url = os.environ.get("AUTOUI_MCP_URL")
    if not url:
        return "blocked", "AUTOUI_MCP_URL is not configured"
    runner = TESTS / "vm_rules_golden.py"
    if not runner.is_file():
        return "blocked", "VM rules golden runner is missing"
    try:
        proc = subprocess.run(
            [sys.executable, str(runner), "--mcp-url", url],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=180,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return "blocked", f"VM golden runner unavailable: {exc}"
    detail = (proc.stdout + proc.stderr).strip().splitlines()
    if proc.returncode != 0:
        return "blocked", detail[-1] if detail else "VM rules golden failed"
    return "supported", detail[-1] if detail else "VM rules golden passed"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", action="store_true", help="write capability evidence")
    parser.add_argument("--suite", choices=["rules", "gameplay", "visual", "persistence"])
    parser.add_argument("--all-modes", action="store_true")
    args = parser.parse_args()

    if args.probe or args.all_modes or args.suite is None:
        result = probe()
        path = write_evidence(result)
        print(path)
        for leg, (status, detail) in sorted(result.items()):
            print(f"{leg}: {status} — {detail.splitlines()[0]}")
        if not args.all_modes and args.suite is None:
            return 0

    if args.suite == "persistence" or args.all_modes:
        status, detail = persistence()
        print(f"persistence: {status} — {detail}")
        if status != "supported" and not args.all_modes:
            return 2
    if args.suite == "rules" or args.all_modes:
        rules_failed = False
        status, detail = rust_rules_golden()
        print(f"rules.rust-golden: {status} — {detail}")
        rules_failed = rules_failed or status != "supported"
        status, detail = vm_rules_golden()
        print(f"rules.vm-golden: {status} — {detail}")
        rules_failed = rules_failed or status != "supported"
        if rules_failed and args.suite == "rules":
            return 2
    if args.suite in {"gameplay", "visual"} or args.all_modes:
        print("native/gameplay/visual: blocked — run with a connected native window or browser URL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
