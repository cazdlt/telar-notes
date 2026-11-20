"""Task query, block lookup, status/date updates, and block ID routes."""

from __future__ import annotations

import pathlib
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import JSONResponse

from telar.config import vault_settings
from telar.deps import AppState, api_error, get_state, get_vault, read_json_body
from telar.task_query import query_tasks
from telar.tasks import (
    TaskLocationError,
    ensure_task_block_id,
    parse_tasks,
    update_task_line,
)
from telar.vault import resolve_vault_path

router = APIRouter()


@router.get("/api/tasks")
def get_tasks(
    query: str = "",
    source: str | None = None,
    vault: pathlib.Path = Depends(get_vault),
) -> dict[str, Any]:
    """Execute a Tasks query against the active vault."""
    return query_tasks(vault, query, source)


@router.get("/api/tasks/block")
def get_task_block(
    path: str = "",
    block_id: str = Query(default="", alias="id"),
    vault: pathlib.Path = Depends(get_vault),
) -> Response:
    """Return the task record matching ``^id`` in ``path``."""
    try:
        target = resolve_vault_path(vault, path)
    except ValueError:
        return api_error(403, "forbidden")
    if not path or not target.is_file():
        return api_error(404, "not found")
    task = next(
        (t for t in parse_tasks(target.read_text(), path) if t["block_id"] == block_id),
        None,
    )
    if task is None:
        return api_error(404, "task not found")
    return JSONResponse({"task": task})


@router.post("/api/tasks/update")
def post_tasks_update(
    body: dict[str, Any] = Depends(read_json_body),
    state: AppState = Depends(get_state),
    vault: pathlib.Path = Depends(get_vault),
) -> Response:
    """Apply a status, date, or priority patch to a task line."""
    location, patch = body.get("location"), body.get("patch")
    if not isinstance(patch, dict):
        return api_error(400, "location and patch required")
    settings = vault_settings(state.config.load(), vault)["plugins"]["tasks"]
    try:
        result = update_task_line(vault, location, patch, settings)
    except TaskLocationError as error:
        return api_error(error.status, str(error))
    except ValueError as error:
        return api_error(400, str(error))
    return JSONResponse(result)


@router.post("/api/tasks/block-id")
def post_tasks_block_id(
    body: dict[str, Any] = Depends(read_json_body),
    vault: pathlib.Path = Depends(get_vault),
) -> Response:
    """Ensure a task line has a unique ``^id`` block identifier."""
    try:
        result = ensure_task_block_id(vault, body.get("location"))
    except TaskLocationError as error:
        return api_error(error.status, str(error))
    return JSONResponse(result)
