# Telar Notes

A local-first web editor for Markdown vaults, built with a Python backend and a Svelte 5 + TypeScript frontend.

> **Local use only:** Telar Notes is designed strictly for single-user local use. The server binds to `127.0.0.1`, has no authentication or multi-user isolation, and reads/writes directly to your local filesystem. **Do not** expose it to the internet or deploy it as a public web service.

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
scripts/dev /path/to/your-vault
```

Then open <http://127.0.0.1:7731>.

You can pass a custom port as the second argument or use environment variables:

```bash
TELAR_VAULT=/path/to/your-vault TELAR_PORT=8000 scripts/dev
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
VAULT_PATH=/path/to/your-vault docker compose up --build
```

If `VAULT_PATH` is omitted, it mounts the bundled `./help` vault. Then open <http://127.0.0.1:7731>.

## Configuration

Configuration is stored at `~/.config/telar/config.json` (or `$XDG_CONFIG_HOME/telar/config.json` if `XDG_CONFIG_HOME` is set). To configure multiple vaults:

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
- `scripts/dev`: development server launcher
- `tests/python/`: HTTP API and backend tests (frontend tests live beside source as `src/**/*.test.ts`)
- `benchmarks/`: performance baseline scripts

## Quality checks

```bash
uv run ruff format --check telar server.py tests/python benchmarks/baseline.py
uv run ruff check telar server.py tests/python benchmarks/baseline.py
uv run ty check telar server.py tests/python benchmarks/baseline.py
uv run pytest
npm install
npm run check
npm run test
```

## License

[MIT](./LICENSE)
