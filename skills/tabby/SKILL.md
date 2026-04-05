---
name: tabby
description: |
  Tabbyターミナルの操作リファレンス。CLI・MCP API（34ツール）の完全ガイド。
  タブ管理、コマンド実行、バッファ読み取り、ペイン分割に対応。
  Windows環境向け。
---

# tabby — Tabby ターミナル操作リファレンス

Windows環境でのTabbyターミナル操作の完全リファレンス。
CLI・MCP APIをカバーする。

## アーキテクチャ

```
Tabby (表示層・タブ管理)
  ├── CLI: tabby run / profile / open / paste
  └── MCP API: http://localhost:3001 (Tabby-MCP plugin)
```

## Tabby CLI

実行パス: `%LOCALAPPDATA%\Programs\Tabby\Tabby.exe`

### コマンド一覧

| コマンド | 説明 |
|---------|------|
| `tabby open [directory]` | ディレクトリでシェルを開く |
| `tabby run [command...]` | コマンドを新規タブで実行 |
| `tabby profile [name]` | 名前付きプロファイルでタブを開く |
| `tabby paste [text]` | アクティブタブにテキスト貼り付け |
| `tabby recent [index]` | 最近のプロファイルでタブを開く |
| `tabby quickConnect <provider> <query>` | SSH等のクイック接続 |

### 重要な制約

- **シングルインスタンス**: 2回目以降の起動はCLI引数を既存インスタンスに転送
- **yargsフラグ消費**: `-e`, `-c`, `-t` 等のフラグがTabbyのパーサーに食われる → `.cmd`バッチファイル経由で回避
- **新ウィンドウ不可**: CLIに新ウィンドウ作成コマンドなし。`Ctrl+Shift+N`（手動のみ）
- **タブ指定不可**: `paste`はアクティブタブのみ対象

## Tabby MCP API (Tabby-MCP plugin)

プラグイン: `tabby-mcp-server`
エンドポイント: `http://localhost:3001`

### セットアップ

1. Tabby Settings → Plugins → "tabby-mcp-server" をインストール
2. Tabby再起動
3. Settings → MCP → Start Server

### 通信方式

| 方式 | エンドポイント | 用途 |
|------|-------------|------|
| Direct HTTP | `POST /api/tool/{tool_name}` | スクリプトから直接呼び出し |
| Streamable HTTP | `POST /mcp` | Claude Code MCP連携 |
| SSE (Legacy) | `GET /sse` | レガシークライアント |
| Health | `GET /health` | ヘルスチェック |

### ターミナル操作ツール (7)

| ツール | パラメータ | 説明 |
|-------|-----------|------|
| `get_session_list` | — | 全セッション一覧（UUID・分割ペイン情報含む） |
| `exec_command` | `command`, `sessionId?`, `tabIndex?`, `title?`, `timeout?` | コマンド実行。出力待機可 |
| `send_input` | `input`, `sessionId?` | 生入力送信。`\x03`=Ctrl+C, `\r`=Enter |
| `get_terminal_buffer` | `sessionId?`, `lastNLines?` | ターミナルバッファ読み取り |
| `abort_command` | `sessionId?` | Ctrl+C送信 |
| `get_command_status` | — | 実行中コマンドの状態 |
| `focus_pane` | `sessionId` | 分割ペインにフォーカス |

### タブ管理ツール (11)

| ツール | パラメータ | 説明 |
|-------|-----------|------|
| `list_tabs` | — | 全タブ一覧（tabId・タイトル・状態） |
| `select_tab` | `tabId?`, `tabIndex?`, `title?` | タブ選択 |
| `close_tab` | `tabId?`, `tabIndex?`, `title?`, `force?` | タブを閉じる |
| `close_all_tabs` | — | 全タブを閉じる |
| `duplicate_tab` | `tabIndex?` | タブ複製 |
| `next_tab` / `previous_tab` | — | タブ移動 |
| `move_tab_left` / `move_tab_right` | — | タブ順序変更 |
| `reopen_last_tab` | — | 最後に閉じたタブを復元 |
| `split_tab` | `direction` (r/l/t/b) | ペイン分割 |

### プロファイル管理ツール (4)

| ツール | パラメータ | 説明 |
|-------|-----------|------|
| `list_profiles` | — | 全プロファイル一覧（profileId取得） |
| `open_profile` | `profileId?`, `profileName?`, `waitForReady?` | プロファイルで新規タブ作成。sessionId返却 |
| `show_profile_selector` | — | プロファイル選択ダイアログ表示 |
| `quick_connect` | `query` ("user@host:port") | SSH クイック接続 |

### セッション識別方式

| 識別子 | 安定性 | 用途 |
|--------|-------|------|
| `sessionId` (UUID) | **安定**（タブ並べ替えでも不変） | ターミナル操作の推奨ターゲット |
| `tabId` (hex) | **安定** | タブ管理の推奨ターゲット |
| `tabIndex` (数値) | 不安定（並べ替えで変わる） | レガシー互換のみ |
| `title` (文字列) | 部分一致 | 簡易指定 |

### 使用例（curl）

```bash
# タブ一覧
curl -s -X POST http://localhost:3001/api/tool/list_tabs \
  -H "Content-Type: application/json" -d '{}'

# プロファイルでタブ作成
curl -s -X POST http://localhost:3001/api/tool/open_profile \
  -H "Content-Type: application/json" \
  -d '{"profileId":"local:wsl"}'

# タブを閉じる（タイトル部分一致）
curl -s -X POST http://localhost:3001/api/tool/close_tab \
  -H "Content-Type: application/json" \
  -d '{"title":"my-tab"}'

# コマンド実行
curl -s -X POST http://localhost:3001/api/tool/exec_command \
  -H "Content-Type: application/json" \
  -d '{"command":"ls -la","sessionId":"xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"}'
```

### Python からの呼び出し

```python
import json, urllib.request

def mcp_call(tool, params=None):
    url = f"http://localhost:3001/api/tool/{tool}"
    data = json.dumps(params or {}).encode("utf-8")
    req = urllib.request.Request(url, data=data,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = json.loads(resp.read())
        return json.loads(body["content"][0]["text"])
```

## Tabby設定ファイル

パス: `%APPDATA%\tabby\config.yaml`

### プロファイル定義例

```yaml
profiles:
  - type: local
    name: 'my-profile'
    options:
      command: 'C:\path\to\command.cmd'
      args: ['arg1']
      env: {}
      cwd: null
      pauseAfterExit: false
    behaviorOnSessionEnd: close
    id: 'local:custom:my-profile-id'
    disableDynamicTitle: true
```

### 主要設定項目

| 項目 | 説明 |
|------|------|
| `behaviorOnSessionEnd` | `auto`/`close`/`keep`/`reconnect` |
| `disableDynamicTitle` | タイトル自動更新を無効化 |
| `recoverTabs` | Tabby再起動時にタブを復元 |
| `hotkeys.new-window` | `Ctrl-Shift-N`（デフォルト） |
