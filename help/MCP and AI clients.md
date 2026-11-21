# MCP and AI clients

Telar Notes includes a built-in **Streamable HTTP MCP server** at `/mcp` on the same address and port as the editor. Any MCP-compatible client can connect directly without cloning the repo or installing a local runner.

```json
{
  "mcpServers": {
    "telar": {
      "url": "http://127.0.0.1:7731/mcp"
    }
  }
}
```

## Multi-vault

With a single vault, omit any headers and requests go straight to it. With multiple vaults, either pass a `vault` argument on a tool call, pin a vault in your client config with the `X-Vault` header, or call `list_vaults` to see available names.

## What clients can do

- **Discover**: list files, check recent files, search by title, content, tags, or links.
- **Read selectively**: inspect headings with `note_outline`, then read a specific section (`"Parent > Child"`) or line range with `read_note`.
- **Edit surgically**: create notes (`create_note`), apply atomic section/text patches with optional `dry_run` diffs and `base_revision` checks (`patch_note`), or open today's note (`open_daily_note`).
- **Manage tasks**: query, add, and update [[Tasks]] with `query_tasks`, `add_task`, and `update_task`.

If your vault root has a `CLAUDE.md` or `AGENTS.md` file, the server instructs clients to read it first and follow your vault's conventions.

## Security and CLI alternative

`/mcp` shares Telar's `Host` / `Origin` checks (`TELAR_ALLOWED_HOSTS`) and vault path containment. Keep it on localhost or behind a private VPN/reverse proxy (such as Tailscale + Caddy), never on the public internet.

For shell-driven agents without MCP support, the repository also bundles a zero-dependency CLI skill in `skills/telar-vault/`.
