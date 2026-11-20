# Current HTTP contract

This is the minimum contract that must survive frontend migration. It does not freeze internal details or prevent later API versioning.

## Common rules

- The server listens only on loopback and accepts `Host` and `Origin` values for `localhost` or `127.0.0.1`.
- File paths are relative to the active vault and cannot escape it.
- An optional `X-Vault: <name>` header scopes that request to a registered vault without changing the session vault. The client sends it from windows opened with `?vault=<name>`; unknown names fall back to the session vault.
- API responses are JSON except `/api/raw` and static assets.
- Errors use `{ "error": "message" }` with an appropriate HTTP status.
- Request bodies larger than 50 MiB return `413`.

## Read operations

| Method and path | Input | Successful response |
|---|---|---|
| `GET /api/files` | None | `{ "tree": FileNode[] }` |
| `GET /api/files/recent?sort=...&limit=...` | `sort`: `modified` (default) or `created`; `limit`: integer, default 50, clamped to 1-500 | `{ "files": RecentFile[] }`, newest first |
| `GET /api/note?path=...` | Text file | `{ "path": string, "content": string }` |
| `GET /api/raw?path=...` | File | Bytes with detected `Content-Type` |
| `GET /api/links?vault=...` | Optional vault; `__all__` merges all | Map from path to `links_to` and `linked_from` |
| `GET /api/config` | None | Effective configuration |
| `GET /api/vaults` | None | `VaultsInfo`: `{ "vaults": Vault[], "active": string | null, "default": string }` |
| `GET /api/search?q=...&mode=...` | `all`, `title`, `content`, `tags`, or `links` | `{ "results": SearchResult[] }` |
| `GET /api/tasks/block?path=...&id=...` | Note path and block ID | `{ "task": TaskRecord }` for the task line ending in `^id`; `404` when absent |

A task's Obsidian block ID (` ^id`, last on the line as Tasks requires) is exposed as `TaskRecord.block_id` and kept last when `POST /api/tasks/update` adds dates or priority. The editor renders `![[Note#^id]]` as the referenced task.

`FileNode` uses `{ "path", "type": "file", "name" }` for files and `{ "path", "type": "dir", "children" }` for directories.

`RecentFile` is `{ "path", "name", "modified", "created" }` with timestamps in epoch milliseconds. It lists only files the app renders (`.md`, `.markdown`, `.excalidraw`, and `.png`/`.jpg`/`.jpeg`/`.gif`/`.webp`/`.svg` images) and skips what the explorer hides (dotfiles, `.trash`, `links-index.json`). The UI requests the active vault's Recent Files plugin `limit` (`vault_settings.plugins.recent-files`: `enabled`, default `true`; `limit`, default 20, range 1-200; imported from Obsidian's `recent-files-obsidian` `maxLength`). `created` is the filesystem birth time where one exists; on Linux, which does not expose one, it equals `modified`. Atomic saves replace the file, so the server carries the original birth time over on macOS; on Windows a save resets it. An unknown `sort` or a non-integer `limit` returns `400`.

## Write operations

| Method and path | JSON body | Effect and successful response |
|---|---|---|
| `POST /api/note` | `{ "path", "content", "base_revision"?, "force"? }` | Create or replace a note; `{ "ok": true, "revision" }`. `base_revision: null` (or omitted) means create-only: `409` if the file exists. A string `base_revision` must match the current revision, otherwise `409` `{ "error", "revision", "content" }` with the on-disk state; a missing file with a string `base_revision` returns `409` `{ "error": "note was removed" }`. `force: true` skips the revision check |
| `POST /api/tasks/block-id` | `{ "location": TaskLocation }` | Append a readable, file-unique `^id` to the task line if it has none; `{ "ok": true, "id", "revision" }`. A stale `location` returns `409` |
| `POST /api/links/rebuild` | None | Rebuild `links-index.json` from disk for the active vault; same body as `GET /api/links` |
| `POST /api/session/vault` | `{ "vault" }` | Switch the session vault; `{ "ok": true, "active_vault" }` |
| `POST /api/vaults/pick` | `{}` | Open the native macOS folder dialog; `{ "path" }` or `{ "cancelled": true }` |
| `POST /api/vaults/add` | `{ "path", "name"? }` | Register an existing absolute folder; `VaultsInfo` |
| `POST /api/vaults/help` | None | Register the bundled `help/` folder as a vault if absent; `VaultsInfo` plus `help`, the vault's name |
| `POST /api/vaults/remove` | `{ "vault" }` | Unregister a vault without touching its files; `VaultsInfo` |
| `POST /api/vaults/default` | `{ "vault" }` | Set the startup vault; `VaultsInfo` |
| `POST /api/attach` | `{ "note" or "dir", "filename", "data_b64" }` | Store an attachment in the vault's `files.attachment_folder` setting (Obsidian `attachmentFolderPath` semantics; default `/`, imported from `.obsidian/app.json`); `{ "ok": true, "embed", "path" }` |
| `POST /api/mkdir` | `{ "path" }` | Create a directory; `{ "ok": true }` |
| `POST /api/rename` | `{ "from", "to" }` | Move or rename without overwrite; `{ "ok": true }` |
| `POST /api/delete` | `{ "path" }` | Move to `.trash`; `{ "ok": true, "trashed" }` |
| `POST /api/reveal` | `{ "path" }` | Reveal in macOS Finder; `{ "ok": true }` |

## Plugin settings

`GET/POST /api/settings` carry `vault_settings.plugins`. Besides `tasks`, `periodic-notes`, `recent-files` and `excalidraw`, `folder-notes` is `{ "enabled": boolean }` (default `false`). When enabled, the client treats `Folder/Folder.md` as the note of `Folder`: it hides that child in the explorer and opens it when the folder name is clicked. The server's `/api/files` is unchanged. `POST /api/settings/import-obsidian` enables it when `folder-notes` is listed in `.obsidian/community-plugins.json`.

## Required guarantees

- `POST /api/rename` returns `409` when the destination exists.
- Delete is recoverable and `.trash` stays hidden from the explorer.
- `/api/note` rejects binary files with `415`; `/api/raw` preserves bytes.
- Switching vaults changes the context for subsequent relative paths; unknown vault names return `404`.
- With no configured vaults, the launch vault is listed alone; the first registry change persists it as the default.
- Adding a vault rejects relative paths and the filesystem root (`400`), missing folders (`404`), and duplicate paths or names (`409`). Without `name`, the folder name is used with a numeric suffix if taken.
- Removing the active or the last vault returns `409`.
- `POST /api/vaults/pick` returns `501` when `osascript` is unavailable; the browser never lists the filesystem.
- Saving a note updates its links and backlinks before responding.
- Autosave failures remain visible instead of reporting a false success.
- Static files are served only from the frontend build: `/`, `/excalidraw-editor.html`, and `/assets/*` with allowed extensions.
- `POST /api/reveal` remains a macOS-specific integration with vault path validation.

## Contracts allowed to evolve

- Tag search is not committed for Milestone 1.
- The tree payload may become an incremental update stream.
- The API must be versioned before plugins consume it.
