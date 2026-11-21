"""Vault note search by title, content, tags, or links."""

from __future__ import annotations

import pathlib
from typing import Any

from telar.links import load_links_index
from telar.vault import iter_notes, parse_frontmatter


def title_search(vault: pathlib.Path, query: str) -> list[dict[str, Any]]:
    """Search notes by filename stem or YAML frontmatter ``title``."""
    results: list[dict[str, Any]] = []
    ql = query.lower()
    for path, rel in iter_notes(vault):
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
    for path, rel in iter_notes(vault):
        try:
            for line in path.read_text(errors="replace").splitlines():
                if ql in line.lower():
                    results.append({"path": rel, "snippet": line.strip()})
                    break  # one snippet per file is enough for the palette
        except OSError:
            pass
    return results


def _all_search(vault: pathlib.Path, query: str) -> list[dict[str, Any]]:
    """Search both titles and content in a single vault walk and single read per note."""
    q = query.strip()
    ql_title = query.lower()
    ql_content = q.lower()
    titled: list[dict[str, Any]] = []
    rest: list[dict[str, Any]] = []
    for path, rel in iter_notes(vault):
        stem_matched = ql_title in path.stem.lower()
        text: str | None = None
        if not stem_matched or q:
            try:
                text = path.read_text(errors="replace")
            except OSError:
                text = None

        title_match: str | None = None
        if stem_matched:
            title_match = path.stem
        elif text is not None:
            title = str(parse_frontmatter(text).get("title", ""))
            if ql_title in title.lower():
                title_match = title or path.stem

        snippet: str | None = None
        if q and text is not None:
            for line in text.splitlines():
                if ql_content in line.lower():
                    snippet = line.strip()
                    break

        if title_match is not None:
            entry: dict[str, Any] = {"path": rel, "match": title_match}
            if snippet is not None:
                entry["snippet"] = snippet
            titled.append(entry)
        elif snippet is not None:
            rest.append({"path": rel, "snippet": snippet})
    return titled + rest


def search_notes(vault: pathlib.Path, query: str, mode: str) -> list[dict[str, Any]]:
    """Dispatch note search across ``title``, ``content``, ``all``, ``tags``, or ``links``."""
    if mode == "title":
        return title_search(vault, query)

    if mode == "content":
        return content_search(vault, query)

    if mode == "all":
        return _all_search(vault, query)

    if mode == "tags":
        results: list[dict[str, Any]] = []
        tag_query = query.lstrip("#").lower()
        for path, rel in iter_notes(vault):
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
                if any(tag_query in t.lower() for t in tags):
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
