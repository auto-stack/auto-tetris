"""PLAN-060 targeted theme-adoption probe for 036-tetris (auto-tetris).

Counter-controls (auto-os/PLAN-060 V-01/V-02/V-03 standalone legs):

  leg A (explicit override track): AUTO_UI_THEME=dark -> official Auto/dark
      applied (vendor/themes Auto family dark background token present)
  leg B (explicit light): AUTO_UI_THEME=light -> Auto/light background
  leg C (host follow track): AUTOOS_DESKTOP_CONFIG full candidate
      Solarized/dark + frozen package root -> Solarized dark background
  leg D (V-02 business during reskin): boot Solarized/dark, press 暂停 P
      (TogglePause, real state transition to 已暂停), then flip the config
      file to light in-session; the paused business state must survive the
      reskin; post-flip pixel share is recorded (OS056-REAPPLY-NOTE: live
      external flip may lag -- contract-named recovery is reopen, closed by
      leg E)
  leg E (reopen recovery): fresh boot with the flipped light config ->
      Solarized light background

Oracle: share of frame pixels exactly matching the expected background
token (>=5%). Fit windows expose a runtime-scaffold margin around the app
root, so single-point sampling is unreliable; the token share is robust.

Piece colors (tetris_store.at `colors`, 7 category hues) and the well/
preview dark arena are fixed content-domain values.

Launch: `auto run -r vm --server vm` (pure-VM split track). The a2r rust
backend has a pre-existing codegen red (`??` on str index -> chained
unwrap_or, E0599) that reproduces identically at the base commit with this
toolchain -- named in PLAN-060 with owner=auto-lang; original rust-track
gates (tracked rules_golden fixture) are exercised separately.

Original gates (smoke.spec.ts, run_matrix.py, vm_rules_golden.py,
native_physical.py, cargo rules_golden) stay untouched. Evidence lives in
D:/autostack/plan-artifacts/plan-060/auto-os/tetris.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

EVIDENCE_DIR = r"D:\autostack\plan-artifacts\plan-060\auto-os\tetris"
CONFIG_DIR = r"D:\autostack\plan-artifacts\plan-060\auto-os\tetris\config"
PACKAGE_DIR = r"D:\autostack\auto-ui\packages\themes"
THEME_DIGEST = "9fa07742dc68aa5377ae06cb2d966386002063f184c515b6c5dddf8a6bef838e"

AUTO_DARK_BG = (0x09, 0x09, 0x0B)
AUTO_LIGHT_BG = (0xFF, 0xFF, 0xFF)
SOLARIZED_DARK_BG = (0x00, 0x2B, 0x36)
SOLARIZED_LIGHT_BG = (0xFD, 0xF6, 0xE3)

READY_STATE_SENTINELS = [
    ("准备好了吗", "ready status label present"),
]
READY_VIEW_SENTINELS = [
    ("下一个", "next-piece preview present"),
]


def write_config(path: str, mode: str, family: str = "Solarized") -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            "desktop {\n"
            f'    theme_family : "{family}"\n'
            '    theme_family_version : "0.2.0"\n'
            f'    theme_family_digest : "{THEME_DIGEST}"\n'
            f'    theme_mode : "{mode}"\n'
            "    dark_theme : true\n"
            "}\n"
        )
    return path


def pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class AutoUiMcpClient:
    def __init__(self, port: int):
        self.url = f"http://127.0.0.1:{port}/mcp"
        self._req_id = 1

    def _call(self, tool_name: str, args: dict = None) -> dict:
        req = {
            "jsonrpc": "2.0",
            "id": self._req_id,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": args or {}},
        }
        self._req_id += 1
        http_req = urllib.request.Request(
            self.url, data=json.dumps(req).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(http_req, timeout=10) as response:
            res = json.loads(response.read().decode("utf-8"))
            if "error" in res:
                raise RuntimeError(f"MCP Tool '{tool_name}' error: {res['error']}")
            return res.get("result", {})

    def text(self, tool_name: str, args: dict = None) -> str:
        return self._call(tool_name, args).get("content", [{}])[0].get("text", "")

    def state(self) -> str:
        return self.text("autoui_state")

    def snapshot(self) -> str:
        return self.text("autoui_snapshot")

    def press(self, element_id):
        # split-mode action dispatch addresses elements as "vnode_<id>" strings
        eid = element_id if isinstance(element_id, str) else f"vnode_{element_id}"
        return self.text("autoui_action", {"element_id": eid, "action": "press"})

    def find_button_by_label(self, label: str):
        """Snapshot lines look like: button #vnode_<id> "LABEL" { ."""
        import re
        snap = self.snapshot()
        for line in snap.splitlines():
            if "button" in line and label in line:
                m = re.search(r"#vnode_(\d+)", line)
                if m:
                    return int(m.group(1))
        return None

    def find_button_by_onclick(self, binding: str):
        """Find a button id whose snapshot block carries `onclick: <binding>`."""
        import re
        snap = self.snapshot()
        lines = snap.splitlines()
        current = None
        for line in lines:
            if "button" in line and "#vnode_" in line:
                m = re.search(r"#vnode_(\d+)", line)
                current = int(m.group(1)) if m else None
            if f"onclick: {binding}" in line and current is not None:
                return current
        return None

    def screenshot(self, name: str) -> str:
        raw = self.text("autoui_screenshot", {"name": name, "baseline": False})
        low = raw.lower()
        if "saved to" in low:
            after = raw[low.index("saved to") + len("saved to"):].lstrip(" :").replace("\\\\?\\", "")
            return after.strip()
        return ""


def token_pixel(png_path: str, expect, tol: int = 2):
    """Share of frame pixels matching the expected official token color
    (robust to fit-window runtime margins around the app root)."""
    from PIL import Image

    with Image.open(png_path) as im:
        rgb = im.convert("RGB")
        w, h = rgb.size
        small = rgb.resize((max(w // 4, 1), max(h // 4, 1)))
        sw, sh = small.size
        px = [small.getpixel((x, y)) for x in range(sw) for y in range(sh)]
    n = len(px)
    hits = sum(1 for c in px if all(abs(a - b) <= tol for a, b in zip(c, expect)))
    return hits / n


def boot_and_check(tag: str, app_dir: str, auto_bin: str, env_extra: dict,
                   expect_bg, failures: list, want_dark_state=None) -> str:
    """Boot -> settle -> sentinels -> official-token pixel oracle.
    One full retry on transient startup failure (tool-host control-stream
    races in the split-HTTP backend mode)."""
    os.makedirs(EVIDENCE_DIR, exist_ok=True)
    state = ""
    for attempt in (1, 2):
        port = pick_free_port()
        env = dict(os.environ, AUTOUI_MCP_PORT=str(port), **env_extra)
        proc = subprocess.Popen([auto_bin, "run", "-r", "vm", "--server", "vm"],
                                cwd=app_dir, env=env)
        try:
            client = AutoUiMcpClient(port)
            start = time.time()
            while time.time() - start < 420:
                try:
                    s = client.state()
                    if "status_label" in s:
                        state = s
                        break
                except Exception:
                    pass
                time.sleep(0.5)
            if not state:
                failures.append(f"{tag}: MCP not ready within 420s (attempt {attempt})")
                continue
            time.sleep(4)  # settle: paint + theme publish

            try:
                for needle, why in READY_STATE_SENTINELS:
                    if needle in state:
                        print(f"  [+] state ok: {why}")
                    else:
                        failures.append(f"{tag}: state sentinel missing: {needle}")
                snap = client.snapshot()
                for needle, why in READY_VIEW_SENTINELS:
                    if needle in snap:
                        print(f"  [+] view ok: {why}")
                    else:
                        failures.append(f"{tag}: view sentinel missing: {needle}")

                tmp = client.screenshot(tag)
                if tmp and os.path.exists(tmp):
                    shot = os.path.join(EVIDENCE_DIR, f"{tag}.png")
                    with open(tmp, "rb") as s, open(shot, "wb") as d:
                        d.write(s.read())
                    share = token_pixel(shot, expect_bg)
                    print(f"  [*] {tag} token share = {share:.1%} (expect >=5% of #{'%02x%02x%02x' % expect_bg})")
                    if share >= 0.05:
                        print(f"  [+] {tag}: official package value applied")
                    else:
                        failures.append(f"{tag}: token share {share:.1%} < 5% for #{'%02x%02x%02x' % expect_bg}")
                else:
                    failures.append(f"{tag}: screenshot not saved")

                if want_dark_state is not None:
                    dm_true = "dark_mode: true" in state
                    if want_dark_state and not dm_true:
                        failures.append(f"{tag}: dark_mode state not true")
                    if (not want_dark_state) and dm_true:
                        failures.append(f"{tag}: dark_mode state not false")

                with open(os.path.join(EVIDENCE_DIR, f"state-{tag}.json"), "w", encoding="utf-8") as f:
                    json.dump(state, f, ensure_ascii=False, indent=1)
                break  # this attempt completed the checks
            except Exception as e:
                failures.append(f"{tag}: probe error on attempt {attempt}: {e}")
                state = ""
                continue
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            time.sleep(2)  # let the backend port settle before the next boot
            tmp_dir = os.path.join(app_dir, "src", "front", "tmp")
            if os.path.isdir(tmp_dir):
                shutil.rmtree(tmp_dir, ignore_errors=True)
    return state


def leg_d_live(app_dir: str, auto_bin: str, failures: list) -> None:
    """Live in-session reskin: boot Solarized/dark -> press 暂停 P -> flip
    config to light while running -> paused state must survive; post-flip
    light-token share recorded (lag per OS056-REAPPLY-NOTE)."""
    os.makedirs(EVIDENCE_DIR, exist_ok=True)
    cfg_flip = write_config(os.path.join(CONFIG_DIR, "config_flip.at"), "dark")
    port = pick_free_port()
    env = dict(os.environ, AUTOUI_MCP_PORT=str(port),
               AUTOOS_DESKTOP_CONFIG=cfg_flip,
               AUTOOS_THEME_PACKAGE_DIR=PACKAGE_DIR)
    proc = subprocess.Popen([auto_bin, "run", "-r", "vm", "--server", "vm"],
                            cwd=app_dir, env=env)
    try:
        client = AutoUiMcpClient(port)
        start = time.time()
        state = ""
        while time.time() - start < 420:
            try:
                s = client.state()
                if "status_label" in s:
                    state = s
                    break
            except Exception:
                pass
            time.sleep(0.5)
        if not state:
            failures.append("leg D: MCP not ready within 420s")
            return
        time.sleep(4)

        # ready phase ignores TogglePause: start the game first via a grid
        # cell button (onclick: .Start), then press 暂停 P (TogglePause).
        start_id = client.find_button_by_onclick(".Start")
        if start_id is not None:
            client.press(start_id)
            time.sleep(1.0)
            st = client.state()
            started = "进行中" in st
            print(f"  [+] start press (id={start_id}); playing state visible: {started}")
        else:
            print("  [!] no onclick: .Start button found; trying direct pause")
        eid = client.find_button_by_label("暂停")
        if eid is None:
            with open(os.path.join(EVIDENCE_DIR, "snapshot-legD.txt"), "w", encoding="utf-8") as f:
                f.write(client.snapshot())
            failures.append("leg D: press target 暂停 not found (snapshot dumped)")
            return
        client.press(eid)
        time.sleep(1.2)
        state_after = client.state()
        if "已暂停" not in state_after:
            client.press(eid)  # one defensive re-press (dispatch timing)
            time.sleep(1.2)
            state_after = client.state()
        paused = "已暂停" in state_after
        print(f"  [+] pressed 暂停 (id={eid}); paused state visible: {paused}")
        if not paused:
            failures.append("leg D: paused state not visible after press")

        write_config(cfg_flip, "light")
        print("  [*] config flipped to light in-session; polling for survival")

        survived = True
        last_state = state_after
        deadline = time.time() + 15
        while time.time() < deadline:
            time.sleep(1)
            last_state = client.state()
            if "已暂停" not in last_state:
                survived = False
                break
        if not survived:
            failures.append("leg D: paused state lost during reskin poll")
        else:
            print("  [+] paused business state survived reskin window (V-02)")

        tmp = client.screenshot("060_tetris_D_after_flip")
        if tmp and os.path.exists(tmp):
            shot = os.path.join(EVIDENCE_DIR, "060_tetris_D_after_flip.png")
            with open(tmp, "rb") as s, open(shot, "wb") as d:
                d.write(s.read())
            share_light = token_pixel(shot, SOLARIZED_LIGHT_BG)
            matches_light = share_light >= 0.05
            print(f"  [*] post-flip light-token share = {share_light:.1%}")
            if matches_light:
                print("  [+] live flip applied in-session")
            else:
                print("  [~] live flip lag recorded (OS056-REAPPLY-NOTE; reopen leg E closes)")
        else:
            failures.append("leg D: post-flip screenshot not saved")

        with open(os.path.join(EVIDENCE_DIR, "state-legD-after.json"), "w", encoding="utf-8") as f:
            json.dump(last_state, f, ensure_ascii=False, indent=1)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        time.sleep(2)
        tmp_dir = os.path.join(app_dir, "src", "front", "tmp")
        if os.path.isdir(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)


def main() -> int:
    failures: list = []
    app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    auto_bin = os.environ.get("AUTO_BIN", "auto")

    print(f"[*] leg A: explicit AUTO_UI_THEME=dark (override track)")
    boot_and_check("060_tetris_A_dark", app_dir, auto_bin,
                   {"AUTO_UI_THEME": "dark"}, AUTO_DARK_BG, failures,
                   want_dark_state=True)

    print(f"[*] leg B: explicit AUTO_UI_THEME=light")
    boot_and_check("060_tetris_B_light", app_dir, auto_bin,
                   {"AUTO_UI_THEME": "light"}, AUTO_LIGHT_BG, failures,
                   want_dark_state=False)

    print(f"[*] leg C: host follow track -- Solarized/dark full candidate")
    cfg_dark = write_config(os.path.join(CONFIG_DIR, "config_solarized_dark.at"), "dark")
    boot_and_check("060_tetris_C_solarized_dark", app_dir, auto_bin,
                   {"AUTOOS_DESKTOP_CONFIG": cfg_dark,
                    "AUTOOS_THEME_PACKAGE_DIR": PACKAGE_DIR},
                   SOLARIZED_DARK_BG, failures)

    print(f"[*] leg D: live business during reskin (pause press + in-session flip)")
    leg_d_live(app_dir, auto_bin, failures)

    print(f"[*] leg E: reopen recovery with flipped light config")
    cfg_flip = os.path.join(CONFIG_DIR, "config_flip.at")
    boot_and_check("060_tetris_E_reopen_light", app_dir, auto_bin,
                   {"AUTOOS_DESKTOP_CONFIG": cfg_flip,
                    "AUTOOS_THEME_PACKAGE_DIR": PACKAGE_DIR},
                   SOLARIZED_LIGHT_BG, failures)

    if failures:
        print("[-] FAILURES:")
        for f in failures:
            print("   -", f)
        return 1
    print("[+] PLAN-060 tetris probe: all counter-controls passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
