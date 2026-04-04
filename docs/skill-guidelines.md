# Skill Guidelines

## SKILL.md フロントマター

必須フィールド:

```yaml
---
name: skill-name        # 小文字英数字とハイフンのみ（最大64文字）
description: ...        # 250文字以内。用途と使用タイミングを具体的に
---
```

推奨フィールド:

```yaml
---
name: skill-name
description: ...
allowed-tools: Read, Grep, Glob    # 必要最小限のツール
context: fork                       # 隔離実行が必要な場合
disable-model-invocation: true      # 副作用がある場合
user-invocable: false               # バックグラウンド知識の場合
---
```

## 設計チェックリスト

- [ ] name は用途を端的に表す命名か
- [ ] description は Claude/Codex が自動適用を判断できる具体性があるか
- [ ] 本文は500行以下か（超える場合は補助ファイルに分離）
- [ ] Mac/Windows両方で動作するか（シェルスクリプトを含む場合）
- [ ] セキュリティリスクのあるコマンドを含んでいないか
- [ ] 副作用のあるスキルに適切なガードがあるか

## クロスプラットフォーム対応

- Claude Code: `.claude/skills/<name>/SKILL.md`
- Codex CLI: `.agents/skills/<name>/SKILL.md`
- SKILL.md のフォーマットは共通。配置パスのみ異なる
- `$ARGUMENTS` 変数展開は Claude Code 固有。Codex では動作しない点に注意
- 動的コンテキスト注入 (`` !`command` ``) も Claude Code 固有
