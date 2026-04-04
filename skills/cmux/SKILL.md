---
name: cmux
description: |
  cmux CLIを介してワークスペース管理、セッション間連携、ブラウザ自動化、
  サイドバーメタデータ管理、通知を行うスキル。
  「ワークスペース作って」「ブラウザで開いて」「ステータス表示して」「通知して」で起動。
---

# cmux スキル

cmux CLIを操作してターミナルマルチプレクサの全機能を活用する。

## 前提条件

- cmuxアプリが起動中であること（`cmux ping` → PONG）
- macOS 14+専用

## コマンドリファレンス

### ワークスペース管理

```bash
# 一覧
cmux list-workspaces

# 新規作成（ディレクトリ指定 or コマンド実行）
cmux new-workspace --cwd /path/to/project
cmux new-workspace --command "claude"

# 選択・切替
cmux select-workspace --workspace workspace:1

# 現在のワークスペース
cmux current-workspace

# リネーム
cmux rename-workspace "new-name"

# 閉じる
cmux close-workspace --workspace workspace:1

# ツリー表示（全階層）
cmux tree --all
```

### ペイン・サーフェス管理

```bash
# 分割（方向: left/right/up/down）
cmux new-split right
cmux new-split down

# 新ペイン（ターミナル or ブラウザ）
cmux new-pane --type terminal --direction right
cmux new-pane --type browser --direction down --url "https://example.com"

# サーフェス一覧
cmux list-pane-surfaces

# フォーカス
cmux focus-pane --pane pane:1

# 閉じる
cmux close-surface --surface surface:1
```

### 入出力（セッション間連携の核心）

```bash
# テキスト送信（Enterは自動付与されない。\nを含めるか send-key enterを続ける）
cmux send --surface surface:3 "ls -la"
cmux send-key --surface surface:3 enter

# 画面読み取り（プレーンテキスト）
cmux read-screen --surface surface:3 --lines 50

# スクロールバック含む
cmux read-screen --surface surface:3 --scrollback --lines 200
```

**パラレルエージェント連携パターン**:
```bash
# 分割ペイン作成
cmux new-split right  # → surface:N が返る

# エージェント起動
cmux send --surface surface:N "claude\n"

# タスク割り当て
cmux send --surface surface:N "このプロジェクトを分析して\n"

# 結果読取
cmux read-screen --surface surface:N --lines 100

# クリーンアップ
cmux close-surface --surface surface:N
```

### ブラウザ自動化

```bash
# ブラウザを開く（新サーフェスが作られる）
cmux browser open "https://example.com"  # → surface:M

# ナビゲーション
cmux browser surface:M navigate "https://example.com/page"
cmux browser surface:M back
cmux browser surface:M reload

# ページ情報取得
cmux browser surface:M url
cmux browser surface:M get title
cmux browser surface:M get text "body"           # セレクタ指定でテキスト取得
cmux browser surface:M get text "h1"
cmux browser surface:M get html ".content"
cmux browser surface:M get attr "a" "href"
cmux browser surface:M get count "li"

# スナップショット（トークン効率最高: 200-400トークン）
cmux browser surface:M snapshot --compact         # 簡潔版
cmux browser surface:M snapshot --interactive      # 操作用ref付き

# DOM操作（snapshotのref番号を使用）
cmux browser surface:M click "ref=e2"
cmux browser surface:M fill "ref=e5" "search text"
cmux browser surface:M type "ref=e5" "additional text"
cmux browser surface:M press Enter
cmux browser surface:M select "ref=e10" "option-value"

# 待機
cmux browser surface:M wait --text "検索結果"
cmux browser surface:M wait --selector ".results"
cmux browser surface:M wait --load-state complete

# スクリーンショット
cmux browser surface:M screenshot --out /path/to/image.png

# JavaScript実行
cmux browser surface:M eval "document.title"

# 閉じる
cmux close-surface --surface surface:M
```

**SPA/JSレンダリングページ取得パターン**:
```bash
cmux browser open "https://example.com/spa-page"  # → surface:M
sleep 5  # JSレンダリング待ち
cmux browser surface:M get text "body"             # 全文取得
cmux close-surface --surface surface:M
```

### サイドバーメタデータ

```bash
# ステータスピル（SF Symbolsアイコン対応）
cmux set-status build "compiling" --icon hammer --color "#ff9500"
cmux set-status deploy "v1.2.3" --icon checkmark.circle --color "#34c759"
cmux clear-status build

# プログレスバー
cmux set-progress 0.5 --label "Building..."
cmux set-progress 1.0 --label "Done"
cmux clear-progress

# ログ（レベル色分け）
cmux log --level info --source "test" -- "テスト開始"
cmux log --level success --source "test" -- "42件全パス"
cmux log --level warning --source "build" -- "非推奨API使用"
cmux log --level error --source "deploy" -- "デプロイ失敗"
cmux list-log --limit 10
cmux clear-log

# 全メタデータ確認
cmux sidebar-state
```

### 通知

```bash
# デスクトップ通知
cmux notify --title "タスク完了" --body "処理が完了しました"
cmux notify --title "エラー" --subtitle "build" --body "テストに失敗"

# 通知管理
cmux list-notifications
cmux clear-notifications
```

### ウィンドウ管理

```bash
cmux list-windows
cmux new-window
cmux focus-window --window window:1
cmux close-window --window window:1
cmux move-workspace-to-window --workspace workspace:3 --window window:2
```

### ユーティリティ

```bash
cmux ping                    # 疎通確認
cmux capabilities            # 利用可能コマンド一覧
cmux identify                # 現在のコンテキスト
cmux version                 # バージョン
cmux trigger-flash           # 青フラッシュでペイン注目喚起
cmux find-window "query"     # ワークスペース検索
```

## 活用パターン

### 長時間タスクの進捗表示

```bash
cmux set-progress 0.0 --label "Phase 1: 分析中..."
# ... 作業 ...
cmux set-progress 0.33 --label "Phase 2: 生成中..."
# ... 作業 ...
cmux set-progress 0.66 --label "Phase 3: レビュー中..."
# ... 作業 ...
cmux set-progress 1.0 --label "完了"
cmux notify --title "完了" --body "処理が完了しました"
cmux clear-progress
```

### Playwright MCPの代替としてのブラウザ自動化

cmux browserはWebKitベースで、多くのユースケースでPlaywright MCPの代替になる。

| 観点 | cmux browser | Playwright MCP |
|------|-------------|----------------|
| トークン効率 | 極めて高い（~93%削減） | 大量消費 |
| エンジン | WebKit | Chromium |
| ヘッドレス | 不可 | 対応 |
| 設定 | cmux内なら不要 | MCP設定必要 |

**使い分け**: cmux内で作業中→cmux browser、ヘッドレス/Chromium必須→Playwright MCP

## 注意事項

- cmuxはmacOS専用。Windows/Linuxでは使用不可
- `send`はEnterを自動付与しない。`\n`を含めるか`send-key enter`を続ける
- ブラウザsurface:Mは`browser open`の戻り値から取得。固定IDを仮定しない
- close-workspaceは保存されていない作業を失う可能性がある。確認してから実行
- cmuxアプリが起動していないとCLIは動作しない（`cmux ping`で確認）
