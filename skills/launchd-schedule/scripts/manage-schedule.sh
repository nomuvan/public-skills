#!/usr/bin/env bash
set -euo pipefail

# manage-schedule.sh — launchdスケジュールの登録・一覧・変更・削除
#
# Usage:
#   manage-schedule.sh create <name> <cron-expr> <session> <workdir> <claude-cmd> <prompt>
#   manage-schedule.sh list
#   manage-schedule.sh update <name> <cron-expr>
#   manage-schedule.sh delete <name>

PLIST_DIR="$HOME/Library/LaunchAgents"
LABEL_PREFIX="com.harness-schedule"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUNNER="$SCRIPT_DIR/run-scheduled-prompt.sh"

# cron式(m h dom mon dow)をlaunchdのStartCalendarIntervalに変換
cron_to_plist_interval() {
  local cron_expr="$1"
  local minute hour day month weekday
  read -r minute hour day month weekday <<< "$cron_expr"

  # */N 形式の検出 → launchdのStartInterval(秒)に変換
  # launchdのStartCalendarIntervalは*/Nを理解しない
  if [[ "$minute" == *"/"* ]]; then
    local step="${minute##*/}"
    local seconds=$((step * 60))
    echo "    <key>StartInterval</key>"
    echo "    <integer>${seconds}</integer>"
    return
  fi
  if [[ "$hour" == *"/"* ]]; then
    local step="${hour##*/}"
    local seconds=$((step * 3600))
    echo "    <key>StartInterval</key>"
    echo "    <integer>${seconds}</integer>"
    return
  fi

  echo "    <key>StartCalendarInterval</key>"

  # 複数エントリが必要な場合(カンマ区切り)は配列にする
  if [[ "$minute" == *","* ]] || [[ "$hour" == *","* ]]; then
    echo "    <array>"
    echo "    <dict>"
    [ "$minute" != "*" ] && echo "        <key>Minute</key><integer>$minute</integer>"
    [ "$hour" != "*" ] && echo "        <key>Hour</key><integer>$hour</integer>"
    [ "$day" != "*" ] && echo "        <key>Day</key><integer>$day</integer>"
    [ "$month" != "*" ] && echo "        <key>Month</key><integer>$month</integer>"
    [ "$weekday" != "*" ] && echo "        <key>Weekday</key><integer>$weekday</integer>"
    echo "    </dict>"
    echo "    </array>"
  else
    echo "    <dict>"
    [ "$minute" != "*" ] && echo "        <key>Minute</key><integer>$minute</integer>"
    [ "$hour" != "*" ] && echo "        <key>Hour</key><integer>$hour</integer>"
    [ "$day" != "*" ] && echo "        <key>Day</key><integer>$day</integer>"
    [ "$month" != "*" ] && echo "        <key>Month</key><integer>$month</integer>"
    [ "$weekday" != "*" ] && echo "        <key>Weekday</key><integer>$weekday</integer>"
    echo "    </dict>"
  fi
}

create_schedule() {
  local name="$1"
  local cron_expr="$2"
  local session="$3"
  local workdir="$4"
  local claude_cmd="$5"
  local prompt="$6"
  local mode="${7:-session}"  # session | script | exec

  local label="${LABEL_PREFIX}.${name}"
  local plist_file="${PLIST_DIR}/${label}.plist"
  local log_dir="$HOME/.local/share/harness-schedule/logs"

  mkdir -p "$log_dir"

  if [ -f "$plist_file" ]; then
    echo "ERROR: Schedule '$name' already exists. Use 'update' or 'delete' first."
    return 1
  fi

  local interval
  interval=$(cron_to_plist_interval "$cron_expr")

  # プロジェクト名をworkdirから自動取得
  local project_name
  project_name=$(basename "$workdir")

  # --- 全モード共通: guard-execution.sh 経由でplist生成 ---
  local guard_script="$SCRIPT_DIR/guard-execution.sh"

  # モード別の実コマンドを組み立て
  local inner_cmd_args=""
  if [ "$mode" = "exec" ]; then
    # execモード: 任意コマンドを直接実行
    local exec_cmd="$claude_cmd"
    [ -n "${prompt:-}" ] && exec_cmd="$exec_cmd $prompt"
    # bash -c で実行（cd含む）
    local exec_cmd_escaped="${exec_cmd//&/&amp;}"
    inner_cmd_args="        <string>/bin/bash</string>
        <string>-c</string>
        <string>cd ${workdir} &amp;&amp; ${exec_cmd_escaped}</string>"
  elif [ "$mode" = "script" ]; then
    # scriptモード: run-scheduled-script.sh 経由でClaude -p実行
    local prompt_dir="$HOME/.local/share/harness-schedule/prompts"
    mkdir -p "$prompt_dir"
    echo "$prompt" > "$prompt_dir/${name}.txt"
    inner_cmd_args="        <string>/bin/bash</string>
        <string>$SCRIPT_DIR/run-scheduled-script.sh</string>
        <string>${name}</string>
        <string>${session}</string>
        <string>${workdir}</string>
        <string>${claude_cmd}</string>
        <string>${prompt}</string>"
  else
    # sessionモード: run-scheduled-prompt.sh 経由でClaude対話
    local prompt_dir="$HOME/.local/share/harness-schedule/prompts"
    mkdir -p "$prompt_dir"
    echo "$prompt" > "$prompt_dir/${name}.txt"
    inner_cmd_args="        <string>/bin/bash</string>
        <string>$RUNNER</string>
        <string>${session}</string>
        <string>${workdir}</string>
        <string>${claude_cmd}</string>
        <string>${prompt}</string>"
  fi

  cat > "$plist_file" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${guard_script}</string>
        <string>${name}</string>
        <string>--</string>
${inner_cmd_args}
    </array>
${interval}
    <key>StandardOutPath</key>
    <string>${log_dir}/${name}-stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${log_dir}/${name}-stderr.log</string>
    <key>WorkingDirectory</key>
    <string>${workdir}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin:$HOME/.local/bin:$HOME/.nodenv/shims:$HOME/.pyenv/shims</string>
        <key>HOME</key>
        <string>$HOME</string>
        <key>SCHEDULE_PROJECT</key>
        <string>${project_name}</string>
        <key>SCHEDULE_MODE</key>
        <string>${mode}</string>
    </dict>
</dict>
</plist>
PLIST

  launchctl bootstrap "gui/$(id -u)" "$plist_file" 2>/dev/null \
    || launchctl load "$plist_file"
  echo "Created schedule '$name' ($cron_expr) [mode: $mode]"
  echo "  Label: $label"
  echo "  Plist: $plist_file"
  if [ "$mode" = "exec" ]; then
    echo "  Command: $exec_cmd"
    echo "  Workdir: $workdir"
  else
    echo "  Session: $session | Workdir: $workdir"
  fi
}

list_schedules() {
  local filter_project="${1:-}"
  local current_project
  current_project=$(basename "$(pwd)")

  if [ "$filter_project" = "--all" ]; then
    echo "=== harness-schedule 一覧（全プロジェクト） ==="
    filter_project=""
  elif [ -z "$filter_project" ]; then
    echo "=== harness-schedule 一覧（${current_project}） ==="
    filter_project="$current_project"
  else
    echo "=== harness-schedule 一覧（${filter_project}） ==="
  fi

  local found=false
  for plist in "$PLIST_DIR"/${LABEL_PREFIX}.*.plist; do
    [ -f "$plist" ] || continue

    local label
    label=$(defaults read "$plist" Label 2>/dev/null)
    local name="${label#${LABEL_PREFIX}.}"

    # プロジェクト名を取得
    local project
    project=$(defaults read "$plist" EnvironmentVariables 2>/dev/null | grep "SCHEDULE_PROJECT" | sed 's/.*= *"\{0,1\}\([^";]*\)"\{0,1\}.*/\1/' || echo "unknown")

    # フィルタ適用
    if [ -n "$filter_project" ] && [ "$project" != "$filter_project" ]; then
      continue
    fi

    found=true

    local status
    if launchctl list "$label" >/dev/null 2>&1; then
      status="active"
    else
      status="inactive"
    fi

    echo ""
    echo "  Name: $name"
    echo "  Project: $project"
    echo "  Status: $status"
    echo "  Label: $label"
    echo "  Plist: $plist"
  done

  if [ "$found" = false ]; then
    if [ -n "$filter_project" ]; then
      echo "  (${filter_project}のスケジュールなし。--all で全プロジェクト表示)"
    else
      echo "  (スケジュールなし)"
    fi
  fi

  # ゴーストジョブ検出: launchdにロード済みだがplistが存在しないジョブ
  local ghosts=()
  while IFS=$'\t' read -r _pid _status label; do
    [ -z "$label" ] && continue
    [[ "$label" != ${LABEL_PREFIX}.* ]] && continue
    local ghost_plist="${PLIST_DIR}/${label}.plist"
    if [ ! -f "$ghost_plist" ]; then
      ghosts+=("$label")
    fi
  done < <(launchctl list 2>/dev/null | grep "${LABEL_PREFIX}\.")

  if [ ${#ghosts[@]} -gt 0 ]; then
    echo ""
    echo "=== ゴーストジョブ（plistなし・launchdに残留） ==="
    for g in "${ghosts[@]}"; do
      local ghost_name="${g#${LABEL_PREFIX}.}"
      echo "  WARNING: $ghost_name ($g)"
      echo "    → 'manage-schedule.sh delete $ghost_name' で削除可能"
    done
  fi
}

update_schedule() {
  local name="$1"
  local cron_expr="$2"

  local label="${LABEL_PREFIX}.${name}"
  local plist_file="${PLIST_DIR}/${label}.plist"

  if [ ! -f "$plist_file" ]; then
    echo "ERROR: Schedule '$name' not found."
    return 1
  fi

  # unload → plist書き換え → reload
  launchctl bootout "gui/$(id -u)/${label}" 2>/dev/null \
    || launchctl unload "$plist_file" 2>/dev/null || true

  # StartCalendarIntervalを置換
  local interval
  interval=$(cron_to_plist_interval "$cron_expr")

  # pythonでplist編集（sedでXML編集は危険）
  python3 << PYEOF
import plistlib, sys

with open("$plist_file", "rb") as f:
    plist = plistlib.load(f)

parts = "$cron_expr".split()
cal = {}
if parts[0] != "*": cal["Minute"] = int(parts[0])
if parts[1] != "*": cal["Hour"] = int(parts[1])
if parts[2] != "*": cal["Day"] = int(parts[2])
if parts[3] != "*": cal["Month"] = int(parts[3])
if parts[4] != "*": cal["Weekday"] = int(parts[4])

plist["StartCalendarInterval"] = cal

with open("$plist_file", "wb") as f:
    plistlib.dump(plist, f)
PYEOF

  launchctl bootstrap "gui/$(id -u)" "$plist_file" 2>/dev/null \
    || launchctl load "$plist_file"
  echo "Updated schedule '$name' to: $cron_expr"
}

delete_schedule() {
  local name="$1"
  local label="${LABEL_PREFIX}.${name}"
  local plist_file="${PLIST_DIR}/${label}.plist"

  local had_plist=false
  [ -f "$plist_file" ] && had_plist=true

  # launchdから確実に削除（plist有無に関わらず）
  launchctl bootout "gui/$(id -u)/${label}" 2>/dev/null \
    || launchctl unload "$plist_file" 2>/dev/null \
    || launchctl remove "$label" 2>/dev/null \
    || true

  # plist・プロンプトファイルを削除
  rm -f "$plist_file"
  rm -f "$HOME/.local/share/harness-schedule/prompts/${name}.txt"

  if [ "$had_plist" = true ]; then
    echo "Deleted schedule '$name'"
  else
    # plistなしでもlaunchdから削除を試みた（ゴースト対応）
    echo "Cleaned up ghost schedule '$name' (plist was already missing)"
  fi
}

run_now() {
  local name="$1"
  local label="${LABEL_PREFIX}.${name}"
  local plist_file="${PLIST_DIR}/${label}.plist"

  if [ ! -f "$plist_file" ]; then
    echo "ERROR: Schedule '$name' not found."
    return 1
  fi

  echo "Running schedule '$name' immediately..."

  # plistからProgramArgumentsを読み取り、そのまま実行
  # guard-execution.sh経由なので二重起動防止も効く
  local args
  args=$(python3 -c "
import plistlib
with open('$plist_file', 'rb') as f:
    plist = plistlib.load(f)
for a in plist['ProgramArguments'][1:]:
    print(a)
" 2>/dev/null)

  if [ -z "$args" ]; then
    echo "ERROR: Failed to parse plist arguments."
    return 1
  fi

  local script_args=()
  while IFS= read -r line; do
    script_args+=("$line")
  done <<< "$args"

  echo "  Guard: ${script_args[0]}"
  echo "  Schedule: $name"
  echo ""
  bash "${script_args[@]}"
}

# メインディスパッチ
case "${1:-help}" in
  create)
    shift
    create_schedule "$@"
    ;;
  list)
    shift
    list_schedules "${1:-}"
    ;;
  update)
    shift
    update_schedule "$@"
    ;;
  delete)
    shift
    delete_schedule "$@"
    ;;
  run)
    shift
    run_now "$@"
    ;;
  *)
    echo "Usage:"
    echo "  $0 create <name> <cron-expr> <session> <workdir> <cmd> <prompt> [session|script|exec]"
    echo "  $0 list [--all|<project>]"
    echo "  $0 update <name> <cron-expr>"
    echo "  $0 delete <name>"
    echo "  $0 run <name>"
    echo ""
    echo "Modes:"
    echo "  session  Claude CLI対話モード（デフォルト）"
    echo "  script   Claude CLI -p モード"
    echo "  exec     任意コマンド実行（Claude不要）"
    echo ""
    echo "Examples:"
    echo "  $0 create patrol '0 3 * * *' harness-patrol /path 'claude --dangerously-skip-permissions' '/patrol'"
    echo "  $0 create research '0 6 * * *' '' /path 'python3 src/researcher.py' 'ai_tech' exec"
    echo "  $0 run patrol"
    ;;
esac
