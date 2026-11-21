"""Streamable HTTP MCP server exposing Telar Notes vaults to AI clients."""

from __future__ import annotations

import pathlib
from datetime import datetime
from typing import Any, Literal

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from telar.config import atomic_write_text, vault_settings
from telar.deps import AppState
from telar.links import update_links_index
from telar.search import search_notes as run_search_notes
from telar.sections import (
    SectionError,
    parse_outline,
    read_lines,
    read_section,
)
from telar.sections import (
    patch_note as apply_note_patch,
)
from telar.task_query import query_tasks as run_query_tasks
from telar.tasks import (
    TaskLocationError,
    add_task_line,
    invalidate_tasks,
    parse_iso_date,
    update_task_line,
)
from telar.vault import (
    RECENT_LIMIT_MAX,
    active_vault,
    build_tree,
    format_periodic_date,
    render_periodic_template,
    resolve_vault_path,
    revision,
    vaults_payload,
)
from telar.vault import (
    recent_files as list_recent_files,
)

MCP_INSTRUCTIONS = """\
You are connected to a Telar Notes Markdown vault over MCP.

Session bootstrap:
- On first use against a vault in a session, check for vault-specific instructions
  at the vault root (`CLAUDE.md` or `AGENTS.md`) via `read_note`. If either exists,
  follow its conventions (language, folder layout, task formatting, confirmation
  rules) for the rest of the session.

Recommended workflow:
1. Discover notes with `list_files`, `recent_files`, or `search_notes`.
2. Inspect structure with `note_outline` before reading large notes.
3. Read selectively with `read_note` using `section` ("Parent > Child", case/accent
   insensitive) or `start_line`/`end_line`.
4. Edit surgically with `patch_note`, `add_task`, or `update_task`. Use
   `dry_run=true` to preview unified diffs and `base_revision` for optimistic
   locking on concurrent edits.

Multi-vault:
- Call `list_vaults` to see available vaults. Pass `vault="<name>"` on any tool
  call (or send the `X-Vault` HTTP header) to target a specific vault.
"""

_READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)
_WRITE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=False,
)


def _header_vault(ctx: Context) -> str | None:
    """Extract the optional ``X-Vault`` header from the current MCP HTTP request."""
    headers = ctx.headers
    if headers is None:
        return None
    return headers.get("x-vault") or headers.get("X-Vault")


def _resolve_vault(
    state: AppState,
    ctx: Context,
    vault: str | None = None,
) -> pathlib.Path:
    """Resolve the target vault from explicit arg, ``X-Vault`` header, or session."""
    if vault:
        cfg = state.config.load()
        configured = cfg.get("vaults") or []
        named = next((v for v in configured if v.get("name") == vault), None)
        if named and named.get("path"):
            return pathlib.Path(named["path"])
        if not configured and state.fallback_vault.name == vault:
            return state.fallback_vault
        raise ToolError(f"unknown vault: {vault}")
    return active_vault(
        state.fallback_vault,
        state.config,
        state.session_path,
        _header_vault(ctx),
    )


def _read_existing_note(
    vault_path: pathlib.Path, path: str
) -> tuple[pathlib.Path, str]:
    """Validate a vault-relative note path and return ``(target, text)``."""
    if not path:
        raise ToolError("path is required")
    try:
        target = resolve_vault_path(vault_path, path)
    except ValueError as error:
        raise ToolError("path is outside the vault") from error
    if not target.exists() or not target.is_file():
        raise ToolError(f"note not found: {path}")
    try:
        return target, target.read_text()
    except UnicodeDecodeError as error:
        raise ToolError(f"not a UTF-8 text file: {path}") from error


def _format_section_error(error: SectionError) -> str:
    """Format a ``SectionError`` with candidate matches when ambiguous."""
    matches = error.extra.get("matches")
    if isinstance(matches, list) and matches:
        return f"{error.message} (matches: {', '.join(str(m) for m in matches)})"
    return error.message


def create_mcp_server(state: AppState) -> MCPServer:
    """Create a Telar Notes ``MCPServer`` bound to ``state``."""
    mcp = MCPServer(
        name="telar-notes",
        title="Telar Notes",
        description="Read, search, create, and surgically edit Markdown notes and Obsidian tasks in Telar Notes vaults.",
        instructions=MCP_INSTRUCTIONS,
    )

    @mcp.tool(annotations=_READ_ONLY)
    def list_vaults(ctx: Context) -> dict[str, Any]:
        """List configured vaults along with the active and default vault names."""
        cfg = state.config.load()
        payload = vaults_payload(
            state.fallback_vault,
            state.config,
            state.session_path,
            cfg,
            override=_header_vault(ctx),
        )
        sanitized = [
            {k: v for k, v in entry.items() if k in ("name", "icon")}
            for entry in payload["vaults"]
        ]
        return {
            "vaults": sanitized,
            "active": payload["active"],
            "default": payload["default"],
        }

    @mcp.tool(annotations=_READ_ONLY)
    def list_files(
        ctx: Context,
        vault: str | None = None,
    ) -> dict[str, Any]:
        """Return the visible file and directory tree for the vault."""
        vault_path = _resolve_vault(state, ctx, vault)
        return {"tree": build_tree(vault_path)}

    @mcp.tool(annotations=_READ_ONLY)
    def recent_files(
        ctx: Context,
        sort: Literal["modified", "created"] = "modified",
        limit: int = 20,
        vault: str | None = None,
    ) -> dict[str, Any]:
        """Return recently modified or created notes and media files, newest first."""
        vault_path = _resolve_vault(state, ctx, vault)
        clamped = min(max(limit, 1), RECENT_LIMIT_MAX)
        return {"files": list_recent_files(vault_path, sort, clamped)}

    @mcp.tool(annotations=_READ_ONLY)
    def search_notes(
        ctx: Context,
        query: str,
        mode: Literal["all", "title", "content", "tags", "links"] = "all",
        vault: str | None = None,
    ) -> dict[str, Any]:
        """Search notes in the vault by title, content, tags, links, or all."""
        vault_path = _resolve_vault(state, ctx, vault)
        return {"results": run_search_notes(vault_path, query, mode)}

    @mcp.tool(annotations=_READ_ONLY)
    def note_outline(
        ctx: Context,
        path: str,
        vault: str | None = None,
    ) -> dict[str, Any]:
        """Return the Markdown heading outline (with line ranges) and current revision for a note."""
        vault_path = _resolve_vault(state, ctx, vault)
        _, content = _read_existing_note(vault_path, path)
        return {
            "path": path,
            "revision": revision(content),
            "headings": parse_outline(content),
        }

    @mcp.tool(annotations=_READ_ONLY)
    def read_note(
        ctx: Context,
        path: str,
        section: str | None = None,
        start_line: int | None = None,
        end_line: int | None = None,
        vault: str | None = None,
    ) -> dict[str, Any]:
        """Read a note in full, by heading section ("Parent > Child"), or by 1-based line range."""
        if section is not None and (start_line is not None or end_line is not None):
            raise ToolError("cannot combine section with start_line or end_line")
        vault_path = _resolve_vault(state, ctx, vault)
        _, content = _read_existing_note(vault_path, path)
        rev = revision(content)
        if section is None and start_line is None and end_line is None:
            return {"path": path, "content": content, "revision": rev}
        try:
            slice_payload = (
                read_section(content, section)
                if section is not None
                else read_lines(content, start_line, end_line)
            )
        except SectionError as error:
            raise ToolError(_format_section_error(error)) from error
        return {"path": path, "revision": rev, **slice_payload}

    @mcp.tool(annotations=_WRITE)
    def create_note(
        ctx: Context,
        path: str,
        content: str = "",
        vault: str | None = None,
    ) -> dict[str, Any]:
        """Create a new note atomically. Fails if a file already exists at ``path``."""
        if not path:
            raise ToolError("path is required")
        vault_path = _resolve_vault(state, ctx, vault)
        try:
            target = resolve_vault_path(vault_path, path)
        except ValueError as error:
            raise ToolError("path is outside the vault") from error
        if target.exists():
            raise ToolError(f"note already exists: {path}")
        atomic_write_text(target, content)
        update_links_index(vault_path, path, content)
        invalidate_tasks(vault_path, path)
        return {"ok": True, "path": path, "revision": revision(content)}

    @mcp.tool(annotations=_WRITE)
    def patch_note(
        ctx: Context,
        path: str,
        op: Literal["insert", "replace_section", "replace_text"],
        content: str | None = None,
        anchor: Literal[
            "after_heading",
            "end_of_section",
            "before_heading",
            "end_of_file",
            "start_of_file",
        ]
        | None = None,
        heading: str | None = None,
        old: str | None = None,
        new: str | None = None,
        base_revision: str | None = None,
        dry_run: bool = False,
        vault: str | None = None,
    ) -> dict[str, Any]:
        """Surgically edit an existing note atomically with optional optimistic locking and dry-run diff.

        Operations:
        - ``insert``: requires ``anchor`` and ``content`` (plus ``heading`` for heading anchors).
        - ``replace_section``: requires ``heading`` and ``content``.
        - ``replace_text``: requires unique ``old`` substring and ``new`` replacement.
        """
        vault_path = _resolve_vault(state, ctx, vault)
        target, existing = _read_existing_note(vault_path, path)
        current_rev = revision(existing)
        if base_revision is not None and base_revision != current_rev:
            raise ToolError(f"note changed on disk (current revision: {current_rev})")
        payload: dict[str, Any] = {"op": op}
        if content is not None:
            payload["content"] = content
        if anchor is not None:
            payload["anchor"] = anchor
        if heading is not None:
            payload["heading"] = heading
        if old is not None:
            payload["old"] = old
        if new is not None:
            payload["new"] = new
        try:
            new_content, diff = apply_note_patch(existing, path, payload)
        except SectionError as error:
            raise ToolError(_format_section_error(error)) from error
        if dry_run:
            return {"ok": True, "dry_run": True, "revision": current_rev, "diff": diff}
        atomic_write_text(target, new_content)
        update_links_index(vault_path, path, new_content)
        invalidate_tasks(vault_path, path)
        return {"ok": True, "revision": revision(new_content), "diff": diff}

    @mcp.tool(annotations=_WRITE)
    def open_daily_note(
        ctx: Context,
        date: str | None = None,
        vault: str | None = None,
    ) -> dict[str, Any]:
        """Open or create a periodic daily note (defaults to today, or YYYY-MM-DD)."""
        vault_path = _resolve_vault(state, ctx, vault)
        settings = vault_settings(state.config.load(), vault_path)["plugins"][
            "periodic-notes"
        ]
        if not settings["enabled"]:
            raise ToolError("Periodic Notes is disabled for this vault")
        try:
            dt = parse_iso_date(date) if date is not None else datetime.now()
        except ValueError as error:
            raise ToolError("invalid date (expected YYYY-MM-DD)") from error
        folder, pattern, template_path = (
            settings["folder"],
            settings["format"],
            settings["template"],
        )
        if not all(
            isinstance(value, str)
            and value
            and not pathlib.PurePosixPath(value).is_absolute()
            for value in (folder, pattern, template_path)
        ):
            raise ToolError("invalid periodic notes settings")
        relative = (
            pathlib.PurePosixPath(folder) / f"{format_periodic_date(dt, pattern)}.md"
        )
        try:
            target = resolve_vault_path(vault_path, str(relative))
            source = resolve_vault_path(vault_path, template_path).resolve()
        except ValueError as error:
            raise ToolError("periodic note path is outside the vault") from error
        created = False
        if not target.exists():
            if not source.is_file():
                raise ToolError("daily template not found")
            try:
                rendered = render_periodic_template(source.read_text(), dt)
            except UnicodeDecodeError as error:
                raise ToolError("daily template is not text") from error
            atomic_write_text(target, rendered)
            update_links_index(vault_path, relative.as_posix(), rendered)
            invalidate_tasks(vault_path, relative.as_posix())
            created = True
        content = target.read_text()
        return {
            "path": relative.as_posix(),
            "created": created,
            "content": content,
            "revision": revision(content),
        }

    @mcp.tool(annotations=_READ_ONLY)
    def query_tasks(
        ctx: Context,
        query: str = "",
        source: str | None = None,
        vault: str | None = None,
    ) -> dict[str, Any]:
        """Run an Obsidian Tasks query across the vault (e.g. ``not done``)."""
        vault_path = _resolve_vault(state, ctx, vault)
        return run_query_tasks(vault_path, query, source)

    @mcp.tool(annotations=_WRITE)
    def add_task(
        ctx: Context,
        path: str,
        description: str,
        status: str = " ",
        priority: str | None = None,
        dates: dict[str, str] | None = None,
        tags: list[str] | None = None,
        block_id: str | None = None,
        children: list[str] | None = None,
        anchor: Literal[
            "end_of_file",
            "start_of_file",
            "after_heading",
            "end_of_section",
            "before_heading",
        ] = "end_of_file",
        heading: str | None = None,
        dry_run: bool = False,
        vault: str | None = None,
    ) -> dict[str, Any]:
        """Format and insert a canonical Obsidian Tasks line into an existing note."""
        vault_path = _resolve_vault(state, ctx, vault)
        payload: dict[str, Any] = {
            "path": path,
            "description": description,
            "status": status,
            "anchor": anchor,
            "dry_run": dry_run,
        }
        if priority is not None:
            payload["priority"] = priority
        if dates is not None:
            payload["dates"] = dates
        if tags is not None:
            payload["tags"] = tags
        if block_id is not None:
            payload["block_id"] = block_id
        if children is not None:
            payload["children"] = children
        if heading is not None:
            payload["heading"] = heading
        try:
            return add_task_line(vault_path, payload)
        except (TaskLocationError, ValueError) as error:
            raise ToolError(str(error)) from error

    @mcp.tool(annotations=_WRITE)
    def update_task(
        ctx: Context,
        path: str,
        line: int | None = None,
        block_id: str | None = None,
        match: str | None = None,
        expected: str | None = None,
        status: str | None = None,
        description: str | None = None,
        priority: str | None = None,
        dates: dict[str, str | None] | None = None,
        set_block_id: str | None = None,
        append_children: list[str] | None = None,
        dry_run: bool = False,
        vault: str | None = None,
    ) -> dict[str, Any]:
        """Update an existing task located by ``block_id``, unique ``match``, or 1-based ``line``."""
        vault_path = _resolve_vault(state, ctx, vault)
        location: dict[str, Any] = {"path": path}
        if block_id is not None:
            location["block_id"] = block_id
        elif match is not None:
            location["match"] = match
        elif line is not None:
            location["line"] = line
            if expected is not None:
                location["expected"] = expected
        else:
            raise ToolError("one of block_id, match, or line is required")

        patch: dict[str, Any] = {}
        if status is not None:
            patch["status"] = status
        if description is not None:
            patch["description"] = description
        if priority is not None:
            patch["priority"] = priority
        if dates is not None:
            patch["dates"] = dates
        if set_block_id is not None:
            patch["block_id"] = set_block_id
        if append_children is not None:
            patch["append_children"] = append_children
        if not patch:
            raise ToolError("at least one task field to update is required")

        settings = vault_settings(state.config.load(), vault_path)["plugins"]["tasks"]
        try:
            return update_task_line(
                vault_path, location, patch, settings, dry_run=dry_run
            )
        except (TaskLocationError, ValueError) as error:
            raise ToolError(str(error)) from error

    return mcp
