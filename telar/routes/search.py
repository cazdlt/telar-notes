"""Search routes."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query

from telar.deps import VaultDep
from telar.search import collect_tags, search_notes

router = APIRouter()


@router.get("/api/search")
def get_search(
    vault: VaultDep,
    q: Annotated[str, Query()] = "",
    mode: Annotated[str, Query()] = "all",
) -> dict[str, Any]:
    """Search notes in the active vault by title, content, tags, or links."""
    return {"results": search_notes(vault, q, mode)}


@router.get("/api/tags")
def get_tags(vault: VaultDep) -> dict[str, Any]:
    """List all tags across the active vault with note counts."""
    return {"tags": collect_tags(vault)}
