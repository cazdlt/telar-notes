#!/usr/bin/env python3
"""Backward-compatible CLI entrypoint and re-exports for Telar Notes."""

from telar.__main__ import main
from telar.app import create_app
from telar.config import CONFIG_DIR, DIST_DIR, HELP_DIR, WEB_DIR, TelarConfig
from telar.links import build_links_index as _build_links_index
from telar.search import content_search as _content_search
from telar.vault import build_tree as _build_tree
from telar.vault import recent_files as _recent_files

__all__ = [
    "CONFIG_DIR",
    "DIST_DIR",
    "HELP_DIR",
    "TelarConfig",
    "WEB_DIR",
    "_build_links_index",
    "_build_tree",
    "_content_search",
    "_recent_files",
    "create_app",
    "main",
]

if __name__ == "__main__":
    main()
