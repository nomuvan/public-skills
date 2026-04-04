#!/usr/bin/env bash
set -euo pipefail

# run-scheduled-script.sh — tmux上でClaude CLIスクリプトモード実行（セッションに入らない）
#
# 既存の run-scheduled-prompt.sh（sessionモード）との違い:
#   - Claudeセッションに入らず `claude -p "prompt"` でバッチ実行
#   - 実行完了後にtmuxセッションは自動終了
#   - 二重起動防止はguard-execution.shが担当
#
# 引数:
#   $1 — スケジュール名（ログ識別に使用）
#   $2 — tmuxセッション名
#   $3 — ワークディレクトリ
#   $4 — claudeコマンドライン（例: claude --dangerously-skip-permissions）
#   $5 — 実行するプロンプト

SCHED_NAME="${1:?スケジュール名が必要です}"
SESSION="${2:?セッション名が必要です}"
WORKDIR="${3:?ワークディレクトリが必要です}"
CLAUDE_CMD="${4:-claude --dangerously-skip-permissions}"
PROMPT="${5:?プロンプトが必要です}"

LOG_DIR="$HOME/.local/share/harness-schedule/logs"
STATE_DIR="$HOME/.local/share/harness-schedule"
COOLDOWN_FILE="$STATE_DIR/claude-rate-limit-cooldown"
mkdir -p "$LOG_DIR" "$STATE_DIR"

LOG_FILE="$LOG_DIR/${SCHED_NAME}-$(date +%Y%m%d-%H%M%S).log"

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG_FILE"; }

parse_rate_limit_reset() {
  local line="$1"

  python3 - "$line" <<'PYEOF'
import datetime as dt
import re
import sys

line = sys.argv[1]
match = re.search(r"resets\s+([0-9]{1,2}(?::[0-9]{2})?\s*[ap]m)\s+\(Asia/Tokyo\)", line, re.IGNORECASE)
if not match:
    sys.exit(1)

label = match.group(1).replace(" ", "").lower()
time_match = re.fullmatch(r"([0-9]{1,2})(?::([0-9]{2}))?(am|pm)", label)
if not time_match:
    sys.exit(1)

hour = int(time_match.group(1))
minute = int(time_match.group(2) or "0")
meridiem = time_match.group(3)

if meridiem == "pm" and hour != 12:
    hour += 12
elif meridiem == "am" and hour == 12:
    hour = 0

tokyo = dt.timezone(dt.timedelta(hours=9))
now = dt.datetime.now(tokyo)
reset_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
if reset_at <= now:
    reset_at += dt.timedelta(days=1)

print(f"{int(reset_at.timestamp())}|{reset_at.isoformat()}|{label}")
PYEOF
}

write_rate_limit_cooldown() {
  local line="$1"
  local parsed
  parsed=$(parse_rate_limit_reset "$line" 2>/dev/null || true)
  [ -n "$parsed" ] || return 0

  local until_epoch until_iso until_label
  IFS='|' read -r until_epoch until_iso until_label <<< "$parsed"
  printf '%s|%s|%s|%s\n' "$until_epoch" "$until_iso" "$until_label" "$line" > "$COOLDOWN_FILE"
  log "Rate limit detected. Future Claude runs will be skipped until $until_iso ($until_label, Asia/Tokyo)."
}

check_rate_limit_cooldown() {
  [ -f "$COOLDOWN_FILE" ] || return 0

  local until_epoch until_iso until_label
  IFS='|' read -r until_epoch until_iso until_label _ < "$COOLDOWN_FILE" || true

  if ! [[ "${until_epoch:-}" =~ ^[0-9]+$ ]]; then
    rm -f "$COOLDOWN_FILE"
    return 0
  fi

  local now_epoch
  now_epoch=$(date +%s)

  if [ "$now_epoch" -lt "$until_epoch" ]; then
    log "=== SKIP: global Claude cooldown active until $until_iso ($until_label, Asia/Tokyo) ==="
    exit 0
  fi

  rm -f "$COOLDOWN_FILE"
}

check_rate_limit_cooldown

# 二重起動防止はguard-execution.shが担当（このスクリプトの呼び出し元）

log "=== Script Schedule Start: $SCHED_NAME ==="
log "Workdir: $WORKDIR | Cmd: $CLAUDE_CMD"
log "Mode: script (non-interactive) | PID: $$"

# tmuxセッションが既に存在する場合は終了を待つか強制終了
if tmux has-session -t "$SESSION" 2>/dev/null; then
  log "WARN: tmux session '$SESSION' already exists. Killing it."
  tmux kill-session -t "$SESSION" 2>/dev/null || true
  sleep 1
fi

# プロンプトをファイルに書き出し（エスケープ問題回避）
PROMPT_FILE="$LOG_DIR/${SCHED_NAME}-prompt-$$.txt"
echo "$PROMPT" > "$PROMPT_FILE"

# tmuxセッション作成 + Claude CLIスクリプトモード実行
log "Creating tmux session and running Claude CLI script mode..."
tmux new-session -d -s "$SESSION" -c "$WORKDIR" \
  "source ~/.zshrc 2>/dev/null; $CLAUDE_CMD -p \"\$(cat '$PROMPT_FILE')\" 2>&1 | tee -a '$LOG_FILE'; echo '[SCRIPT_DONE]' >> '$LOG_FILE'; rm -f '$PROMPT_FILE'"

# 実行完了を待つ（最大30分）
MAX_WAIT=1800
WAITED=0
RATE_LIMIT_LINE=""
log "Waiting for script completion (max ${MAX_WAIT}s)..."

while [ "$WAITED" -lt "$MAX_WAIT" ]; do
  sleep 10
  WAITED=$((WAITED + 10))

  # tmuxセッションが終了したか確認
  if ! tmux has-session -t "$SESSION" 2>/dev/null; then
    log "tmux session ended. (${WAITED}s)"
    break
  fi

  # ログにSCRIPT_DONEが出たか確認
  if grep -q '\[SCRIPT_DONE\]' "$LOG_FILE" 2>/dev/null; then
    log "Script completed. (${WAITED}s)"
    tmux kill-session -t "$SESSION" 2>/dev/null || true
    break
  fi

  if [ -z "$RATE_LIMIT_LINE" ] && grep -q "You've hit your limit" "$LOG_FILE" 2>/dev/null; then
    RATE_LIMIT_LINE=$(grep "You've hit your limit" "$LOG_FILE" | tail -n 1)
  fi

  # 5分ごとに進捗ログ
  if [ $((WAITED % 300)) -eq 0 ]; then
    log "  Still running... (${WAITED}s / ${MAX_WAIT}s)"
  fi
done

if [ "$WAITED" -ge "$MAX_WAIT" ]; then
  log "ERROR: Script timed out after ${MAX_WAIT}s. Killing session."
  tmux kill-session -t "$SESSION" 2>/dev/null || true
fi

if [ -z "$RATE_LIMIT_LINE" ] && grep -q "You've hit your limit" "$LOG_FILE" 2>/dev/null; then
  RATE_LIMIT_LINE=$(grep "You've hit your limit" "$LOG_FILE" | tail -n 1)
fi

[ -n "$RATE_LIMIT_LINE" ] && write_rate_limit_cooldown "$RATE_LIMIT_LINE"

# クリーンアップ
rm -f "$PROMPT_FILE"
log "=== Script Schedule Complete: $SCHED_NAME ==="
