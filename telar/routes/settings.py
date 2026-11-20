"""Configuration, settings, Obsidian import, and vault registry routes."""

from __future__ import annotations

import itertools
import json
import pathlib
import shutil
import subprocess
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from telar.config import (
    HELP_DIR,
    HELP_VAULT_NAME,
    import_obsidian_settings,
    settings_payload,
    validate_preferences,
    vault_settings,
)
from telar.deps import AppState, api_error, get_state, get_vault, read_json_body
from telar.vault import materialize_vaults, registered_vaults, vaults_payload

router = APIRouter()


@router.get("/api/config")
def get_config(state: AppState = Depends(get_state)) -> dict[str, Any]:
    """Return the effective configuration."""
    return state.config.load()


@router.get("/api/settings")
def get_settings(
    state: AppState = Depends(get_state),
    vault: pathlib.Path = Depends(get_vault),
) -> dict[str, Any]:
    """Return preferences and active vault settings."""
    return settings_payload(state.config.load(), vault)


@router.post("/api/settings")
def post_settings(
    body: dict[str, Any] = Depends(read_json_body),
    state: AppState = Depends(get_state),
    vault: pathlib.Path = Depends(get_vault),
) -> Response:
    """Validate and persist preferences and active vault settings."""
    raw_preferences = body.get("preferences")
    raw_vault_settings = body.get("vault_settings")
    if not isinstance(raw_preferences, dict) or not isinstance(
        raw_vault_settings, dict
    ):
        return api_error(400, "preferences and vault_settings required")
    valid_preferences = validate_preferences(raw_preferences)
    normalized = vault_settings(
        {"vault_settings": {str(vault.resolve()): raw_vault_settings}},
        vault,
    )
    cfg = state.config.load()
    cfg["preferences"] = valid_preferences
    entries = cfg.setdefault("vault_settings", {})
    if not isinstance(entries, dict):
        entries = cfg["vault_settings"] = {}
    existing = entries.get(str(vault.resolve()), {})
    entries[str(vault.resolve())] = {
        **(existing if isinstance(existing, dict) else {}),
        **normalized,
    }
    state.config.save(cfg)
    return JSONResponse(settings_payload(cfg, vault))


@router.post("/api/settings/import-obsidian")
def post_import_obsidian(
    state: AppState = Depends(get_state),
    vault: pathlib.Path = Depends(get_vault),
) -> dict[str, Any]:
    """Import supported plugin and attachment settings from ``.obsidian/``."""
    cfg = import_obsidian_settings(state.config.load(), vault)
    state.config.save(cfg)
    return settings_payload(cfg, vault)


@router.get("/api/vaults")
def get_vaults(
    request: Request,
    state: AppState = Depends(get_state),
) -> dict[str, Any]:
    """List registered vaults along with active and default names."""
    return vaults_payload(
        state.fallback_vault,
        state.config,
        state.session_path,
        state.config.load(),
        request.headers.get("X-Vault"),
    )


@router.post("/api/session/vault")
def post_session_vault(
    body: dict[str, Any] = Depends(read_json_body),
    state: AppState = Depends(get_state),
) -> Response:
    """Switch the active session vault."""
    name = body.get("vault")
    if not name:
        return api_error(400, "vault required")
    if name not in {
        v["name"] for v in registered_vaults(state.fallback_vault, state.config.load())
    }:
        return api_error(404, "unknown vault")
    from telar.config import atomic_write_text

    session = pathlib.Path(state.session_path)
    atomic_write_text(session, json.dumps({"active_vault": name}))
    return JSONResponse({"ok": True, "active_vault": name})


@router.post("/api/vaults/pick")
def post_vaults_pick() -> Response:
    """Open the native macOS folder picker dialog."""
    if not shutil.which("osascript"):
        return api_error(501, "folder picker requires macOS")
    script = [
        "activate",
        'POSIX path of (choose folder with prompt "Choose a vault folder")',
    ]
    result = subprocess.run(
        ["osascript", *itertools.chain(*(("-e", s) for s in script))],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        if "-128" in result.stderr:
            return JSONResponse({"cancelled": True})
        return api_error(500, "folder picker failed")
    picked = result.stdout.strip().rstrip("/") or "/"
    return JSONResponse({"path": picked})


@router.post("/api/vaults/add")
def post_vaults_add(
    body: dict[str, Any] = Depends(read_json_body),
    state: AppState = Depends(get_state),
) -> Response:
    """Register an existing absolute folder as a vault."""
    raw_path = body.get("path")
    raw_name = body.get("name")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return api_error(400, "path required")
    target = pathlib.Path(raw_path.strip()).expanduser()
    if not target.is_absolute():
        return api_error(400, "path must be absolute")
    target = target.resolve()
    if not target.is_dir():
        return api_error(404, "folder not found")
    if target == pathlib.Path(target.anchor):
        return api_error(400, "filesystem root cannot be a vault")
    cfg = state.config.load()
    vaults = materialize_vaults(state.fallback_vault, cfg)
    if any(pathlib.Path(v["path"]).resolve() == target for v in vaults):
        return api_error(409, "vault already registered")
    names = {v["name"] for v in vaults}
    if raw_name is not None:
        if not isinstance(raw_name, str) or not raw_name.strip():
            return api_error(400, "invalid name")
        name = raw_name.strip()[:64]
        if name in names:
            return api_error(409, "vault name taken")
    else:
        name = target.name
        for counter in itertools.count(2):
            if name not in names:
                break
            name = f"{target.name} {counter}"
    vaults.append({"name": name, "path": str(target)})
    state.config.save(cfg)
    return JSONResponse(
        vaults_payload(state.fallback_vault, state.config, state.session_path, cfg)
    )


@router.post("/api/vaults/help")
def post_vaults_help(state: AppState = Depends(get_state)) -> Response:
    """Register the bundled ``help/`` folder as a vault if absent."""
    cfg = state.config.load()
    vaults = materialize_vaults(state.fallback_vault, cfg)
    help_path = HELP_DIR.resolve()
    if not help_path.is_dir():
        return api_error(404, "help folder not found")
    entry = next(
        (v for v in vaults if pathlib.Path(v["path"]).resolve() == help_path),
        None,
    )
    if entry is None:
        name = HELP_VAULT_NAME
        taken = {v["name"] for v in vaults}
        for counter in itertools.count(2):
            if name not in taken:
                break
            name = f"{HELP_VAULT_NAME} {counter}"
        entry = {"name": name, "path": str(help_path)}
        vaults.append(entry)
        state.config.save(cfg)
    payload = vaults_payload(
        state.fallback_vault, state.config, state.session_path, cfg
    )
    return JSONResponse({**payload, "help": entry["name"]})


@router.post("/api/vaults/remove")
def post_vaults_remove(
    body: dict[str, Any] = Depends(read_json_body),
    state: AppState = Depends(get_state),
    vault: pathlib.Path = Depends(get_vault),
) -> Response:
    """Unregister a vault without touching its files."""
    name = body.get("vault")
    cfg = state.config.load()
    vaults = materialize_vaults(state.fallback_vault, cfg)
    entry = next((v for v in vaults if v["name"] == name), None)
    if entry is None:
        return api_error(404, "unknown vault")
    if len(vaults) == 1:
        return api_error(409, "cannot remove the last vault")
    if pathlib.Path(entry["path"]).resolve() == vault.resolve():
        return api_error(409, "switch to another vault before removing it")
    vaults.remove(entry)
    if cfg.get("default_vault") == name:
        cfg["default_vault"] = vaults[0]["name"]
    state.config.save(cfg)
    return JSONResponse(
        vaults_payload(state.fallback_vault, state.config, state.session_path, cfg)
    )


@router.post("/api/vaults/default")
def post_vaults_default(
    body: dict[str, Any] = Depends(read_json_body),
    state: AppState = Depends(get_state),
) -> Response:
    """Set the default startup vault."""
    name = body.get("vault")
    cfg = state.config.load()
    vaults = materialize_vaults(state.fallback_vault, cfg)
    if name not in {v["name"] for v in vaults}:
        return api_error(404, "unknown vault")
    cfg["default_vault"] = name
    state.config.save(cfg)
    return JSONResponse(
        vaults_payload(state.fallback_vault, state.config, state.session_path, cfg)
    )
