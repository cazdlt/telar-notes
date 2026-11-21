---
name: telar-vault
description: Read, search, create, and surgically edit Markdown notes and Obsidian tasks in a remote or local Telar Notes vault via its HTTP API using the bundled zero-dependency Python CLI (`scripts/telar_cli.py`).
---

# Telar Vault

Interact with any Telar Notes vault over HTTP using `scripts/telar_cli.py` (Python 3 stdlib only; no external packages required).

> **Tip:** If your client supports Streamable HTTP MCP, Telar Notes also exposes a built-in MCP server at `/mcp` (zero client-side installation — see `docs/mcp.md`). Use this skill when working in shell-driven environments without MCP or when scripting from the terminal.

## Configuration

Set connection environment variables or pass global flags before the subcommand:

- `TELAR_URL` (or `--url URL`): Base URL of the Telar server. Defaults to `http://127.0.0.1:7731`.
- `TELAR_VAULT` (or `--vault NAME`): Optional vault name sent as `X-Vault` header.
- `--json`: Print raw JSON responses instead of formatted text.

## Session Bootstrap Rule

On first use against a vault in a session, check for vault-specific instructions at the vault root:

```bash
python3 scripts/telar_cli.py note read CLAUDE.md
python3 scripts/telar_cli.py note read AGENTS.md
```

If either file exists, follow its conventions (language, folder layout, task formatting, confirmation rules) for the rest of the session.

## Recommended Workflow

Prefer narrow, section-scoped reads and surgical edits to preserve context and avoid clobbering concurrent changes:

1. **Discover**: `files`, `files --recent`, or `search <query>` to locate target notes.
2. **Inspect structure**: `note outline <path>` to list headings with line ranges.
3. **Read selectively**: `note read <path> --section "<Heading>"` or `--lines START:END` (supports `"Parent > Child"` paths and accent/case-insensitive heading matching).
4. **Edit surgically**: `note patch`, `task add`, or `task update`. Pass `--dry-run` first to preview unified diffs when verifying non-trivial edits.

## Command Reference

### Files & Search

```bash
telar_cli.py files
telar_cli.py files --recent --sort modified --limit 20
telar_cli.py search "project roadmap" --mode content
```

`--mode` accepts `all`, `title`, `content`, `tags`, `links`.

### Notes

```bash
# Outline & read
telar_cli.py note outline "folder/note.md"
telar_cli.py note read "folder/note.md"
telar_cli.py note read "folder/note.md" --section "Parent > Child"
telar_cli.py note read "folder/note.md" --lines 10:40

# Create a new note (fails with 409 if it already exists)
telar_cli.py note create "folder/new.md" --content "# Title"
telar_cli.py note create "folder/new.md" --stdin <<'EOF'
# Title

Initial body.
EOF

# Patch an existing note (add --dry-run to preview, --base-revision REV for optimistic locking)
telar_cli.py note patch "folder/note.md" --append-section "Log" --stdin <<'EOF'
- Added entry
EOF

telar_cli.py note patch "folder/note.md" --insert-after "Summary" --content "Key point."
telar_cli.py note patch "folder/note.md" --insert-before "Archive" --content "## Next"
telar_cli.py note patch "folder/note.md" --append-file --content "Footer note"
telar_cli.py note patch "folder/note.md" --prepend-file --content "Top callout"
telar_cli.py note patch "folder/note.md" --replace-section "Status" --content "In progress"
telar_cli.py note patch "folder/note.md" --replace "old phrase" "new phrase"
```

### Tasks

```bash
# Query tasks
telar_cli.py task query
telar_cli.py task query "not done" --source "daily/2026-11-20.md"

# Add a task
telar_cli.py task add "daily/2026-11-20.md" \
  --text "Review API contract" \
  --priority high \
  --due 2026-11-25 \
  --tag work \
  --section "Tasks" \
  --anchor end_of_section \
  --child "Check edge cases" \
  --dry-run

# Update a task (locate by --id, --match, or --line)
telar_cli.py task update "daily/2026-11-20.md" --id abc123 --status x
telar_cli.py task update "daily/2026-11-20.md" --match "Review API" --priority medium --due 2026-11-26
telar_cli.py task update "daily/2026-11-20.md" --line 14 --set-id api-review --child "Follow up tomorrow"
```

Errors are printed to `stderr` as `{"error": "..."}` with a non-zero exit code.
