# public-skills

Publicly shareable skills for [Claude Code](https://code.claude.com/) and [Codex CLI](https://github.com/openai/codex).

## Usage

### Claude Code

Copy a skill directory into your project's `.claude/skills/`:

```bash
cp -r skills/<skill-name> /path/to/your-project/.claude/skills/
```

### Codex CLI

Copy a skill directory into your project's `.agents/skills/`:

```bash
cp -r skills/<skill-name> /path/to/your-project/.agents/skills/
```

### Personal (all projects)

```bash
# Claude Code
cp -r skills/<skill-name> ~/.claude/skills/

# Codex CLI
cp -r skills/<skill-name> ~/.agents/skills/
```

### Windows (PowerShell)

```powershell
# Claude Code
Copy-Item -Recurse skills/<skill-name> "$env:USERPROFILE\.claude\skills\"

# Codex CLI
Copy-Item -Recurse skills/<skill-name> "$env:USERPROFILE\.agents\skills\"
```

## Skills

| Skill | Description |
|-------|-------------|
| [cmux](skills/cmux/) | cmux CLIでワークスペース管理、セッション間連携、ブラウザ自動化、通知 |
| [cmux-workspace](skills/cmux-workspace/) | cmuxで作業用Windowを起動・停止。TOML定義、tmux/Claude/Codex自動ログイン対応 |
| [launchd-schedule](skills/launchd-schedule/) | macOS launchdで定期タスク実行。Claude対話/スクリプト/任意コマンドの3モード |

## Skill Format

Each skill follows the [Agent Skills](https://agentskills.io) open standard:

```
skills/<skill-name>/
├── SKILL.md           # Main skill definition (required)
├── templates/         # Templates (optional)
├── scripts/           # Helper scripts (optional)
└── examples/          # Usage examples (optional)
```

## Contributing

1. Create a feature branch
2. Add your skill under `skills/<skill-name>/`
3. Ensure `SKILL.md` has proper frontmatter (`name`, `description`)
4. Open a PR with a description of the skill's purpose and use cases

## License

MIT
