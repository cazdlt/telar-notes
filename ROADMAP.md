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
- [x] Create a deterministic 5,000-note benchmark and record the baseline.
- [x] Document the HTTP contracts that must survive frontend migration.
- [x] Add a `uv`-based development launcher under `scripts/dev`.
- [x] Standardize user-facing UI text and repository documentation in English.
- [x] Remove the old welcome illustration and replace it with a minimal empty state.
- [x] Start the explorer collapsed and persist only explicitly expanded folders.
- [x] Autosave 500 ms after typing stops and expose save failures in the UI.
- [x] Add a left action sidebar with a button that opens or creates today's note at `diario/YYYY/MM/YYYY-MM-DD.md`.
- [x] Make the note path focus and reveal the current file in the explorer.

### Artifacts

- HTTP contract: [`docs/http-api.md`](docs/http-api.md)
- Benchmark: `uv run python -m benchmarks.baseline`
- Recorded baseline: [`benchmarks/baseline-5000.json`](benchmarks/baseline-5000.json)

### Exit criteria

- The critical suite completes in under a few seconds and protects data-risk operations.
- Every current feature has an explicit keep, defer, or remove decision.
- Performance measurements are reproducible.
- The PoC can migrate in parts without a full rewrite.

## Milestone 1.1: Svelte foundation and feature parity

### Goal

Replace the monolithic frontend with a typed Svelte application without losing current behavior or changing the HTTP API.

### Scope

- Svelte 5, TypeScript, and Vite using the official frontend toolchain.
- Official CodeMirror 6 packages behind an application-owned typed adapter; do not introduce a Svelte-specific CodeMirror wrapper.
- Native `fetch` behind a typed API client; no general HTTP dependency unless the API develops needs that `fetch` does not cover.
- Svelte state primitives for application state; no external state library at this scale.
- Vitest for focused TypeScript tests and a minimal browser suite only for critical cross-component flows.
- Keep remote assets where they simplify the PoC; full offline operation is not required.

### Non-goals and deferrals

- Keep Mermaid rendering through the Mermaid library and preserve the existing Excalidraw editor, preview, and format interoperability in 1.1. Do not redesign or expand these integrations during the Svelte migration.
- Do not add a command framework, settings framework, plugin runtime, generalized component library, or mobile redesign before a current feature needs it.
- Do not rewrite backend search, backlink extraction, or filesystem polling during the frontend migration. Their scalable replacements belong to 1.2.
- Do not require every legacy implementation detail to become a Svelte component. Small stable integrations may remain framework-independent behind typed boundaries.

### Implementation plan

#### 1. Scaffold and build integration

- [ ] Create the Svelte 5 and TypeScript source tree and Vite configuration without moving the Python backend.
- [x] Add development proxying to the existing HTTP API and make the Python server serve the production Vite build.
- [ ] Keep `scripts/dev` as the single development entrypoint and run both processes with clean shutdown.
- [ ] Add type checking, frontend build, and focused test commands.
- [x] Preserve the deprecated plain frontend at `/legacy` as a temporary rollback path. Removed once unused.

#### 2. Boundaries and state

- [ ] Define TypeScript models for vaults, files, search results, links, backlinks, settings, and API errors.
- [ ] Create one API client module and remove direct network calls from UI components as they migrate.
- [ ] Define explicit state for the active vault, open file, dirty/save status, explorer expansion, panels, and preferences.
- [ ] Create domain modules only for behavior migrated in 1.1: application state, editor, explorer, vaults, links, and search. Add commands, settings, and plugins when their milestones require them.

#### 3. Shell and navigation

- [ ] Migrate the application shell, left action sidebar, panels, empty state, and current desktop layout.
- [ ] Migrate vault selection and switching with pending-save protection.
- [ ] Migrate today's-note navigation using `diario/YYYY/MM/YYYY-MM-DD.md` without default frontmatter.
- [ ] Preserve keyboard behavior and visible loading and error states.

#### 4. Explorer

- [ ] Migrate the collapsed-by-default explorer and persisted expansion state.
- [ ] Preserve file opening, folder expansion, context actions, and Reveal in Finder.
- [ ] Preserve clicking the active file path to expand and focus it in the explorer.
- [ ] Keep all path-sensitive operations on the validated backend API.

#### 5. Editor and persistence

- [ ] Introduce a typed CodeMirror adapter for creation, document replacement, focus, selection, extensions, and teardown.
- [ ] Migrate the current Markdown editing and rendering behavior without expanding syntax support yet.
- [ ] Preserve 500 ms autosave, flush-before-navigation, save status, attachment handling, and raw-file behavior.
- [ ] Keep CodeMirror document state outside Svelte reactivity to avoid duplicate state and cursor regressions.

#### 6. Links, search, and integration bridges

- [ ] Migrate hyperlinks, wikilinks, backlinks, and current search behavior.
- [ ] Integrate the Mermaid library through a narrow renderer module and keep the current Excalidraw editor operational through an isolated bridge; neither needs to become a Svelte component.
- [ ] Keep current attachment and raw-file behavior operational without redesigning their views.
- [ ] Isolate these integrations so their parsers, renderers, and views can be replaced independently in later milestones.

#### 7. Cutover and cleanup

- [ ] Run the existing Python and JavaScript contract tests throughout the migration.
- [ ] Add a small browser suite later; Playwright is deferred for the current cutover.
- [ ] Compare explorer, note-open, search, and link-index timings with the 5,000-note baseline.
- [x] Switch the production entrypoint to Svelte and deprecate the legacy frontend.
- [x] Identify newly unused legacy code and request confirmation before deleting it.

### Exit criteria

- The Vite production build is the default frontend served by Python.
- All Priority 0 behavior remains available and the critical test suite passes.
- No UI component performs ad hoc HTTP calls or owns CodeMirror internals.
- Development still starts through `scripts/dev` and production has one documented start path.
- The reference vault does not show a material regression against the recorded baseline.

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

- Create daily, weekly, and monthly notes.
- Configure paths, filenames, and templates.
- Add navigation commands between periods.
- Preserve common Obsidian conventions.
- Implement it as a plugin over the public API.

## Milestone 5: Folder Notes

- Define a configurable folder-note convention.
- Open or create the folder note from the explorer.
- Support optional automatic creation.
- Implement it as a plugin without special core logic.

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
