# Skill Guidelines

## 1. Agent Skills 仕様（オープンスタンダード）

[Agent Skills](https://agentskills.io) 仕様で定義されているフィールド。

### 必須

```yaml
---
name: skill-name        # 小文字英数字とハイフンのみ
description: ...        # スキルの用途と使用タイミング
---
```

### 仕様上の Optional

```yaml
---
license: MIT
compatibility:
  - claude-code
  - codex-cli
metadata:
  author: ...
  version: "1.0.0"
allowed-tools: Read, Grep, Glob
---
```

## 2. プラットフォーム固有拡張（Claude Code / Codex CLI）

以下は Agent Skills 仕様ではなく各プラットフォームの拡張フィールド。

### Claude Code 固有

```yaml
---
context: fork                       # 隔離サブエージェントで実行
agent: Explore                      # context: fork 時のエージェントタイプ
disable-model-invocation: true      # Claude の自動呼び出しを禁止
user-invocable: false               # /メニューから非表示
model: sonnet                       # モデル指定
effort: high                        # エフォートレベル
paths: "src/**/*.ts"                # 自動適用のパススコープ
shell: bash                         # インラインコマンドのシェル
---
```

- `$ARGUMENTS` 変数展開: Claude Code 固有。Codex では動作しない
- 動的コンテキスト注入 (`` !`command` ``): Claude Code 固有

### Codex CLI 固有

- SKILL.md フォーマットは共通。配置パスが `.agents/skills/` になる
- 上記 Claude Code 固有フィールドは無視される（エラーにはならない）

## 3. このリポジトリの独自ルール

Agent Skills 仕様やプラットフォーム仕様ではなく、public-skills リポジトリの品質基準。

### 推奨

- description は **250文字以内**（Claude Code のコンテキストバジェット考慮）
- スキル本文は **500行以下**（超える場合は補助ファイルに分離）
- 副作用のあるスキルは `disable-model-invocation: true` を設定

### 設計チェックリスト

- [ ] name は用途を端的に表す命名か
- [ ] description は Claude/Codex が自動適用を判断できる具体性があるか
- [ ] 本文は500行以下か
- [ ] Mac/Windows両方で動作するか（シェルスクリプトを含む場合）
- [ ] セキュリティリスクのあるコマンドを含んでいないか
- [ ] 副作用のあるスキルに適切なガードがあるか

## クロスプラットフォーム配置パス

| プラットフォーム | プロジェクトスコープ | 個人スコープ |
|:--|:--|:--|
| Claude Code | `.claude/skills/<name>/SKILL.md` | `~/.claude/skills/<name>/SKILL.md` |
| Codex CLI | `.agents/skills/<name>/SKILL.md` | `~/.agents/skills/<name>/SKILL.md` |

### Windows での注意事項

- Claude Code の hooks は `shell: "powershell"` で PowerShell 対応可能
- Codex CLI の hooks は Windows で一部制限あり（公式ドキュメント参照）
- シェルスクリプトを含むスキルは POSIX 互換にするか、PowerShell 版も用意する
