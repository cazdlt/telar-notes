"""File tree, note CRUD, raw files, attachments, periodic notes, and Finder reveal."""

from __future__ import annotations

import base64
import mimetypes
import pathlib
import shutil
import subprocess
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from telar.config import atomic_write_text, vault_settings
from telar.deps import AppState, api_error, get_state, get_vault, read_json_body
from telar.links import update_links_index
from telar.tasks import invalidate_tasks, parse_iso_date
from telar.vault import (
    RECENT_LIMIT_MAX,
    RECENT_SORTS,
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
def get_files(vault: pathlib.Path = Depends(get_vault)) -> dict[str, Any]:
    """Return the visible file and directory tree for the active vault."""
    return {"tree": build_tree(vault)}


@router.get("/api/files/recent")
def get_recent_files(
    sort: str = "modified",
    limit: str = "50",
    vault: pathlib.Path = Depends(get_vault),
) -> Response:
    """Return recently modified or created openable files."""
    if sort not in RECENT_SORTS:
        return api_error(400, "invalid sort")
    try:
        parsed_limit = int(limit)
    except ValueError:
        return api_error(400, "invalid limit")
    clamped = min(max(parsed_limit, 1), RECENT_LIMIT_MAX)
    return JSONResponse({"files": recent_files(vault, sort, clamped)})


@router.get("/api/note")
def get_note(
    request: Request,
    path: str | None = None,
    vault: pathlib.Path = Depends(get_vault),
) -> Response:
    """Read a UTF-8 note with ETag / If-None-Match support."""
    if not path:
        return api_error(400, "path required")
    try:
        target = resolve_vault_path(vault, path)
    except ValueError:
        return api_error(403, "forbidden")
    if not target.exists() or not target.is_file():
        return api_error(404, "not found")
    try:
        content = target.read_text()
    except UnicodeDecodeError:
        return api_error(415, "not a text file")
    rev = revision(content)
    if request.headers.get("If-None-Match") == rev:
        return Response(status_code=304, headers={"ETag": rev})
    return JSONResponse(
        {"path": path, "content": content, "revision": rev},
        headers={"ETag": rev},
    )


@router.get("/api/raw")
def get_raw(
    path: str | None = None,
    vault: pathlib.Path = Depends(get_vault),
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
    return Response(content=target.read_bytes(), media_type=ctype, headers=headers)


@router.post("/api/note")
def post_note(
    body: dict[str, Any] = Depends(read_json_body),
    vault: pathlib.Path = Depends(get_vault),
) -> Response:
    """Create or update a note atomically with optimistic concurrency."""
    rel = body.get("path")
    content = body.get("content", "")
    base_revision = body.get("base_revision")
    force = body.get("force") is True
    if not rel or not isinstance(content, str):
        return api_error(400, "path required")
    try:
        target = resolve_vault_path(vault, rel)
    except ValueError:
        return api_error(400, "path outside vault")
    previous = target.read_text() if target.exists() else None
    current_revision = revision(previous) if previous is not None else None
    if previous is not None and not force and base_revision != current_revision:
        return api_error(
            409,
            "note changed on disk",
            revision=current_revision,
            content=previous,
        )
    if previous is None and base_revision not in (None, ""):
        return api_error(409, "note was removed")
    atomic_write_text(target, content)
    update_links_index(vault, rel, content)
    invalidate_tasks(vault, rel)
    return JSONResponse({"ok": True, "revision": revision(content)})


@router.post("/api/periodic/today")
def post_periodic_today(
    body: dict[str, Any] = Depends(read_json_body),
    state: AppState = Depends(get_state),
    vault: pathlib.Path = Depends(get_vault),
) -> Response:
    """Open or create a periodic daily note from the configured template."""
    settings = vault_settings(state.config.load(), vault)["plugins"]["periodic-notes"]
    if not settings["enabled"]:
        return api_error(409, "Periodic Notes is disabled")
    raw_date = body.get("date")
    try:
        dt = parse_iso_date(raw_date) if isinstance(raw_date, str) else datetime.now()
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
    body: dict[str, Any] = Depends(read_json_body),
    state: AppState = Depends(get_state),
    vault: pathlib.Path = Depends(get_vault),
) -> Response:
    """Save a base64-encoded attachment into the configured attachment folder."""
    note = body.get("note")
    filename = body.get("filename")
    data_b64 = body.get("data_b64")
    dir_rel = body.get("dir")
    if (
        not isinstance(filename, str)
        or not filename
        or filename in (".", "..")
        or "/" in filename
        or "\\" in filename
        or not isinstance(data_b64, str)
        or not (note or dir_rel)
    ):
        return api_error(400, "note or dir, plus safe filename and data_b64, required")
    try:
        raw_bytes = base64.b64decode(data_b64, validate=True)
    except ValueError:
        return api_error(400, "invalid base64 data")

    vault_root = vault.resolve()
    if dir_rel:
        if not isinstance(dir_rel, str):
            return api_error(400, "dir must be a string")
        dest_dir = vault if dir_rel == "." else vault / dir_rel
        dest = dest_dir / filename
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

    if not isinstance(note, str):
        return api_error(400, "note must be a string")
    folder = vault_settings(state.config.load(), vault)["files"]
    dest = attachment_dir(vault, note, folder["attachment_folder"]) / filename
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
    body: dict[str, Any] = Depends(read_json_body),
    vault: pathlib.Path = Depends(get_vault),
) -> Response:
    """Create a directory inside the active vault."""
    rel = body.get("path")
    if not rel:
        return api_error(400, "path required")
    try:
        target = resolve_vault_path(vault, rel)
    except ValueError:
        return api_error(400, "path outside vault")
    if target.exists():
        return api_error(409, "exists")
    target.mkdir(parents=True, exist_ok=False)
    return JSONResponse({"ok": True})


@router.post("/api/rename")
def post_rename(
    body: dict[str, Any] = Depends(read_json_body),
    vault: pathlib.Path = Depends(get_vault),
) -> Response:
    """Move or rename a file or directory without overwriting."""
    src_rel = body.get("from")
    dst_rel = body.get("to")
    if not src_rel or not dst_rel:
        return api_error(400, "from and to required")
    try:
        src = resolve_vault_path(vault, src_rel)
        dst = resolve_vault_path(vault, dst_rel)
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
    body: dict[str, Any] = Depends(read_json_body),
    vault: pathlib.Path = Depends(get_vault),
) -> Response:
    """Soft-delete a file or directory into ``.trash/``."""
    rel = body.get("path")
    if not rel:
        return api_error(400, "path required")
    try:
        target = resolve_vault_path(vault, rel)
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
    body: dict[str, Any] = Depends(read_json_body),
    vault: pathlib.Path = Depends(get_vault),
) -> Response:
    """Reveal a vault-relative file or folder in macOS Finder."""
    rel = body.get("path")
    if not rel:
        return api_error(400, "path required")
    try:
        target = resolve_vault_path(vault, rel)
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
