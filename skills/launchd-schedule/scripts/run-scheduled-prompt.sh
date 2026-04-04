#!/usr/bin/env bash
set -euo pipefail

# run-scheduled-prompt.sh — tmuxセッション作成→Claude起動→準備完了検出→プロンプト実行
#
# 引数:
#   $1 — tmuxセッション名
#   $2 — ワークディレクトリ
#   $3 — claudeコマンドライン
#   $4 — 実行するプロンプト

SESSION="${1:?セッション名が必要です}"
WORKDIR="${2:?ワークディレクトリが必要です}"
CLAUDE_CMD="${3:-claude --dangerously-skip-permissions}"
PROMPT="${4:?プロンプトが必要です}"

LOG_DIR="$HOME/.local/share/harness-schedule/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/${SESSION}-$(date +%Y%m%d-%H%M%S).log"

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG_FILE"; }

log "=== Schedule Start: $SESSION ==="
log "Workdir: $WORKDIR | Cmd: $CLAUDE_CMD"

# tmuxセッション存在チェック
SESSION_EXISTS=false
if tmux has-session -t "$SESSION" 2>/dev/null; then
  SESSION_EXISTS=true
  log "Session '$SESSION' already exists"
fi

# Claudeプロセスが生きているか確認
CLAUDE_ALIVE=false
if [ "$SESSION_EXISTS" = true ]; then
  PANE_PID=$(tmux list-panes -t "$SESSION" -F '#{pane_pid}' 2>/dev/null | head -1)
  if [ -n "$PANE_PID" ]; then
    # paneの子プロセスにclaudeがいるか
    if pgrep -P "$PANE_PID" -f "claude" >/dev/null 2>&1; then
      CLAUDE_ALIVE=true
      log "Claude is alive in session"
    fi
  fi
fi

if [ "$CLAUDE_ALIVE" = true ]; then
  # 既存セッションにClaudeが動いている → /clear してプロンプト送信
  log "Sending /clear to existing session..."
  tmux send-keys -t "$SESSION" "/clear" Enter
  sleep 3
  log "Sending prompt..."
  tmux send-keys -t "$SESSION" "$PROMPT" Enter
else
  # セッションがない or Claudeが死んでいる → 再作成
  if [ "$SESSION_EXISTS" = true ]; then
    log "Claude not running. Killing old session..."
    tmux kill-session -t "$SESSION" 2>/dev/null || true
  fi

  log "Creating new tmux session..."
  tmux new-session -d -s "$SESSION" -c "$WORKDIR"
  sleep 1

  log "Starting Claude CLI: $CLAUDE_CMD"
  tmux send-keys -t "$SESSION" "$CLAUDE_CMD" Enter

  # Claude起動待ち: pane出力を監視して準備完了を検出
  log "Waiting for Claude to be ready..."
  MAX_WAIT=60
  WAITED=0
  READY=false

  while [ "$WAITED" -lt "$MAX_WAIT" ]; do
    sleep 2
    WAITED=$((WAITED + 2))

    # tmux paneの出力をキャプチャ
    SCREEN=$(tmux capture-pane -t "$SESSION" -p 2>/dev/null || true)

    # Claude準備完了の判定:
    # - ">" プロンプトが表示されている
    # - "Claude" を含む出力がある
    # - trust確認が出ている場合はyを送る
    if echo "$SCREEN" | grep -q "Is this a project you trust"; then
      log "Trust prompt detected. Sending 'y'..."
      tmux send-keys -t "$SESSION" "y" Enter
      continue
    fi

    if echo "$SCREEN" | grep -q "^>" 2>/dev/null || echo "$SCREEN" | grep -qi "ready\|claude\|workspace\|tips:" 2>/dev/null; then
      READY=true
      log "Claude ready! (${WAITED}s)"
      break
    fi

    log "  Waiting... (${WAITED}s / ${MAX_WAIT}s)"
  done

  if [ "$READY" = false ]; then
    log "WARN: Claude readiness not confirmed after ${MAX_WAIT}s. Sending prompt anyway."
  fi

  sleep 2
  log "Sending prompt..."
  tmux send-keys -t "$SESSION" "$PROMPT" Enter
fi

log "=== Schedule Complete ==="
