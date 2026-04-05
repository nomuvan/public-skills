---
name: tabby-workspace
description: |
  Tabby + WSL tmux でマルチペイン作業環境の起動・停止を自動化するスキル。
  TOML定義ファイルから複数のClaude/Codexセッションを一括起動。
  マシン名の概念でremote-controlプレフィックスを管理。
---

# tabby-workspace — ワークスペース管理スキル

WSL tmux + Tabby (MCP/CLI) を使ったマルチペイン作業環境の起動・停止を自動化する。
Tabbyの詳細な操作リファレンスは `/tabby` スキル、tmux操作は `/wsl-tmux` スキルを参照。

## 使い方

```bash
# デフォルトワークスペースを起動
python3 .claude/skills/tabby-workspace/scripts/launch-workspace.py

# 名前指定で起動
python3 .claude/skills/tabby-workspace/scripts/launch-workspace.py --workspace デフォルト

# ワークスペース停止（タブ閉じ、tmux+Claude維持）
python3 .claude/skills/tabby-workspace/scripts/launch-workspace.py --stop

# 完全停止（タブ閉じ + Claude終了 + tmux kill）
python3 .claude/skills/tabby-workspace/scripts/launch-workspace.py --stop --kill

# ワークスペース一覧
python3 .claude/skills/tabby-workspace/scripts/launch-workspace.py --list
```

## 停止モードの違い

| モード | Tabbyタブ | Claude | tmuxセッション |
|--------|----------|--------|--------------|
| `--stop` | 閉じる | **維持** | **維持** |
| `--stop --kill` | 閉じる | 終了 | kill |

`--stop` が日常の停止操作。翌日の再起動でClaude即復帰。

## ワークスペース設定ファイル（TOML）

`workspaces/*.toml` に配置。ファイル名にはマシン名を使用（例: `ai01.toml`）。

```toml
machine = "ai01"                # マシン名（login_cmdの{machine}に展開される）

[[window]]
name = "ワークスペース名"
default = true

  [[window.pane]]
  title = "表示名"
  workdir = "C:\\Users\\user\\project"
  tmux_session = "session_name"
  mode = "claude"
  login_cmd = "claude --dangerously-skip-permissions --name session_name --remote-control-session-name-prefix {machine}:session_name"
```

### フィールド

**トップレベル:**

| フィールド | 必須 | 説明 |
|-----------|------|------|
| `machine` | No | マシン名。login_cmdの `{machine}` に展開される |

**ペイン:**

| フィールド | 必須 | 説明 |
|-----------|------|------|
| `title` | Yes | ペインの識別名（Tabbyタブタイトルにも使用） |
| `workdir` | Yes | 作業ディレクトリ（Windowsパス、`\\`エスケープ） |
| `tmux_session` | No | tmuxセッション名。省略時はtmuxなし |
| `mode` | Yes | `claude` / `codex` / `plain` |
| `login_cmd` | No | claude/codex起動コマンド。`{machine}`プレースホルダ使用可 |

## 動作フロー

### 起動
1. TOML設定読み込み、`machine`名を取得
2. 各ペインについて:
   - tmuxセッションが既存 → Claude稼働チェック → 稼働中ならタブだけ開く（再アタッチ）
   - tmuxセッション新規作成 → PowerShell経由でworkdirへ移動 → login_cmd送信（`{machine}`展開）
   - プロンプト待機（最大60秒）
   - `--remote-control-session-name-prefix` 含む場合 → `/remote-control` 送信
3. Tabby-MCP `open_profile` でWSLタブ作成 → `send_input`でtmux attach

### 停止（--stop）
1. Tabby-MCP `close_tab` でタブを閉じる
2. tmuxセッション・Claudeはそのまま維持

### 完全停止（--stop --kill）
1. tmux経由で `/exit` を送信 → Claude終了待機
2. Tabby-MCP `close_tab` でタブを閉じる
3. tmuxセッションをkill

## 前提条件

- WSL tmux (`wsl.exe -e tmux` で動作確認)
- Tabby + tabby-mcp-server プラグイン（推奨、なくても動作可）
- Python 3.11+ (tomllib), pyyaml

## 技術的な注意

- Tabby CLIのyargsパーサーは `-e`, `-c`, `-t` を消費する → `.cmd`バッチファイルで回避
- MCP API経由のタブ操作は即座に反映される
- タブタイトルはprintf escape sequenceで設定（tmux set-titles off併用）
