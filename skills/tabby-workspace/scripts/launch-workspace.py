#!/usr/bin/env python3
"""
tabby-workspace launcher
WSL tmux + Tabby でマルチペインワークスペースを起動・停止する。
"""

import argparse
import glob
import json
import os
import platform
import subprocess
import sys
import time
import tomllib
import uuid
import urllib.request

import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))
WORKSPACES_DIR = os.path.join(PROJECT_ROOT, "workspaces")
TABBY_EXE = os.path.join(
    os.environ.get("LOCALAPPDATA", r"C:\Users\nomuv\AppData\Local"),
    "Programs", "Tabby", "Tabby.exe",
)
TABBY_CONFIG = os.path.join(
    os.environ.get("APPDATA", r"C:\Users\nomuv\AppData\Roaming"),
    "tabby", "config.yaml",
)
TABBY_MCP_URL = "http://localhost:3001/api/tool"


def mcp_call(tool, params=None):
    """Call a Tabby-MCP API tool and return parsed result."""
    url = f"{TABBY_MCP_URL}/{tool}"
    data = json.dumps(params or {}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            text = body.get("content", [{}])[0].get("text", "{}")
            return json.loads(text)
    except Exception as e:
        return {"success": False, "error": str(e)}


def mcp_available():
    """Check if Tabby-MCP server is running."""
    try:
        req = urllib.request.Request(f"http://localhost:3001/health")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def run(cmd, check=True, capture=True, timeout=30):
    """Run a command and return stdout."""
    try:
        r = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=check,
            timeout=timeout,
            shell=isinstance(cmd, str),
        )
        if capture and r.stdout:
            return r.stdout.strip()
        return ""
    except subprocess.CalledProcessError as e:
        if capture and e.stdout:
            return e.stdout.strip()
        return ""
    except subprocess.TimeoutExpired:
        return ""


def wsl_tmux(*args):
    """Execute a tmux command via WSL."""
    return run(["wsl.exe", "-e", "tmux"] + list(args), check=False)


def tmux_session_exists(name):
    """Check if a tmux session exists."""
    r = subprocess.run(
        ["wsl.exe", "-e", "tmux", "has-session", "-t", name],
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    return r.returncode == 0


def tmux_list_sessions():
    """List all tmux sessions."""
    output = wsl_tmux("ls", "-F", "#{session_name}")
    if not output:
        return []
    return [s.strip() for s in output.splitlines() if s.strip()]


def tmux_create_session(name):
    """Create a new detached tmux session."""
    print(f"  Creating tmux session: {name}")
    wsl_tmux("new-session", "-d", "-s", name)


def tmux_send_keys(session, keys, enter=True):
    """Send keys to a tmux session."""
    if enter:
        wsl_tmux("send-keys", "-t", session, keys, "C-m")
    else:
        wsl_tmux("send-keys", "-t", session, keys)


def tmux_read_screen(session, lines=50):
    """Read the current screen content of a tmux session."""
    return wsl_tmux("capture-pane", "-t", session, "-p", "-S", f"-{lines}")


def tmux_kill_session(name):
    """Kill a tmux session."""
    print(f"  Killing tmux session: {name}")
    wsl_tmux("kill-session", "-t", name)


def win_path_to_ps(path):
    """Ensure Windows path uses backslashes for PowerShell."""
    return path.replace("/", "\\")


def win_path_to_wsl(path):
    """Convert a Windows path to WSL path (e.g., C:\\Users\\... -> /mnt/c/Users/...)."""
    path = path.replace("\\", "/")
    # Handle drive letter: C:/... -> /mnt/c/...
    if len(path) >= 2 and path[1] == ":":
        drive = path[0].lower()
        path = f"/mnt/{drive}{path[2:]}"
    return path


def load_workspace_configs():
    """Load all workspace TOML configs from workspaces/ directory."""
    configs = []
    pattern = os.path.join(WORKSPACES_DIR, "*.toml")
    for filepath in glob.glob(pattern):
        with open(filepath, "rb") as f:
            config = tomllib.load(f)
        config["_filepath"] = filepath
        configs.append(config)
    return configs


def find_workspace(configs, name=None, machine_filter=None):
    """Find a workspace window definition by name or default. Returns (window, machine).

    When machine_filter is set, only configs matching that machine are considered.
    If no match, falls back to all configs.
    """
    # If no explicit machine_filter, auto-detect from hostname
    if machine_filter is None:
        machine_filter = platform.node().lower()

    def _search(cfgs):
        for config in cfgs:
            machine = config.get("machine", "")
            for window in config.get("window", []):
                if name and window.get("name") == name:
                    return window, machine
                if not name and window.get("default", False):
                    return window, machine
        if not name:
            for config in cfgs:
                machine = config.get("machine", "")
                windows = config.get("window", [])
                if windows:
                    return windows[0], machine
        return None, ""

    # Try machine-filtered configs first
    if machine_filter:
        filtered = [c for c in configs if c.get("machine", "").lower() == machine_filter]
        if filtered:
            result = _search(filtered)
            if result[0] is not None:
                return result

    # Fallback to all configs
    return _search(configs)


def is_claude_or_codex_running(session):
    """Check if claude or codex is running in a tmux session by reading screen content."""
    screen = tmux_read_screen(session, lines=5)
    if not screen:
        return False
    # Look for common claude/codex prompt indicators
    indicators = [
        "claude>",
        "Claude Code",
        "\u276f",  # ❯ claude prompt (heavy right-pointing angle)
        ">",  # claude prompt (ascii fallback)
        "codex>",
        "What can I help you with?",
        "Tips:",
        "bypass permissions",
    ]
    for indicator in indicators:
        if indicator in screen:
            return True
    return False


def wait_for_prompt(session, timeout=60):
    """Wait for a claude/codex prompt to appear in the tmux session."""
    print(f"    Waiting for prompt in {session}...", end="", flush=True)
    start = time.time()
    while time.time() - start < timeout:
        screen = tmux_read_screen(session, lines=10)
        if screen:
            # Claude Code prompt indicators
            if any(ind in screen for ind in [
                "What can I help",
                "Tips:",
                "claude>",
                "\u276f",  # ❯
                "bypass permissions",
            ]):
                print(" ready!")
                return True
        time.sleep(2)
        print(".", end="", flush=True)
    print(" timeout!")
    return False


def setup_pane(pane, machine=""):
    """Set up a single pane: create tmux session, send commands, open Tabby tab."""
    title = pane["title"]
    workdir = pane["workdir"]
    tmux_session = pane.get("tmux_session")
    mode = pane.get("mode", "plain")
    login_cmd = pane.get("login_cmd", "").replace("{machine}", machine)

    print(f"\n[{title}]")

    if not tmux_session:
        print(f"  No tmux_session specified, skipping tmux setup")
        return

    # Create tmux session if it doesn't exist
    existing = tmux_list_sessions()
    if tmux_session in existing:
        print(f"  tmux session '{tmux_session}' already exists")
        # Check if claude/codex is already running
        if mode in ("claude", "codex") and is_claude_or_codex_running(tmux_session):
            print(f"  {mode} already running in session")
            open_tabby_tab(tmux_session, title)
            return
    else:
        tmux_create_session(tmux_session)
        time.sleep(0.5)

    # Set tmux window title for Tabby tab display
    wsl_tmux("rename-window", "-t", tmux_session, title)

    # Send working directory change via PowerShell
    ps_workdir = win_path_to_ps(workdir)
    if mode in ("claude", "codex"):
        # For claude/codex: launch PowerShell with workdir and login command
        ps_cmd = f"powershell.exe -NoProfile -Command \"Set-Location '{ps_workdir}'; {login_cmd}\""
        print(f"  Launching {mode}: {login_cmd[:80]}...")
        tmux_send_keys(tmux_session, ps_cmd)
        time.sleep(1)

        # Wait for prompt
        wait_for_prompt(tmux_session, timeout=60)

        # If login_cmd contains --remote-control-session-name-prefix, send /remote-control
        if "--remote-control-session-name-prefix" in login_cmd:
            print(f"  Sending /remote-control")
            time.sleep(1)
            tmux_send_keys(tmux_session, "/remote-control")
            time.sleep(2)
    else:
        # Plain mode: just cd to workdir
        ps_cmd = f"powershell.exe -NoProfile -Command \"Set-Location '{ps_workdir}'\""
        tmux_send_keys(tmux_session, ps_cmd)

    # Open Tabby tab for this session
    open_tabby_tab(tmux_session, title)


def load_tabby_config():
    """Load Tabby config.yaml."""
    with open(TABBY_CONFIG, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_tabby_config(config):
    """Save Tabby config.yaml."""
    with open(TABBY_CONFIG, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def ensure_tabby_profile(tmux_session, title):
    """Ensure a Tabby profile exists for this tmux session. Returns profile name."""
    profile_name = f"tmux:{title}"
    profile_id = f"local:custom:tmux-{tmux_session}"
    attach_cmd = os.path.join(PROJECT_ROOT, "scripts", "tmux-attach.cmd")
    attach_cmd_win = win_path_to_ps(attach_cmd)

    config = load_tabby_config()
    profiles = config.get("profiles", [])

    # Check if profile already exists
    for p in profiles:
        if p.get("id") == profile_id:
            return profile_name

    # Create new profile
    profile = {
        "type": "local",
        "name": profile_name,
        "options": {
            "command": attach_cmd_win,
            "args": [tmux_session, title],
            "env": {},
            "cwd": None,
            "pauseAfterExit": False,
        },
        "behaviorOnSessionEnd": "close",
        "id": profile_id,
        "disableDynamicTitle": True,
    }
    profiles.append(profile)
    config["profiles"] = profiles
    save_tabby_config(config)
    return profile_name


def remove_tabby_profiles():
    """Remove all tmux workspace profiles from Tabby config."""
    config = load_tabby_config()
    profiles = config.get("profiles", [])
    config["profiles"] = [p for p in profiles if not str(p.get("id", "")).startswith("local:custom:tmux-")]
    save_tabby_config(config)


def open_tabby_tab(tmux_session, title):
    """Open a Tabby tab that attaches to a WSL tmux session."""
    if not os.path.exists(TABBY_EXE):
        print(f"  WARNING: Tabby not found at {TABBY_EXE}, skipping tab creation")
        return

    tab_title = f"tmux:{title}"
    print(f"  Opening Tabby tab for session '{tmux_session}'")
    if mcp_available():
        # Open WSL tab via MCP, then send tmux attach command
        result = mcp_call("open_profile", {
            "profileId": "local:wsl",
            "waitForReady": True,
            "timeout": 30000,
        })
        if result.get("success"):
            sid = result.get("sessionId", "")
            # Set terminal title BEFORE tmux attach (tmux won't override if set-titles is off)
            mcp_call("send_input", {
                "sessionId": sid,
                "input": f"printf '\\033]0;{tab_title}\\007'; tmux attach -t {tmux_session}\r",
            })
            time.sleep(0.5)
            print(f"    MCP: opened tab '{tab_title}'")
        else:
            print(f"    MCP: failed ({result.get('error', 'unknown')}), fallback to CLI")
            _open_tabby_tab_cli(tmux_session, title)
    else:
        _open_tabby_tab_cli(tmux_session, title)


def _close_tabby_tab(tmux_session, title):
    """Close Tabby tab associated with a tmux session."""
    tab_title = f"tmux:{title}"
    if mcp_available():
        result = mcp_call("close_tab", {"title": tab_title})
        if result.get("success"):
            print(f" tab closed.", end="")
            return
    # Fallback: detach tmux client
    wsl_tmux("detach-client", "-s", tmux_session)
    time.sleep(0.5)


def _open_tabby_tab_cli(tmux_session, title):
    """Fallback: Open Tabby tab via CLI."""
    attach_cmd = os.path.join(PROJECT_ROOT, "scripts", "tmux-attach.cmd")
    attach_cmd_win = win_path_to_ps(attach_cmd)
    cmd = [TABBY_EXE, "run", attach_cmd_win, tmux_session, title]
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
    except Exception as e:
        print(f"  WARNING: Failed to open Tabby tab: {e}")


def do_launch(workspace_name=None):
    """Launch a workspace."""
    configs = load_workspace_configs()
    if not configs:
        print(f"ERROR: No workspace configs found in {WORKSPACES_DIR}")
        sys.exit(1)

    window, machine = find_workspace(configs, workspace_name)
    if not window:
        print(f"ERROR: Workspace '{workspace_name}' not found")
        available = []
        for c in configs:
            for w in c.get("window", []):
                available.append(w.get("name", "unnamed"))
        print(f"Available: {', '.join(available)}")
        sys.exit(1)

    name = window.get("name", "unnamed")
    panes = window.get("pane", [])
    print(f"Launching workspace: {name} (machine={machine}, {len(panes)} panes)")

    # Disable tmux set-titles so it doesn't override our tab titles
    wsl_tmux("set-option", "-g", "set-titles", "off")

    for pane in panes:
        setup_pane(pane, machine=machine)

    print(f"\nWorkspace '{name}' launched successfully!")
    print(f"tmux sessions:")
    for s in tmux_list_sessions():
        print(f"  - {s}")


def do_stop(workspace_name=None, kill=False):
    """Stop a workspace."""
    configs = load_workspace_configs()
    window, machine = find_workspace(configs, workspace_name)
    if not window:
        print(f"ERROR: Workspace '{workspace_name or 'default'}' not found")
        sys.exit(1)

    name = window.get("name", "unnamed")
    panes = window.get("pane", [])
    existing = tmux_list_sessions()

    print(f"Stopping workspace: {name}")

    for pane in panes:
        title = pane["title"]
        tmux_session = pane.get("tmux_session")
        mode = pane.get("mode", "plain")

        if not tmux_session or tmux_session not in existing:
            print(f"  [{title}] tmux session '{tmux_session}' not found, skipping")
            continue

        print(f"  [{title}]", end="")

        if kill:
            # Send /exit to claude/codex first
            if mode in ("claude", "codex"):
                print(f" sending /exit...", end="")
                tmux_send_keys(tmux_session, "/exit")
                # Wait for process to exit
                for _ in range(15):
                    time.sleep(1)
                    if not is_claude_or_codex_running(tmux_session):
                        break
                print(f" exited.", end="")

            # Close Tabby tab via MCP or detach tmux client
            _close_tabby_tab(tmux_session, title)

            # Kill tmux session
            tmux_kill_session(tmux_session)
            print(f" killed.")
        else:
            # Close Tabby tab but preserve tmux session
            _close_tabby_tab(tmux_session, title)
            print(f" tmux preserved.")

    if not kill:
        print(f"\ntmuxセッションは維持されています。再起動で再アタッチされます。")
    else:
        print(f"\nWorkspace '{name}' stopped and killed.")


def do_list():
    """List available workspaces and current tmux sessions."""
    configs = load_workspace_configs()
    existing = tmux_list_sessions()

    print("=== Available Workspaces ===")
    for config in configs:
        filepath = config.get("_filepath", "unknown")
        machine = config.get("machine", "")
        machine_label = f" [machine={machine}]" if machine else ""
        for window in config.get("window", []):
            name = window.get("name", "unnamed")
            is_default = window.get("default", False)
            panes = window.get("pane", [])
            default_mark = " [default]" if is_default else ""
            print(f"\n  {name}{default_mark}{machine_label} ({os.path.basename(filepath)})")
            for pane in panes:
                title = pane["title"]
                session = pane.get("tmux_session", "-")
                mode = pane.get("mode", "plain")
                status = "ACTIVE" if session in existing else "inactive"
                print(f"    - {title} ({mode}) tmux={session} [{status}]")

    print(f"\n=== Active tmux Sessions ===")
    if existing:
        for s in existing:
            print(f"  - {s}")
    else:
        print("  (none)")


def main():
    parser = argparse.ArgumentParser(description="tabby-workspace launcher")
    parser.add_argument("--workspace", "-w", help="Workspace name (default: use default workspace)")
    parser.add_argument("--stop", action="store_true", help="Stop the workspace")
    parser.add_argument("--kill", action="store_true", help="Kill tmux sessions (use with --stop)")
    parser.add_argument("--list", "-l", action="store_true", help="List workspaces and sessions")
    args = parser.parse_args()

    if args.list:
        do_list()
    elif args.stop:
        do_stop(args.workspace, kill=args.kill)
    else:
        do_launch(args.workspace)


if __name__ == "__main__":
    main()
