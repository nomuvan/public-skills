#!/usr/bin/env python3
"""launch-workspace.py — cmuxで作業用Windowを起動・停止する

Usage:
  python3 launch-workspace.py              # デフォルトWindow起動
  python3 launch-workspace.py --name "名前" # 指定Window起動
  python3 launch-workspace.py --stop       # デフォルトWindow停止
  python3 launch-workspace.py --list       # 定義一覧
"""

import argparse
import re
import subprocess
import sys
import time
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
CONFIGS_DIR = PROJECT_ROOT / "workspaces"


# ── helpers ──────────────────────────────────────────────

def run(cmd: str) -> tuple[str, int]:
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return r.stdout.strip(), r.returncode


def cmux(args: str) -> str:
    out, _ = run(f"cmux {args}")
    return out


def log(msg: str):
    print(f"  {msg}")


# ── config ───────────────────────────────────────────────

def load_all_windows() -> list[dict]:
    windows = []
    if not CONFIGS_DIR.exists():
        return windows
    for p in sorted(CONFIGS_DIR.glob("*.toml")):
        with open(p, "rb") as f:
            data = tomllib.load(f)
        for w in data.get("window", []):
            w["_source"] = p.name
            windows.append(w)
    return windows


def find_window_config(windows: list[dict], name: str | None) -> dict | None:
    if name:
        return next((w for w in windows if w["name"] == name), None)
    return next(
        (w for w in windows if w.get("default")),
        windows[0] if windows else None,
    )


# ── tree parsing ─────────────────────────────────────────

def get_tree_raw() -> str:
    return cmux("--id-format both tree --all")


def get_workspace_ids() -> set[str]:
    raw = get_tree_raw()
    return set(re.findall(r"workspace:\d+", raw))


def find_windows_containing_titles(pane_titles: list[str]) -> list[str]:
    """pane_titlesに一致するワークスペースを持つウィンドウのUUIDを返す"""
    raw = get_tree_raw()
    title_set = set(pane_titles)
    windows_to_close = []
    current_win_uuid = None
    matched = False

    for line in raw.splitlines():
        # window行: "window window:N <UUID> ..."
        win_match = re.match(r"window\s+window:\d+\s+([0-9A-F-]+)", line, re.IGNORECASE)
        if win_match:
            if current_win_uuid and matched:
                windows_to_close.append(current_win_uuid)
            current_win_uuid = win_match.group(1)
            matched = False
            continue
        # workspace行のタイトルをチェック
        for title in title_set:
            if f'"{title}"' in line:
                matched = True
                break

    if current_win_uuid and matched:
        windows_to_close.append(current_win_uuid)

    return windows_to_close


def find_workspace_ids_by_titles(pane_titles: list[str]) -> dict[str, str]:
    """pane_titlesに一致するワークスペースの {title: workspace_id} を返す"""
    raw = get_tree_raw()
    title_set = set(pane_titles)
    result = {}
    for line in raw.splitlines():
        ws_match = re.search(r"(workspace:\d+)\s+\S+\s+\"([^\"]+)\"", line)
        if ws_match:
            ws_id = ws_match.group(1)
            ws_name = ws_match.group(2)
            if ws_name in title_set:
                result[ws_name] = ws_id
    return result


# ── tmux ─────────────────────────────────────────────────

def tmux_session_exists(session: str) -> bool:
    _, rc = run(f"tmux has-session -t '{session}'")
    return rc == 0


def tmux_create_session(session: str, workdir: str):
    run(f"tmux new-session -d -s '{session}' -c '{workdir}'")


def is_process_running_in_tmux(session: str, process_name: str) -> bool:
    """tmuxセッションのpane PIDの子プロセスにclaude/codexがいるか確認"""
    pane_pid, rc = run(f"tmux list-panes -t '{session}' -F '#{{pane_pid}}'")
    if rc != 0 or not pane_pid:
        return False
    for pid in pane_pid.splitlines():
        children, _ = run(f"pgrep -P {pid}")
        for child_pid in children.splitlines():
            comm, _ = run(f"ps -p {child_pid} -o comm=")
            if process_name in comm:
                return True
    return False


def wait_for_prompt(ws_id: str, mode: str, timeout: int = 30) -> bool:
    """claude/codexのプロンプト表示を待つ"""
    prompt_indicators = {
        "claude": ["❯", "> ", "tips:"],
        "codex": ["❯", "> "],
    }
    indicators = prompt_indicators.get(mode, ["> "])
    for i in range(timeout):
        time.sleep(1.0)
        screen = cmux(f"read-screen --workspace {ws_id} --lines 30")
        if screen and any(ind in screen for ind in indicators):
            log(f"{mode} 起動完了 ({i + 1}s)")
            return True
    return False


# ── window ops ───────────────────────────────────────────

def close_existing_windows(pane_titles: list[str]):
    win_uuids = find_windows_containing_titles(pane_titles)
    for uuid in win_uuids:
        log(f"既存ウィンドウを閉じます: {uuid}")
        cmux(f"close-window --window {uuid}")
        time.sleep(0.5)


def resize_window(win_uuid: str):
    cmux(f"focus-window --window {win_uuid}")
    time.sleep(0.3)
    run(
        """osascript -e '
tell application "System Events"
    tell process "cmux"
        set frontWin to front window
        set position of frontWin to {100, 50}
        set size of frontWin to {1400, 750}
    end tell
end tell'"""
    )


# ── pane setup ───────────────────────────────────────────

def setup_pane(pane: dict, is_first: bool, before_ws: set[str], win_uuid: str) -> tuple[str | None, set[str]]:
    """ペインをセットアップし、(ws_id, 更新後のworkspace集合)を返す"""
    title = pane["title"]
    workdir = pane["workdir"]
    tmux_session = pane.get("tmux_session")
    mode = pane.get("mode", "plain")
    login_cmd = pane.get("login_cmd", "")

    log(f"--- {title} ---")

    if is_first:
        # new-windowのデフォルトワークスペースを差分で特定（既に新Window内にある）
        after_ws = get_workspace_ids()
        new_ws = after_ws - before_ws
        if not new_ws:
            log("ERROR: デフォルトワークスペース特定失敗")
            return None, after_ws
        ws_id = new_ws.pop()
    else:
        # new-workspaceは実行元Windowに作成されるため、作成後に新Windowへ移動
        before = get_workspace_ids()
        cmux("new-workspace")
        time.sleep(0.5)
        after = get_workspace_ids()
        new = after - before
        if not new:
            log(f"ERROR: ワークスペース作成失敗: {title}")
            return None, after
        ws_id = new.pop()
        cmux(f"move-workspace-to-window --workspace {ws_id} --window {win_uuid}")
        time.sleep(0.3)

    # リネーム
    cmux(f'rename-workspace --workspace {ws_id} "{title}"')

    # tmuxセットアップ or cd
    if tmux_session:
        if tmux_session_exists(tmux_session):
            log(f"tmux '{tmux_session}' exists -> attaching")
        else:
            log(f"tmux '{tmux_session}' not found -> creating")
            tmux_create_session(tmux_session, workdir)
        cmux(f'send --workspace {ws_id} "tmux attach-session -t {tmux_session}\n"')
        time.sleep(2.0)
    else:
        cmux(f'send --workspace {ws_id} "cd {workdir} && clear\n"')
        time.sleep(0.3)

    # claude/codexセットアップ
    if mode in ("claude", "codex") and login_cmd:
        running = False
        if tmux_session:
            running = is_process_running_in_tmux(tmux_session, mode)
        if running:
            log(f"{mode} already running -> skipping")
        else:
            log(f"Starting {mode}: {login_cmd}")
            cmux(f'send --workspace {ws_id} "{login_cmd}\n"')
            # claude起動完了を待つ（プロンプト表示まで）
            if not wait_for_prompt(ws_id, mode, timeout=30):
                log(f"WARNING: {mode} プロンプト待ちタイムアウト")
            # /remote-control 発行（新規起動時のみ）
            if mode == "claude" and "--remote-control-session-name-prefix" in login_cmd:
                log("Sending /remote-control")
                cmux(f'send --workspace {ws_id} "/remote-control\n"')
                time.sleep(1.0)

    log(f"OK: {title} ({ws_id})")
    return ws_id, get_workspace_ids()


# ── stop ─────────────────────────────────────────────────

def wait_for_process_exit(session: str, process_name: str, timeout: int = 15) -> bool:
    """プロセスが終了するまで待機（タイムアウト付き）"""
    for _ in range(timeout * 2):
        if not is_process_running_in_tmux(session, process_name):
            return True
        time.sleep(0.5)
    return False


def stop_pane(pane: dict, ws_id: str | None):
    """1つのペインを停止: claude exit → tmux kill"""
    title = pane["title"]
    tmux_session = pane.get("tmux_session")
    mode = pane.get("mode", "plain")

    log(f"--- {title} ---")

    # claude/codex exit
    if mode in ("claude", "codex") and tmux_session:
        if is_process_running_in_tmux(tmux_session, mode):
            if ws_id:
                log(f"{mode} exit送信")
                cmux(f'send --workspace {ws_id} "/exit\n"')
            else:
                # cmux workspaceがない場合、tmux経由で直接送信
                log(f"{mode} exit送信 (tmux直接)")
                run(f"tmux send-keys -t '{tmux_session}' '/exit' Enter")
            if wait_for_process_exit(tmux_session, mode):
                log(f"{mode} 終了確認")
            else:
                log(f"WARNING: {mode} 終了タイムアウト")
        else:
            log(f"{mode} 未起動")

    # tmux kill
    if tmux_session and tmux_session_exists(tmux_session):
        log(f"tmux '{tmux_session}' kill")
        run(f"tmux kill-session -t '{tmux_session}'")
    elif tmux_session:
        log(f"tmux '{tmux_session}' 未存在")

    log(f"OK: {title}")


def do_stop(win_config: dict, kill: bool = False):
    """Window定義に基づいて停止。kill=Trueでclaude/tmuxも終了"""
    panes = win_config.get("pane", [])
    pane_titles = [p["title"] for p in panes]
    label = "Killing" if kill else "Closing"

    print(f"=== {label}: {win_config['name']} ({len(panes)} panes) ===")

    if kill:
        # ワークスペースID取得（cmux上にあれば）
        ws_map = find_workspace_ids_by_titles(pane_titles)
        # 各ペインを停止（claude exit → tmux kill）
        for pane in panes:
            ws_id = ws_map.get(pane["title"])
            stop_pane(pane, ws_id)
            time.sleep(0.3)

    # cmuxウィンドウを閉じる
    win_uuids = find_windows_containing_titles(pane_titles)
    for uuid in win_uuids:
        log(f"ウィンドウ閉じます: {uuid}")
        cmux(f"close-window --window {uuid}")
        time.sleep(0.3)

    if not win_uuids:
        log("cmuxウィンドウなし")

    print(f"\n=== {label[:-3]}ed: {win_config['name']} ===")


# ── main ─────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="cmux workspace launcher")
    parser.add_argument("--name", help="起動するWindow名")
    parser.add_argument("--stop", action="store_true", help="Windowを停止（cmux windowのみ閉じる）")
    parser.add_argument("--kill", action="store_true", help="--stopと併用: claude/tmuxも終了")
    parser.add_argument("--list", action="store_true", help="定義一覧を表示")
    args = parser.parse_args()

    # cmux疎通確認
    if cmux("ping") != "PONG":
        print("ERROR: cmuxが起動していません")
        sys.exit(1)

    windows = load_all_windows()
    if not windows:
        print(f"ERROR: Window定義が見つかりません: {CONFIGS_DIR}")
        sys.exit(1)

    # 一覧表示
    if args.list:
        print("=== Window定義一覧 ===")
        for w in windows:
            default = " (default)" if w.get("default") else ""
            panes = w.get("pane", [])
            print(f"\n  {w['name']}{default}  [{w['_source']}]")
            for p in panes:
                tmux = f" tmux:{p['tmux_session']}" if p.get("tmux_session") else ""
                print(f"    - {p['title']}  [{p.get('mode', 'plain')}]{tmux}  {p['workdir']}")
        return

    # Window定義を検索
    win_config = find_window_config(windows, args.name)
    if not win_config:
        print(f"ERROR: Window '{args.name or '(default)'}' not found")
        sys.exit(1)

    # 停止
    if args.stop:
        do_stop(win_config, kill=args.kill)
        return

    panes = win_config.get("pane", [])
    if not panes:
        print(f"ERROR: Window '{win_config['name']}' にpane定義がありません")
        sys.exit(1)

    print(f"=== Launching: {win_config['name']} ({len(panes)} panes) ===")

    # 既存の同名ウィンドウを閉じる
    pane_titles = [p["title"] for p in panes]
    close_existing_windows(pane_titles)

    # ワークスペース一覧を記録（差分検出用）
    before_ws = get_workspace_ids()

    # 新ウィンドウ作成
    win_result = cmux("new-window")
    win_uuid = win_result.replace("OK ", "").strip()
    if not win_uuid:
        print("ERROR: ウィンドウ作成失敗")
        sys.exit(1)
    log(f"Window作成: {win_uuid}")
    time.sleep(0.8)

    # 各ペインをセットアップ
    current_ws = before_ws
    for i, pane in enumerate(panes):
        _, current_ws = setup_pane(pane, is_first=(i == 0), before_ws=current_ws, win_uuid=win_uuid)
        time.sleep(0.3)

    # ウィンドウをリサイズ
    resize_window(win_uuid)

    print(f"\n=== Done: {win_config['name']} ===")


if __name__ == "__main__":
    main()
