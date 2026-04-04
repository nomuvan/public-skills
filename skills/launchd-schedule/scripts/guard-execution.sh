#!/usr/bin/env bash
set -u

# guard-execution.sh — 全スケジュール共通の実行ガード
#
# launchdから呼ばれ、二重起動防止・cooldownチェック後に実コマンドを実行。
# 全モード（session/script/exec）で統一的に保護する。
#
# Usage:
#   guard-execution.sh <schedule-name> -- <command> [args...]
#
# Examples:
#   guard-execution.sh daily-patrol -- bash run-scheduled-prompt.sh patrol-session ...
#   guard-execution.sh research -- python3 src/researcher.py ai_tech
#   guard-execution.sh script-run -- bash run-scheduled-script.sh script-run ...

# --- 引数パース ---
SCHED_NAME="${1:?Usage: guard-execution.sh <name> -- <command> [args...]}"
shift

# "--" を読み飛ばし
if [ "${1:-}" = "--" ]; then
  shift
fi

EXEC_CMD=("$@")
if [ ${#EXEC_CMD[@]} -eq 0 ]; then
  echo "ERROR: No command specified after '--'" >&2
  exit 1
fi

LOG_DIR="$HOME/.local/share/harness-schedule/logs"
COOLDOWN_FILE="$HOME/.local/share/harness-schedule/.claude-cooldown"
mkdir -p "$LOG_DIR"

LOG_FILE="$LOG_DIR/${SCHED_NAME}-$(date +%Y%m%d-%H%M%S).log"

log() {
  echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# --- 1. psベース二重起動防止 ---
# 自分以外に同じスケジュール名でguard-execution.shが動いていたらスキップ
MY_PID=$$
RUNNING_PIDS=$(pgrep -f "guard-execution.sh ${SCHED_NAME}" 2>/dev/null | grep -v "^${MY_PID}$" || true)

if [ -n "$RUNNING_PIDS" ]; then
  log "=== SKIP: '${SCHED_NAME}' already running (PIDs: ${RUNNING_PIDS}) ==="
  exit 0
fi

# --- 2. Claude APIレートリミットcooldown ---
# execモード（Python等）では不要だが、チェック自体は軽いので統一的に実行
if [ -f "$COOLDOWN_FILE" ]; then
  cooldown_data=$(head -1 "$COOLDOWN_FILE" 2>/dev/null || true)
  if [ -n "$cooldown_data" ]; then
    # run-scheduled-script.sh形式: epoch|iso|label|message
    # run-strategy.sh形式: ISO8601のみ
    cooldown_epoch=$(echo "$cooldown_data" | cut -d'|' -f1)

    # epochが数字かチェック
    if [[ "$cooldown_epoch" =~ ^[0-9]+$ ]]; then
      now_epoch=$(date +%s)
      if [ "$now_epoch" -lt "$cooldown_epoch" ]; then
        cooldown_iso=$(echo "$cooldown_data" | cut -d'|' -f2)
        log "=== SKIP: Claude cooldown active until ${cooldown_iso:-$cooldown_epoch} ==="
        exit 0
      fi
      rm -f "$COOLDOWN_FILE"
    else
      # ISO8601形式の場合
      until_epoch=$(date -j -f "%Y-%m-%dT%H:%M:%S%z" "$cooldown_data" +%s 2>/dev/null || echo 0)
      now_epoch=$(date +%s)
      if [ "$now_epoch" -lt "$until_epoch" ]; then
        log "=== SKIP: Claude cooldown active until $cooldown_data ==="
        exit 0
      fi
      rm -f "$COOLDOWN_FILE"
    fi
  fi
fi

# --- 3. 実行 ---
log "=== Guard: '${SCHED_NAME}' start (PID=$$) ==="
log "Command: ${EXEC_CMD[*]}"

"${EXEC_CMD[@]}" 2>&1 | tee -a "$LOG_FILE"
EXIT_CODE=${PIPESTATUS[0]}

log "=== Guard: '${SCHED_NAME}' complete (exit=${EXIT_CODE}) ==="
