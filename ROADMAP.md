# Development roadmap

This plan turns Telar Notes from a proof of concept into a local, extensible web editor. The goal is not to reproduce every Obsidian feature. The first objective is a fast and reliable daily workflow with portable Markdown files.

## Architecture decisions

### Frontend

- Svelte 5, TypeScript, and Vite.
- Keep CodeMirror 6 as the editor engine.
- Svelte owns the surrounding UI but not CodeMirror's internal document state.
- Split the application by domain: editor, explorer, vaults, links, search, commands, settings, and plugins.
- Keep the public plugin API independent from Svelte.
- Let Vite manage frontend dependencies. Bundling every remote asset for offline use is not a requirement.

### Backend

- Prefer the newest stable CPython release compatible with the selected libraries and let `uv` provision it. Python 3.14 is the current development preference, not a hard compatibility target.
- Keep Python while it meets measured performance targets.
- Do not rewrite preventively in Rust or Go.
- Replace full scans and unnecessary polling with file observation and incremental indexes.
- Do not use optional runtime dependencies such as `ripgrep`; every installation must behave consistently.
- Keep distribution open until the architecture stabilizes. `uvx` is an option, not a requirement.
- Remain a local web application. A native wrapper is not currently required.

### Plugins

- Author plugins in TypeScript and distribute bundled JavaScript.
- Provide a manifest, API version, activation lifecycle, commands, settings, events, and permissions.
- Initial capabilities cover vault access, workspace integration, commands, events, settings, and CodeMirror extensions.
- Run untrusted plugins in isolation behind a limited API.
- Tasks is the first official plugin and validates the contract before it expands.

### Dependency policy

- Prefer a focused, maintained library over implementing a standard parser, index, watcher, sanitizer, or UI behavior from scratch.
- Evaluate libraries by maintenance, license, bundle or runtime cost, browser and platform support, data fidelity, and escape hatches.
- Wrap important third-party libraries behind small application-owned interfaces so they can be replaced without leaking into every feature.
- Do not add a dependency for behavior already provided clearly by the browser, Python standard library, Svelte, or CodeMirror.
- Record a short decision and a representative compatibility test before adopting a library for a core file format.

## Principles

- Simple operation: avoid unnecessary infrastructure and optional system dependencies.
- Portable files: Markdown and interoperable formats remain the source of truth.
- Measured performance: optimizations and language changes respond to observed bottlenecks.
- Data safety: save, move, rename, delete, and synchronization operations never lose changes silently.
- Small core: functionality that can be a plugin stays outside the core unless there is a concrete reason.
- Incremental migration: preserve useful behavior while replacing the current implementation.

## Priority 0: simplify the PoC

**Status:** completed.

### Goal

Reduce the cost and risk of future changes.

### Completed work

- [x] Inventory current capabilities and decide what belongs in Milestone 1.
- [x] Identify and remove confirmed accidental, duplicate, or deferred code.
- [x] Remove the CSV/TSV table view, D3 graph, and Dataview-like query mode.
- [x] Keep Reveal in Finder as a macOS-specific convenience.
- [x] Remove the optional `ripgrep` execution path and ignore its legacy settings.
- [x] Migrate Python tests from `unittest` to `pytest`.
- [x] Reduce 54 Python tests taking 17.2 seconds to 15 critical tests taking about 0.6 seconds.
- [x] Reduce JavaScript tests from 23 cases to three Excalidraw format contracts.
- [x] Protect reading, writing, autosave persistence, vault path isolation, create/move/rename/trash operations, wikilinks, backlinks, vault switching, attachments, raw files, and origin checks.
- [x] Document the HTTP contracts that must survive frontend migration.
- [x] Add a `uv`-based development launcher under `scripts/dev.sh`.
- [x] Standardize user-facing UI text and repository documentation in English.
- [x] Remove the old welcome illustration and replace it with a minimal empty state.
- [x] Start the explorer collapsed and persist only explicitly expanded folders.
- [x] Autosave 500 ms after typing stops and expose save failures in the UI.
- [x] Add a left action sidebar with a button that opens or creates today's note at `diario/YYYY/MM/YYYY-MM-DD.md`.
- [x] Make the note path focus and reveal the current file in the explorer.

### Artifacts

- HTTP contract: [`docs/http-api.md`](docs/http-api.md)

### Exit criteria

- The critical suite completes in under a few seconds and protects data-risk operations.
- Every current feature has an explicit keep, defer, or remove decision.
- Performance measurements are reproducible.
- The PoC can migrate in parts without a full rewrite.

## Milestone 1.1: Svelte foundation and feature parity

**Status:** completed.

### Goal

Replace the monolithic frontend with a typed Svelte application without losing current behavior or changing the HTTP API.

### Delivered

- Svelte 5 + TypeScript + Vite frontend in `src/`, served from `web/dist/` by FastAPI in production and proxied via `scripts/dev.sh` in development.
- Typed API client (`src/lib/api.ts`), explicit application/vault/editor state, collapsed-by-default explorer, 500 ms autosave with optimistic concurrency, Live Preview CodeMirror 6 adapter, Mermaid renderer, and isolated Excalidraw bridge.
- Legacy frontend removed after cutover.

## Milestone 1.2: editor capabilities and scalable indexing

### Goal

Deliver the new editor capabilities needed for daily use on top of the migrated frontend.

### Library evaluation before implementation

- Evaluate `yaml` and its Document/CST APIs for loss-minimizing frontmatter parsing and edits.
- Evaluate the unified/remark ecosystem for Markdown parsing and transformation outside CodeMirror; use CodeMirror's Markdown syntax tree for editor decorations where appropriate.
- Evaluate a maintained HTML sanitizer before rendering generated or embedded HTML.
- Evaluate `watchfiles` and maintained alternatives for cross-platform filesystem observation instead of implementing OS watchers directly.
- Evaluate a maintained client or server search index before building a custom index. Choose its location using the 5,000-note benchmark, not preference.
- Evaluate accessible Svelte primitives or components for complex tree and menu behavior before implementing ARIA interactions manually.

### Live Preview and persistence

- Keep editing and rendering in one surface.
- Complete inline elements, blocks, tables, tasks, callouts, code, embeds, and frontmatter.
- Preserve cursor, selection, IME composition, and undo/redo behavior.
- Avoid rebuilding decorations outside the viewport when possible.
- Keep debounced autosave responsive and make failures recoverable.
- Add browser tests for editing and saving critical Markdown elements.

### YAML frontmatter

- Parse full YAML frontmatter instead of the current flat `key: value` subset.
- Support nested objects, arrays, multiline strings, dates, booleans, numbers, aliases, and tags.
- Preserve comments, field ordering, quoting, and unknown values during round-trip edits.
- Expose structured properties without rewriting frontmatter merely by opening a note.
- Recover from invalid YAML without hiding or overwriting the original source.
- Provide typed frontmatter access through the future plugin API.

### Explorer

- Create, move, rename, and send files and folders to recoverable trash.
- Start collapsed, preserve expansion state, and support complete keyboard navigation.
- Add filtering while preserving selection and scroll position.
- Virtualize large trees only if measurements require it.
- Replace periodic polling with filesystem observation.

### Links and search

- Navigate Markdown hyperlinks and wikilinks.
- Support aliases, anchors, relative paths, and missing notes.
- Keep backlinks correct after save, move, rename, and delete operations.
- Build incremental content, metadata, and link indexes.
- [x] Remove the optional `ripgrep` dependency without silently changing search behavior.
- Move expensive indexing away from the browser's main thread.

### Exit criteria

- Users can create, edit, organize, search, and navigate a Markdown vault.
- Live Preview does not lose content or break undo/redo in covered cases.
- Explorer and search remain responsive with the reference vault.
- No optional runtime system dependency changes application behavior.

## Milestone 2: minimum plugin platform and Tasks

### Plugin platform

- Define `manifest.json` with ID, name, version, API version, entrypoint, and permissions.
- Implement `activate(context)` and `deactivate()`.
- Expose typed APIs for controlled vault access, file/workspace events, commands, shortcuts, persistent settings, declarative views, and CodeMirror extensions.
- Define permissions such as `vault:read`, `vault:write`, `ui`, and `network`.
- Do not expose internal Svelte components.
- Define API compatibility and migration rules.
- Design isolation before enabling arbitrary third-party installation.

### Tasks plugin

- Preserve Markdown checkbox compatibility.
- Add states, dates, priorities, and recurrence.
- Implement task filters and queries.
- Provide commands to create, complete, and reschedule tasks.
- Integrate Live Preview through public extension points.
- Use only APIs available to other plugins unless an exception is documented.

### Exit criteria

- Tasks can be installed, activated, and deactivated without core changes.
- Markdown files remain interoperable.
- The plugin contract covers commands, settings, events, views, and editor extensions.
- Any limitation discovered through Tasks is resolved in the general API rather than private access.

## Milestone 3: Git integration

- Show vault status and per-file changes.
- Display readable diffs.
- Allow explicit selection and commit creation.
- Keep pull and push separate, confirmed operations with visible progress.
- Detect conflicts without resolving them automatically.
- Never overwrite files or discard local changes.
- Preserve normal Git use outside the application.
- Expose Git capabilities to plugins only through separate permissions.

## Milestone 4: Periodic Notes

- Daily notes (`POST /api/periodic/today`, calendar panel, configurable folder/format/template, and Obsidian import) are implemented.
- Remaining: weekly/monthly notes, period navigation commands, and extraction to the plugin API.

## Milestone 5: Folder Notes

- `Folder/Folder.md` detection, explorer hiding, and Obsidian import (`folder-notes`) are implemented.
- Remaining: configurable folder-note conventions, creation from the explorer, and extraction to the plugin API.

## Milestone 6: additional plugins

- Prioritize extensions based on real usage.
- Expand the API only when multiple capabilities share the same need.
- Consider another scripting language only if TypeScript is insufficient for recurring automation cases.

## Milestone 7: advanced Excalidraw

- Strengthen round-trip compatibility for `.excalidraw` and `.excalidraw.md`.
- Support embeds, associated files, and required fonts consistently.
- Recover from invalid content without overwriting the original file.
- Keep the editor and renderer usable under the application's documented network requirements.
- Decide whether it remains an isolated official integration or becomes a plugin.

## Deferred decisions

### Distribution

Decide after Milestone 1. Compare options by corporate installation, updates, and maintenance cost. A single binary is not required.

### Rust or Go

Evaluate only if Python misses concrete targets after incremental indexing and file observation. Compare implementations with the same reference vault and Priority 0 metrics.

### Native wrapper

Consider Tauri or another wrapper only if it provides required OS integration or materially simpler corporate distribution.

### Second plugin language

TypeScript is the only initial plugin language. Add Lua or another runtime only if frequent small automations justify its runtime and bindings.
