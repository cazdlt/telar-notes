"""Vault note search by title, content, tags, or links."""

from __future__ import annotations

import pathlib
from typing import Any

from telar.links import load_links_index
from telar.vault import is_note, parse_frontmatter


def title_search(vault: pathlib.Path, query: str) -> list[dict[str, Any]]:
    """Search notes by filename stem or YAML frontmatter ``title``."""
    results: list[dict[str, Any]] = []
    ql = query.lower()
    for path in vault.rglob("*.md"):
        if not is_note(vault, path):
            continue
        rel = str(path.relative_to(vault))
        matched = ql in path.stem.lower()
        title = ""
        if not matched:
            try:
                title = str(
                    parse_frontmatter(path.read_text(errors="replace")).get("title", "")
                )
                matched = ql in title.lower()
            except OSError:
                pass
        if matched:
            results.append({"path": rel, "match": title or path.stem})
    return results


def content_search(vault: pathlib.Path, query: str) -> list[dict[str, Any]]:
    """Search Markdown content without optional runtime dependencies."""
    q = query.strip()
    if not q:
        return []
    results: list[dict[str, Any]] = []
    ql = q.lower()
    for path in vault.rglob("*.md"):
        if not is_note(vault, path):
            continue
        try:
            for line in path.read_text(errors="replace").splitlines():
                if ql in line.lower():
                    results.append(
                        {"path": str(path.relative_to(vault)), "snippet": line.strip()}
                    )
                    break  # one snippet per file is enough for the palette
        except OSError:
            pass
    return results


def search_notes(vault: pathlib.Path, query: str, mode: str) -> list[dict[str, Any]]:
    """Dispatch note search across ``title``, ``content``, ``all``, ``tags``, or ``links``."""
    if mode == "title":
        return title_search(vault, query)

    if mode == "content":
        return content_search(vault, query)

    if mode == "all":
        by_path: dict[str, dict[str, Any]] = {}
        for r in title_search(vault, query):
            by_path[r["path"]] = {"path": r["path"], "match": r.get("match")}
        for r in content_search(vault, query):
            if r["path"] in by_path:
                by_path[r["path"]].setdefault("snippet", r.get("snippet"))
            else:
                by_path[r["path"]] = {"path": r["path"], "snippet": r.get("snippet")}
        titled = [v for v in by_path.values() if v.get("match")]
        rest = [v for v in by_path.values() if not v.get("match")]
        return titled + rest

    if mode == "tags":
        results: list[dict[str, Any]] = []
        for path in vault.rglob("*.md"):
            if not is_note(vault, path):
                continue
            rel = str(path.relative_to(vault))
            try:
                fm = parse_frontmatter(path.read_text(errors="replace"))
                tags_raw = fm.get("tags", "")
                if isinstance(tags_raw, list):
                    tags = [str(tag).strip().lstrip("#") for tag in tags_raw]
                else:
                    tags = [
                        tag.strip().strip("[]").lstrip("#")
                        for tag in str(tags_raw).split(",")
                    ]
                if any(query.lstrip("#").lower() in t.lower() for t in tags):
                    results.append({"path": rel, "tags": tags})
            except OSError:
                pass
        return results

    if mode == "links":
        index = load_links_index(vault)
        norm = query.strip()
        if norm.startswith("[["):
            norm = norm[2:]
        if norm.endswith("]]"):
            norm = norm[:-2]
        norm = norm.strip()
        if not pathlib.PurePosixPath(norm).suffix:
            norm += ".md"
        entry = index.get(norm, {})
        results = []
        for p in entry.get("linked_from", []):
            results.append({"path": p, "direction": "linked_from"})
        for p in entry.get("links_to", []):
            results.append({"path": p, "direction": "links_to"})
        return results

    return []
