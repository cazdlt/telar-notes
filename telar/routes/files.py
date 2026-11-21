"""File tree, note CRUD, raw files, attachments, periodic notes, and Finder reveal."""

from __future__ import annotations

import base64
import mimetypes
import pathlib
import shutil
import subprocess
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, Header, Query, Response
from fastapi.responses import FileResponse, JSONResponse

from telar.config import atomic_write_text, vault_settings
from telar.deps import StateDep, VaultDep, api_error
from telar.links import update_links_index
from telar.schemas import (
    AttachRequest,
    NotePatchRequest,
    NoteWriteRequest,
    PathRequest,
    PeriodicTodayRequest,
    RenameRequest,
)
from telar.sections import (
    parse_outline,
    patch_note,
    read_lines,
    read_section,
)
from telar.tasks import invalidate_tasks, parse_iso_date
from telar.vault import (
    RECENT_LIMIT_MAX,
    attachment_dir,
    build_tree,
    format_periodic_date,
    recent_files,
    render_periodic_template,
    resolve_vault_path,
    revision,
    unique_dest,
)

router = APIRouter()


@router.get("/api/files")
def get_files(vault: VaultDep) -> dict[str, Any]:
    """Return the visible file and directory tree for the active vault."""
    return {"tree": build_tree(vault)}


@router.get("/api/files/recent")
def get_recent_files(
    vault: VaultDep,
    sort: Annotated[Literal["modified", "created"], Query()] = "modified",
    limit: Annotated[int, Query()] = 50,
) -> Response:
    """Return recently modified or created openable files."""
    clamped = min(max(limit, 1), RECENT_LIMIT_MAX)
    return JSONResponse({"files": recent_files(vault, sort, clamped)})


def _read_existing_note(
    vault: pathlib.Path, path: str | None
) -> tuple[pathlib.Path, str] | Response:
    """Validate a vault-relative note path and return ``(target, text)`` or an error."""
    if not path or not isinstance(path, str):
        return api_error(400, "path required")
    try:
        target = resolve_vault_path(vault, path)
    except ValueError:
        return api_error(403, "forbidden")
    if not target.exists() or not target.is_file():
        return api_error(404, "not found")
    try:
        return target, target.read_text()
    except UnicodeDecodeError:
        return api_error(415, "not a text file")


@router.get("/api/note/outline")
def get_note_outline(
    vault: VaultDep,
    path: Annotated[str | None, Query()] = None,
) -> Response:
    """Return the Markdown heading outline and current revision for a note."""
    loaded = _read_existing_note(vault, path)
    if isinstance(loaded, Response):
        return loaded
    _, content = loaded
    rev = revision(content)
    return JSONResponse(
        {"path": path, "revision": rev, "headings": parse_outline(content)},
        headers={"ETag": rev},
    )


@router.get("/api/note")
def get_note(
    vault: VaultDep,
    path: Annotated[str | None, Query()] = None,
    section: Annotated[str | None, Query()] = None,
    start_line: Annotated[int | None, Query()] = None,
    end_line: Annotated[int | None, Query()] = None,
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
) -> Response:
    """Read a UTF-8 note (full, by section, or by line range) with ETag support."""
    if section is not None and (start_line is not None or end_line is not None):
        return api_error(400, "cannot combine section with start_line or end_line")
    loaded = _read_existing_note(vault, path)
    if isinstance(loaded, Response):
        return loaded
    _, content = loaded
    rev = revision(content)
    if section is None and start_line is None and end_line is None:
        if if_none_match == rev:
            return Response(status_code=304, headers={"ETag": rev})
        return JSONResponse(
            {"path": path, "content": content, "revision": rev},
            headers={"ETag": rev},
        )
    slice_payload = (
        read_section(content, section)
        if section is not None
        else read_lines(content, start_line, end_line)
    )
    return JSONResponse(
        {"path": path, "revision": rev, **slice_payload},
        headers={"ETag": rev},
    )


@router.post("/api/note/patch")
def post_note_patch(
    body: NotePatchRequest,
    vault: VaultDep,
) -> Response:
    """Apply a surgical patch to an existing note with optional concurrency check."""
    loaded = _read_existing_note(vault, body.path)
    if isinstance(loaded, Response):
        return loaded
    target, content = loaded
    current_rev = revision(content)
    if body.base_revision is not None and body.base_revision != current_rev:
        return api_error(409, "note changed on disk", revision=current_rev)
    new_content, diff = patch_note(
        content, body.path, body.model_dump(exclude_none=True)
    )
    if body.dry_run:
        return JSONResponse(
            {"ok": True, "dry_run": True, "revision": current_rev, "diff": diff}
        )
    atomic_write_text(target, new_content)
    update_links_index(vault, body.path, new_content)
    invalidate_tasks(vault, body.path)
    return JSONResponse({"ok": True, "revision": revision(new_content), "diff": diff})


@router.get("/api/raw")
def get_raw(
    vault: VaultDep,
    path: Annotated[str | None, Query()] = None,
) -> Response:
    """Serve raw file bytes with a detected Content-Type."""
    if not path:
        return api_error(400, "path required")
    try:
        target = resolve_vault_path(vault, path)
    except ValueError:
        return api_error(403, "forbidden")
    if not target.exists() or not target.is_file():
        return api_error(404, "not found")
    ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    headers = {
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; sandbox",
    }
    if target.suffix.lower() in {".html", ".htm", ".xhtml", ".svg", ".xml"}:
        headers["Content-Disposition"] = f'attachment; filename="{target.name}"'
    return FileResponse(target, media_type=ctype, headers=headers)


@router.post("/api/note")
def post_note(
    body: NoteWriteRequest,
    vault: VaultDep,
) -> Response:
    """Create or update a note atomically with optimistic concurrency."""
    try:
        target = resolve_vault_path(vault, body.path)
    except ValueError:
        return api_error(400, "path outside vault")
    previous = target.read_text() if target.exists() else None
    current_revision = revision(previous) if previous is not None else None
    if (
        previous is not None
        and not body.force
        and body.base_revision != current_revision
    ):
        return api_error(
            409,
            "note changed on disk",
            revision=current_revision,
            content=previous,
        )
    if previous is None and body.base_revision not in (None, ""):
        return api_error(409, "note was removed")
    atomic_write_text(target, body.content)
    update_links_index(vault, body.path, body.content)
    invalidate_tasks(vault, body.path)
    return JSONResponse({"ok": True, "revision": revision(body.content)})


@router.post("/api/periodic/today")
def post_periodic_today(
    state: StateDep,
    vault: VaultDep,
    body: Annotated[PeriodicTodayRequest | None, Body()] = None,
) -> Response:
    """Open or create a periodic daily note from the configured template."""
    settings = vault_settings(state.config.load(), vault)["plugins"]["periodic-notes"]
    if not settings["enabled"]:
        return api_error(409, "Periodic Notes is disabled")
    raw_date = body.date if body is not None else None
    try:
        dt = parse_iso_date(raw_date) if raw_date is not None else datetime.now()
    except ValueError:
        return api_error(400, "invalid date")
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
        return api_error(400, "invalid periodic notes settings")
    relative = pathlib.PurePosixPath(folder) / f"{format_periodic_date(dt, pattern)}.md"
    try:
        target = resolve_vault_path(vault, str(relative))
        source = resolve_vault_path(vault, template_path).resolve()
    except ValueError:
        return api_error(400, "path outside vault")
    created = False
    if not target.exists():
        if not source.is_file():
            return api_error(409, "daily template not found")
        try:
            content = render_periodic_template(source.read_text(), dt)
        except UnicodeDecodeError:
            return api_error(415, "daily template is not text")
        atomic_write_text(target, content)
        update_links_index(vault, relative.as_posix(), content)
        invalidate_tasks(vault, relative.as_posix())
        created = True
    content = target.read_text()
    return JSONResponse(
        {
            "path": relative.as_posix(),
            "created": created,
            "content": content,
            "revision": revision(content),
        }
    )


@router.post("/api/attach")
def post_attach(
    body: AttachRequest,
    state: StateDep,
    vault: VaultDep,
) -> Response:
    """Save a base64-encoded attachment into the configured attachment folder."""
    try:
        raw_bytes = base64.b64decode(body.data_b64, validate=True)
    except ValueError:
        return api_error(400, "invalid base64 data")

    vault_root = vault.resolve()
    if body.dir:
        dest_dir = vault if body.dir == "." else vault / body.dir
        dest = dest_dir / body.filename
        try:
            dest.resolve().relative_to(vault_root)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest = unique_dest(dest)
            dest.resolve().relative_to(vault_root)
        except ValueError:
            return api_error(403, "forbidden")
        dest.write_bytes(raw_bytes)
        rel = dest.relative_to(vault).as_posix()
        return JSONResponse({"ok": True, "embed": rel, "path": rel})

    assert body.note is not None
    folder = vault_settings(state.config.load(), vault)["files"]
    dest = attachment_dir(vault, body.note, folder["attachment_folder"]) / body.filename
    try:
        dest.resolve().relative_to(vault_root)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest = unique_dest(dest)
        dest.resolve().relative_to(vault_root)
    except ValueError:
        return api_error(403, "forbidden")
    dest.write_bytes(raw_bytes)
    return JSONResponse(
        {
            "ok": True,
            "embed": dest.name,
            "path": dest.relative_to(vault).as_posix(),
        }
    )


@router.post("/api/mkdir")
def post_mkdir(
    body: PathRequest,
    vault: VaultDep,
) -> Response:
    """Create a directory inside the active vault."""
    try:
        target = resolve_vault_path(vault, body.path)
    except ValueError:
        return api_error(400, "path outside vault")
    if target.exists():
        return api_error(409, "exists")
    target.mkdir(parents=True, exist_ok=False)
    return JSONResponse({"ok": True})


@router.post("/api/rename")
def post_rename(
    body: RenameRequest,
    vault: VaultDep,
) -> Response:
    """Move or rename a file or directory without overwriting."""
    try:
        src = resolve_vault_path(vault, body.src)
        dst = resolve_vault_path(vault, body.dst)
    except ValueError:
        return api_error(400, "path outside vault")
    if not src.exists():
        return api_error(404, "not found")
    if dst.exists():
        return api_error(409, "exists")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return JSONResponse({"ok": True})


@router.post("/api/delete")
def post_delete(
    body: PathRequest,
    vault: VaultDep,
) -> Response:
    """Soft-delete a file or directory into ``.trash/``."""
    try:
        target = resolve_vault_path(vault, body.path)
    except ValueError:
        return api_error(400, "path outside vault")
    if not target.exists():
        return api_error(404, "not found")
    trash_dir = vault / ".trash"
    trash_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = trash_dir / f"{stamp}-{target.name}"
    shutil.move(str(target), str(dest))
    return JSONResponse(
        {"ok": True, "trashed": str(dest.relative_to(vault).as_posix())}
    )


@router.post("/api/reveal")
def post_reveal(
    body: PathRequest,
    vault: VaultDep,
) -> Response:
    """Reveal a vault-relative file or folder in macOS Finder."""
    try:
        target = resolve_vault_path(vault, body.path)
    except ValueError:
        return api_error(400, "path outside vault")
    if not target.exists():
        return api_error(404, "not found")
    import sys

    if sys.platform == "darwin":
        cmd = ["open", "-R", str(target)]
    elif sys.platform == "win32":
        cmd = ["explorer", f"/select,{target}"]
    elif shutil.which("xdg-open"):
        cmd = ["xdg-open", str(target.parent)]
    else:
        return api_error(501, "reveal is not supported on this platform")
    try:
        subprocess.run(cmd, check=False)
    except OSError:
        return api_error(500, "reveal failed")
    return JSONResponse({"ok": True})
