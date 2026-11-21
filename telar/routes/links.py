"""Link index read and rebuild routes."""

from __future__ import annotations

import pathlib
from typing import Annotated, Any

from fastapi import APIRouter, Query

from telar.deps import StateDep, VaultDep
from telar.links import build_links_index, load_links_index, write_links_index

router = APIRouter()


@router.get("/api/links")
def get_links(
    state: StateDep,
    active: VaultDep,
    vault_param: Annotated[str | None, Query(alias="vault")] = None,
) -> dict[str, Any]:
    """Return forward/backward link index for one vault or all vaults."""
    cfg = state.config.load()
    vaults = cfg.get("vaults", [])
    if vault_param == "__all__" and vaults:
        merged: dict[str, Any] = {}
        for v in vaults:
            vp = pathlib.Path(v["path"])
            idx = load_links_index(vp)
            for k, entry in idx.items():
                merged[f"{v['name']}/{k}"] = {
                    "links_to": [f"{v['name']}/{t}" for t in entry.get("links_to", [])],
                    "linked_from": [
                        f"{v['name']}/{t}" for t in entry.get("linked_from", [])
                    ],
                }
        return merged
    if vault_param:
        vp = next(
            (pathlib.Path(v["path"]) for v in vaults if v["name"] == vault_param),
            active,
        )
        return load_links_index(vp)
    return load_links_index(active)


@router.post("/api/links/rebuild")
def post_links_rebuild(vault: VaultDep) -> dict[str, Any]:
    """Rebuild the link index from disk for the active vault."""
    index = build_links_index(vault)
    write_links_index(vault, index)
    return index
