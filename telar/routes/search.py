"""Search routes."""

from __future__ import annotations

import pathlib
from typing import Any

from fastapi import APIRouter, Depends

from telar.deps import get_vault
from telar.search import search_notes

router = APIRouter()


@router.get("/api/search")
def get_search(
    q: str = "",
    mode: str = "all",
    vault: pathlib.Path = Depends(get_vault),
) -> dict[str, Any]:
    """Search notes in the active vault by title, content, tags, or links."""
    return {"results": search_notes(vault, q, mode)}
