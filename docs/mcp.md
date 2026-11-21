# MCP Server (`/mcp`)

Telar Notes exposes a built-in **Streamable HTTP MCP server** at `/mcp` on the same host and port as the web editor and HTTP API. Clients connect directly to a running Telar instance with no local installation or repository clone required.

- **Transport**: Streamable HTTP (`stateless_http=True`, `json_response=True`)
- **Endpoint**: `http://127.0.0.1:7731/mcp` (or `https://<your-host>/mcp` behind a private Tailscale/Caddy reverse proxy)
- **Stateless**: Server restarts and upgrades (`./scripts/upgrade.sh`) do not invalidate client connections.

## Client configuration

### Local Telar instance

Generic MCP JSON config (Antigravity, Cursor, Claude Code `.mcp.json`, etc.):

```json
{
  "mcpServers": {
    "telar": {
      "url": "http://127.0.0.1:7731/mcp"
    }
  }
}
```

Claude Code CLI:

```bash
claude mcp add --transport http telar http://127.0.0.1:7731/mcp
```

### Remote instance (Tailscale + Caddy) with pinned vault

Ensure your proxy hostname is listed in `TELAR_ALLOWED_HOSTS` on the Telar server (see [README.md](../README.md#docker)), then point your client at `/mcp` with an optional `X-Vault` header:

```json
{
  "mcpServers": {
    "telar": {
      "url": "https://telar.your-tailnet.ts.net/mcp",
      "headers": {
        "X-Vault": "personal"
      }
    }
  }
}
```

## Multi-vault resolution

Every vault-scoped tool resolves the target vault in this order:

1. Explicit `vault` tool argument (fails fast with an error if unknown).
2. `X-Vault` HTTP request header (matches HTTP API behavior).
3. Active session vault (or launch fallback vault).

Call `list_vaults` to discover configured vault names without exposing host filesystem paths.

## Server instructions & session bootstrap

On `initialize`, the server sends built-in `instructions` that guide clients to:

1. Check for vault-specific instructions (`CLAUDE.md` or `AGENTS.md`) at the vault root via `read_note` on first use.
2. Follow a narrow, context-preserving workflow: discover (`list_files`, `recent_files`, `search_notes`) -> inspect structure (`note_outline`) -> read selectively (`read_note` with `section` or `start_line`/`end_line`) -> edit surgically (`patch_note`, `add_task`, `update_task`).

## Tool reference

### Discovery & reading (read-only)

| Tool | Key parameters | Description |
|---|---|---|
| `list_vaults` | *(none)* | List configured vault names (`name`, optional `icon`), `active`, and `default`. Host filesystem paths are omitted. |
| `list_files` | `vault?` | Visible file and directory tree (skips dotfiles, `.trash/`, `links-index.json`). |
| `recent_files` | `sort?` (`modified` \| `created`), `limit?` (1–500, default 20), `vault?` | Recently modified or created notes and media files, newest first. |
| `search_notes` | `query`, `mode?` (`all` \| `title` \| `content` \| `tags` \| `links`), `vault?` | Search across the vault. |
| `note_outline` | `path`, `vault?` | Heading hierarchy with 1-based `line` / `end_line` ranges and current `revision`. |
| `read_note` | `path`, `section?`, `start_line?`, `end_line?`, `vault?` | Read a note in full, by heading path (`"Parent > Child"`, case/accent insensitive), or by 1-based inclusive line range. `section` and line ranges are mutually exclusive. |
| `query_tasks` | `query?`, `source?`, `vault?` | Execute an Obsidian Tasks query across the vault (e.g. `not done`). |

### Creating & surgical editing (write)

All write tools perform atomic writes, update the link index, and invalidate the task cache before returning.

| Tool | Key parameters | Description |
|---|---|---|
| `create_note` | `path`, `content?`, `vault?` | Create-only atomic write; fails if a file already exists at `path`. |
| `patch_note` | `path`, `op` (`insert` \| `replace_section` \| `replace_text`), `content?`, `anchor?`, `heading?`, `old?`, `new?`, `base_revision?`, `dry_run?`, `vault?` | Surgical edit with unified diff output. Supports `base_revision` optimistic locking and `dry_run=true` previews. |
| `open_daily_note` | `date?` (`YYYY-MM-DD`), `vault?` | Open or create a periodic daily note from the vault's Periodic Notes template. |
| `add_task` | `path`, `description`, `status?`, `priority?`, `dates?`, `tags?`, `block_id?`, `children?`, `anchor?`, `heading?`, `dry_run?`, `vault?` | Format and insert a canonical Obsidian Tasks line (with optional child lines and unique `^block_id`). |
| `update_task` | `path`, locator (`block_id` \| `match` \| `line` + optional `expected`), patch (`status`, `description`, `priority`, `dates`, `set_block_id`, `append_children`), `dry_run?`, `vault?` | Update an existing task line in place with optional `dry_run=true` diff preview. |

## Security boundary

`/mcp` shares Telar's HTTP security middleware (`boundary_and_limits` in `telar/app.py`):

- Requests with a `Host` or `Origin` outside `127.0.0.1`, `localhost`, and `TELAR_ALLOWED_HOSTS` are rejected with `403`.
- Every file path is validated against the active vault root; traversal outside the vault is rejected.
- `list_vaults` strips host filesystem paths from its response.
- Telar has no built-in authentication. Never expose `/mcp` to the public internet; keep it on loopback or behind a private VPN/reverse proxy.

## MCP vs. CLI skill (`skills/telar-vault`)

Telar also bundles a zero-dependency CLI skill in [`skills/telar-vault/`](../skills/telar-vault/SKILL.md):

- **Use `/mcp`** when your client supports Streamable HTTP MCP (zero client-side setup, works without a shell, automatic schema updates when Telar is upgraded).
- **Use `skills/telar-vault`** when working in a shell-driven agent without MCP support, or when you want to pipe/script vault operations from the terminal.
