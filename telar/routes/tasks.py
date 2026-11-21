"""Task query, block lookup, status/date updates, and block ID routes."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Response
from fastapi.responses import JSONResponse

from telar.config import vault_settings
from telar.deps import StateDep, VaultDep, api_error
from telar.schemas import TaskAddRequest, TaskBlockIdRequest, TaskUpdateRequest
from telar.task_query import query_tasks
from telar.tasks import (
    TaskLocationError,
    add_task_line,
    ensure_task_block_id,
    parse_tasks,
    update_task_line,
)
from telar.vault import resolve_vault_path

router = APIRouter()


@router.get("/api/tasks")
def get_tasks(
    vault: VaultDep,
    query: Annotated[str, Query()] = "",
    source: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    """Execute a Tasks query against the active vault."""
    return query_tasks(vault, query, source)


@router.get("/api/tasks/block")
def get_task_block(
    vault: VaultDep,
    path: Annotated[str, Query()] = "",
    block_id: Annotated[str, Query(alias="id")] = "",
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


@router.post("/api/tasks/add")
def post_tasks_add(
    body: TaskAddRequest,
    vault: VaultDep,
) -> Response:
    """Format and insert a new task line into an existing note."""
    try:
        result = add_task_line(vault, body.model_dump(exclude_none=True))
    except TaskLocationError:
        raise
    except ValueError as error:
        return api_error(400, str(error))
    return JSONResponse(result)


@router.post("/api/tasks/update")
def post_tasks_update(
    body: TaskUpdateRequest,
    state: StateDep,
    vault: VaultDep,
) -> Response:
    """Apply a status, date, or priority patch to a task line."""
    settings = vault_settings(state.config.load(), vault)["plugins"]["tasks"]
    try:
        result = update_task_line(
            vault, body.location, body.patch, settings, dry_run=body.dry_run
        )
    except TaskLocationError:
        raise
    except ValueError as error:
        return api_error(400, str(error))
    return JSONResponse(result)


@router.post("/api/tasks/block-id")
def post_tasks_block_id(
    body: TaskBlockIdRequest,
    vault: VaultDep,
) -> Response:
    """Ensure a task line has a unique ``^id`` block identifier."""
    return JSONResponse(ensure_task_block_id(vault, body.location))
