"""Shared FastAPI dependencies and response helpers."""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from telar.config import TelarConfig
from telar.vault import active_vault


@dataclass
class AppState:
    """Runtime dependencies bound to a Telar FastAPI application."""

    fallback_vault: pathlib.Path
    config: TelarConfig
    session_path: str
    activity: dict[str, float]


def get_state(request: Request) -> AppState:
    """Return the ``AppState`` attached to the FastAPI app."""
    return request.app.state.telar


def get_vault(request: Request, state: AppState = Depends(get_state)) -> pathlib.Path:
    """Resolve the active vault for this request, honoring ``X-Vault``."""
    return active_vault(
        state.fallback_vault,
        state.config,
        state.session_path,
        request.headers.get("X-Vault"),
    )


async def read_json_body(request: Request) -> dict[str, Any]:
    """Parse an optional JSON object body, returning ``{}`` when empty."""
    raw = await request.body()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=400, detail="invalid json") from error
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="json object required")
    return parsed


def api_error(status: int, message: str, **extra: Any) -> JSONResponse:
    """Return a JSON error response matching the ``{"error": ...}`` contract."""
    return JSONResponse({"error": message, **extra}, status_code=status)
