"""Static asset routes serving only the production frontend build."""

from __future__ import annotations

from fastapi import APIRouter, Response

import telar.config as telar_config
from telar.deps import api_error

router = APIRouter()

_ASSET_TYPES = {
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml; charset=utf-8",
    ".png": "image/png",
    ".webp": "image/webp",
    ".woff2": "font/woff2",
    ".map": "application/json; charset=utf-8",
}


@router.get("/")
def get_index() -> Response:
    """Serve the built SPA entrypoint."""
    index_path = telar_config.DIST_DIR / "index.html"
    if not index_path.exists():
        return api_error(503, "frontend build not found")
    return Response(
        content=index_path.read_bytes(),
        media_type="text/html; charset=utf-8",
    )


@router.get("/excalidraw-editor.html")
def get_excalidraw_editor() -> Response:
    """Serve the built Excalidraw iframe entrypoint if present."""
    page_path = telar_config.DIST_DIR / "excalidraw-editor.html"
    if not page_path.is_file():
        return api_error(404, "not found")
    return Response(
        content=page_path.read_bytes(),
        media_type="text/html; charset=utf-8",
    )


@router.get("/assets/{asset_path:path}")
def get_asset(asset_path: str) -> Response:
    """Serve fingerprinted frontend assets with containment and extension checks."""
    dist_dir = telar_config.DIST_DIR
    target = (dist_dir / "assets" / asset_path).resolve()
    try:
        target.relative_to(dist_dir.resolve())
    except ValueError:
        return api_error(403, "forbidden")
    content_type = _ASSET_TYPES.get(target.suffix.lower())
    if content_type and target.is_file():
        return Response(content=target.read_bytes(), media_type=content_type)
    return api_error(404, "not found")
