---
name: cmux-workspace
description: |
  cmuxで日々の作業用Windowを起動・停止するスキル。
  Window構成はTOMLファイルで複数定義可能。デフォルト指定あり。
  tmux連携、Claude/Codexセッション自動ログイン対応。
  「ワークスペース起動して」「作業環境を開いて」「Windowを開いて」で起動。
  「ワークスペース停止して」「作業環境を止めて」で停止。
---

# cmux-workspace スキル

cmuxで定義済みの作業用Windowを起動・停止する。

## 操作

### launch — Window起動

```bash
SKILL_DIR=.claude/skills/cmux-workspace

# デフォルトWindow起動
python3 "$SKILL_DIR/scripts/launch-workspace.py"

# 名前指定で起動
python3 "$SKILL_DIR/scripts/launch-workspace.py" --name "my-workspace"
```

### stop — Window停止

```bash
# cmux windowだけ閉じる（tmux/claudeは残る）
python3 "$SKILL_DIR/scripts/launch-workspace.py" --stop

# 完全停止（claude exit → tmux kill → cmux close）
python3 "$SKILL_DIR/scripts/launch-workspace.py" --stop --kill

# 名前指定で停止
python3 "$SKILL_DIR/scripts/launch-workspace.py" --stop --name "my-workspace"
```

### list — 定義済みWindow一覧

```bash
python3 "$SKILL_DIR/scripts/launch-workspace.py" --list
```

## Window構成の定義

`workspaces/` 配下のTOMLファイルで定義。複数ファイル対応。

```toml
[[window]]
name = "my-workspace"
default = true

  [[window.pane]]
  title = "project_01"
  workdir = "/path/to/project"
  tmux_session = "project_01"    # 省略時: tmux不使用
  mode = "claude"                # claude | codex | plain
  login_cmd = "claude --name project_01"  # mode=claude/codex時の起動コマンド
```

### 各フィールド

| フィールド | 必須 | 説明 |
|-----------|------|------|
| `title` | Yes | cmuxワークスペース名（左メニュー表示） |
| `workdir` | Yes | ワークディレクトリ |
| `tmux_session` | No | tmuxセッション名。省略でtmux不使用 |
| `mode` | No | `claude` / `codex` / `plain`（デフォルト: `plain`） |
| `login_cmd` | No | claude/codex起動コマンド |

### 動作仕様

- 同名ワークスペースを持つ既存Windowがあれば自動で閉じてから再作成
- tmuxセッション未作成 -> 新規作成してアタッチ
- tmuxセッション作成済み -> そのままアタッチ
- claude/codex動作中 -> login_cmd送信をスキップ

## セットアップ

1. このスキルディレクトリをプロジェクトの `.claude/skills/` にコピー
2. プロジェクトルートに `workspaces/` ディレクトリを作成
3. `workspaces/default.toml` に自分の作業環境を定義（`workspaces/example.toml` を参考に）

## 注意事項

- cmuxアプリが起動中であること（`cmux ping`で確認）
- macOS専用
- tmuxが必要な場合は `brew install tmux`
