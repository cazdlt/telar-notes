# Telar Notes

A local-first web editor for Markdown vaults, built with a Python backend and a Svelte 5 + TypeScript frontend.

> **Local and private self-hosted use only:** Telar Notes is designed for single-user use, either locally on `127.0.0.1` or self-hosted behind a private VPN/reverse proxy (e.g. Tailscale + Caddy, ideally inside Docker with `TELAR_ALLOWED_HOSTS`). It has no built-in authentication or multi-user isolation and reads/writes directly to the filesystem. **Do not** expose it to the public internet.

## Features

- Markdown editing with CodeMirror 6 and Live Preview
- Debounced autosave (500 ms) with optimistic concurrency
- Wikilinks, backlinks, tags, frontmatter, and local graph view
- Title, content, link, and tag search
- File/folder creation, rename, move, and recoverable deletion (`.trash/`)
- Pasted images and local embeds
- Markdown tasks and task queries
- Mermaid diagrams and `.excalidraw` / `.excalidraw.md` editing
- Themes, font-size controls, reading mode, and multi-vault switching
- macOS Finder reveal for files and folders

## Requirements

- Python 3.13+ and [`uv`](https://docs.astral.sh/uv/)
- Node.js and npm (for building the frontend and running JS tests)
- A modern browser

### External network requests (Google Fonts)

The frontend loads interface fonts at runtime from Google Fonts (`fonts.googleapis.com` and `fonts.gstatic.com`). Everything else is bundled locally. If you run offline or block external font requests, the browser will fall back to local system fonts.

## Running locally

Start the development server against a vault:

```bash
scripts/dev.sh /path/to/your-vault
```

Then open <http://127.0.0.1:7731>.

You can pass a custom port as the second argument or use environment variables:

```bash
TELAR_VAULT=/path/to/your-vault TELAR_PORT=8000 scripts/dev.sh
```

To run the production build directly:

```bash
npm install
npm run build
uv run python server.py --vault /path/to/your-vault --port 7731
```

### Docker

Run locally with Docker Compose (bound to `127.0.0.1` only):

```bash
VAULT_PATH=/path/to/your-vault TELAR_UID=$(id -u) TELAR_GID=$(id -g) docker compose up --build
```

Then open <http://127.0.0.1:7731>.

Environment variables:

- `VAULT_PATH`: Vault directory mounted at `/vault` (defaults to `./help`).
- `TELAR_CONFIG_PATH`: Host directory mounted at `/config` (`XDG_CONFIG_HOME`) for app config and link indexes (defaults to `./.telar-config`).
- `TELAR_UID` / `TELAR_GID`: Host user and group IDs the container runs as (defaults to `1000:1000`). Match your host or Syncthing user so atomic writes (`0600`) remain owned by the right user.
- `TELAR_ALLOWED_HOSTS`: Optional comma-separated hostnames allowed in `Host` / `Origin` headers (empty by default). Set this only when fronting Telar with a private reverse proxy/VPN (such as Tailscale + Caddy), as Telar has no built-in authentication and must never be exposed to the public internet.

For repeatable server deployments, copy `.env.example` to `.env`, set `VAULT_PATH` (and any other variables), then run:

```bash
./scripts/deploy.sh   # initial start / rebuild using .env
./scripts/upgrade.sh  # git pull --ff-only + deploy.sh
```

## Configuration

Configuration is stored at `~/.config/telar/config.json` (or `$XDG_CONFIG_HOME/telar/config.json` if `XDG_CONFIG_HOME` is set), and per-vault link indexes are stored under `$XDG_CONFIG_HOME/telar/indexes/` (not inside the vault). To configure multiple vaults:

```json
{
  "vaults": [
    {
      "name": "notes",
      "path": "/absolute/path/to/notes",
      "icon": "home"
    }
  ],
  "default_vault": "notes",
  "lang": "en",
  "theme_override": null,
  "font_size": 14
}
```

The `--vault` argument acts as a fallback when no vault is configured.

## Project structure

- `telar/`: FastAPI application package (vault logic, indexers, search, routes)
- `server.py`: Python CLI runner and backward-compatible entrypoint
- `src/`: Svelte 5 + TypeScript frontend
- `excalidraw-editor.html`, `src/excalidraw/`: isolated Excalidraw iframe
- `scripts/dev.sh`: development server launcher
- `scripts/deploy.sh`, `scripts/upgrade.sh`: Docker deployment and upgrade helpers
- `tests/python/`: HTTP API and backend tests (frontend tests live beside source as `src/**/*.test.ts`)
- `docs/`: HTTP API contract and task reference documentation

## Quality checks

```bash
uv run ruff format --check telar server.py tests/python
uv run ruff check telar server.py tests/python
uv run ty check telar server.py tests/python
uv run pytest
npm install
npm run check
npm run test
```

## License

[MIT](./LICENSE)
