---
name: wsl-tmux
description: |
  WSL上のtmuxをWindows環境から操作するためのリファレンス。
  セッション管理、コマンド送信、画面読み取り、Windowsプロセス起動パターン。
---

# wsl-tmux — WSL tmux 操作リファレンス

Windows環境からWSL上のtmuxを操作するためのリファレンス。
セッション永続化により、ターミナルを閉じてもプロセスが維持される。

## 基本

Windows (Git Bash) から全て `wsl.exe -e tmux ...` で操作する。

## セッション管理

```bash
# 一覧
wsl.exe -e tmux ls

# 新規作成（デタッチ状態）
wsl.exe -e tmux new-session -d -s <name>

# アタッチ
wsl.exe -e tmux attach -t <name>

# 存在確認
wsl.exe -e tmux has-session -t <name>

# セッション終了
wsl.exe -e tmux kill-session -t <name>

# 全セッション終了
wsl.exe -e tmux kill-server

# アタッチ中のクライアント一覧
wsl.exe -e tmux list-clients
wsl.exe -e tmux list-clients -F "#{client_tty}: #{session_name}"

# クライアントをデタッチ（セッションは維持）
wsl.exe -e tmux detach-client -s <name>
```

## コマンド送信（Cross-session I/O）

```bash
# コマンド送信（C-m = Enter）
wsl.exe -e tmux send-keys -t <name> '<command>' C-m

# テキストだけ送信（Enterなし）
wsl.exe -e tmux send-keys -t <name> '<text>'

# 特殊キー
wsl.exe -e tmux send-keys -t <name> C-c        # Ctrl+C
wsl.exe -e tmux send-keys -t <name> Enter       # Enter
wsl.exe -e tmux send-keys -t <name> Escape      # Escape
wsl.exe -e tmux send-keys -t <name> C-d         # Ctrl+D (EOF)
```

## 画面読み取り

```bash
# 現在の画面
wsl.exe -e tmux capture-pane -t <name> -p

# スクロールバック含む（最大1000行）
wsl.exe -e tmux capture-pane -t <name> -p -S -1000
```

## ウィンドウ・ペイン操作

```bash
# ウィンドウ一覧
wsl.exe -e tmux list-windows -t <name>

# ペイン一覧
wsl.exe -e tmux list-panes -t <name>

# 水平分割
wsl.exe -e tmux split-window -h -t <name>

# 垂直分割
wsl.exe -e tmux split-window -v -t <name>

# ウィンドウタイトル設定
wsl.exe -e tmux rename-window -t <name> "new_title"
```

## Windowsプロセスの起動パターン

tmuxセッション内からPowerShell経由でWindowsコマンドを実行する。

```bash
# Claude Code起動
wsl.exe -e tmux send-keys -t <session> \
  "powershell.exe -NoProfile -Command \"Set-Location '<workdir>'; claude --dangerously-skip-permissions\"" C-m

# 任意のWindowsコマンド
wsl.exe -e tmux send-keys -t <session> \
  "powershell.exe -NoProfile -Command \"<command>\"" C-m
```

## Windows固有の注意事項

- **パス**: WSL内では `/mnt/c/Users/...` 形式。PowerShellに渡すときは `C:\Users\...` 形式
- **Git Bash MSYS2パス変換**: Git Bashは `/mnt/...` を `C:/Program Files/Git/mnt/...` に変換してしまう → `wsl.exe -e` 経由で回避
- **Tabby ConPTY**: `wsl -e tmux attach` がTabby内で失敗する場合は `wsl -- bash -c "tmux attach -t <name>"` を使う
- **セッション永続化**: WSLが起動している限りtmuxセッションは維持される。PCスリープ/再起動でWSLが止まるとセッションも消失
