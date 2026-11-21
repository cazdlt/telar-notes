"""Shared FastAPI dependencies and response helpers."""

from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Header, Request
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


StateDep = Annotated[AppState, Depends(get_state)]


def get_vault(
    state: StateDep,
    x_vault: Annotated[str | None, Header(alias="X-Vault")] = None,
) -> pathlib.Path:
    """Resolve the active vault for this request, honoring ``X-Vault``."""
    return active_vault(
        state.fallback_vault,
        state.config,
        state.session_path,
        x_vault,
    )


VaultDep = Annotated[pathlib.Path, Depends(get_vault)]


def api_error(status: int, message: str, **extra: Any) -> JSONResponse:
    """Return a JSON error response matching the ``{"error": ...}`` contract."""
    return JSONResponse({"error": message, **extra}, status_code=status)
