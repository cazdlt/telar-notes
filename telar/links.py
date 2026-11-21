"""Wikilink resolution, link index maintenance, and BFS traversal."""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import unicodedata
from collections import deque
from typing import Any

from telar import config as telar_config
from telar.vault import is_note

# Inside Markdown tables the alias pipe is escaped (`[[note\|alias]]`); the backslash is not
# part of the target. Obsidian counts embeds (`![[note#^block]]`, `![[image.png]]`) as links.
_INDEX_LINK = re.compile(r"!?\[\[([^\]|#]+?)\\?(?:[|#][^\]]*)?\]\]")
_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")


def link_key(value: str) -> str:
    """Normalize a vault path for case-insensitive Unicode link matching."""
    return unicodedata.normalize("NFC", value).casefold()


def catalog_exact_path(catalog: dict[str, list[str]], path: str) -> str | None:
    """Return the real catalog path canonically equivalent to a full path."""
    normalized = pathlib.PurePosixPath(path).as_posix()
    depth = len(pathlib.PurePosixPath(normalized).parts)
    return next(
        (
            match
            for match in catalog.get(link_key(normalized), [])
            if len(pathlib.PurePosixPath(match).parts) == depth
        ),
        None,
    )


def strip_code(content: str) -> str:
    """Remove fenced blocks and inline code so [[links]] in examples don't count."""
    content = _FENCE_RE.sub("", content)
    content = _INLINE_CODE_RE.sub("", content)
    return content


def build_link_catalog(vault: pathlib.Path) -> dict[str, list[str]]:
    """Map every Obsidian-style shortest path to its matching notes."""
    catalog: dict[str, list[str]] = {}
    for note in vault.rglob("*.md"):
        if not is_note(vault, note):
            continue
        rel = note.relative_to(vault).as_posix()
        parts = pathlib.PurePosixPath(rel).parts
        for start in range(len(parts)):
            suffix = link_key(pathlib.PurePosixPath(*parts[start:]).as_posix())
            catalog.setdefault(suffix, []).append(rel)
    return catalog


def resolve_link(
    vault: pathlib.Path,
    source_rel: str,
    raw_link: str,
    catalog: dict[str, list[str]] | None = None,
) -> str:
    """Resolve [[raw_link]] to a vault-relative path. Keeps an explicit extension."""
    catalog = catalog or build_link_catalog(vault)
    target = raw_link.strip()
    if not pathlib.PurePosixPath(target).suffix:
        target = target + ".md"
    source_dir = pathlib.Path(source_rel).parent
    candidate = vault / source_dir / target
    if candidate.exists():
        relative = (source_dir / target).as_posix()
        return catalog_exact_path(catalog, relative) or relative
    candidate = vault / target
    if candidate.exists():
        relative = pathlib.Path(target).as_posix()
        return catalog_exact_path(catalog, relative) or relative

    target_key = link_key(pathlib.PurePosixPath(target).as_posix())
    matches = catalog.get(target_key, [])
    if matches:
        source_parts = pathlib.PurePosixPath(source_rel).parent.parts

        def proximity(rel: str) -> tuple[int, int, str]:
            candidate_parts = pathlib.PurePosixPath(rel).parent.parts
            common = 0
            for source_part, candidate_part in zip(source_parts, candidate_parts):
                if link_key(source_part) != link_key(candidate_part):
                    break
                common += 1
            distance = len(source_parts) + len(candidate_parts) - (2 * common)
            return distance, len(candidate_parts), link_key(rel)

        return min(matches, key=proximity)
    return target


def extract_targets(
    vault: pathlib.Path,
    rel_path: str,
    content: str,
    catalog: dict[str, list[str]] | None = None,
) -> list[str]:
    """Forward-link targets for one note, embeds included: strip code, resolve."""
    catalog = catalog or build_link_catalog(vault)
    targets: list[str] = []
    for match in _INDEX_LINK.finditer(strip_code(content)):
        target = resolve_link(vault, rel_path, match.group(1), catalog)
        if target != rel_path and target not in targets:
            targets.append(target)
    return targets


def build_links_index(vault: pathlib.Path) -> dict[str, dict[str, list[str]]]:
    """Build the full forward and backward link index for a vault."""
    index: dict[str, dict[str, list[str]]] = {}
    md_files = [f for f in vault.rglob("*.md") if is_note(vault, f)]
    catalog = build_link_catalog(vault)
    for f in md_files:
        rel = str(f.relative_to(vault))
        if rel not in index:
            index[rel] = {"links_to": [], "linked_from": []}
    for f in md_files:
        rel = str(f.relative_to(vault))
        content = f.read_text(errors="replace")
        for target in extract_targets(vault, rel, content, catalog):
            if target not in index[rel]["links_to"]:
                index[rel]["links_to"].append(target)
            if target not in index:
                index[target] = {"links_to": [], "linked_from": []}
            if rel not in index[target]["linked_from"]:
                index[target]["linked_from"].append(rel)
    return index


def links_index_path(vault: pathlib.Path) -> pathlib.Path:
    """Return the per-vault link index path inside ``CONFIG_DIR/indexes/``."""
    digest = hashlib.sha256(str(vault.resolve()).encode("utf-8")).hexdigest()[:16]
    return telar_config.CONFIG_DIR / "indexes" / f"{digest}.json"


def write_links_index(vault: pathlib.Path, index: dict[str, Any]) -> None:
    """Persist the generated link index."""
    telar_config.atomic_write_text(links_index_path(vault), json.dumps(index, indent=2))


def load_links_index(vault: pathlib.Path) -> dict[str, dict[str, list[str]]]:
    """Load a complete index, rebuilding missing, corrupt, or partial caches."""
    idx_path = links_index_path(vault)
    actual_notes = {
        note.relative_to(vault).as_posix()
        for note in vault.rglob("*.md")
        if is_note(vault, note)
    }
    try:
        index = json.loads(idx_path.read_text())
        if not isinstance(index, dict):
            raise ValueError("incomplete links index")
        actual_link_keys = set()
        for path in actual_notes:
            parts = pathlib.PurePosixPath(path).parts
            actual_link_keys.update(
                link_key(pathlib.PurePosixPath(*parts[start:]).as_posix())
                for start in range(len(parts))
            )
        has_unicode_alias = any(
            path not in actual_notes and link_key(path) in actual_link_keys
            for path in index
        )
        has_hidden = any(
            part.startswith(".")
            for path in index
            for part in pathlib.PurePosixPath(path).parts
        )
        if not actual_notes.issubset(index) or has_unicode_alias or has_hidden:
            raise ValueError("incomplete links index")
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        index = build_links_index(vault)
        write_links_index(vault, index)
    return index


def update_links_index(vault: pathlib.Path, rel_path: str, content: str) -> None:
    """Incrementally update forward and backward links for one note."""
    if rel_path.endswith(".excalidraw.md"):
        return  # drawings are not notes; keep them out of the links-index
    index = load_links_index(vault)
    if rel_path not in index:
        index[rel_path] = {"links_to": [], "linked_from": []}
    old_links = index[rel_path]["links_to"]
    for old in old_links:
        if old in index and rel_path in index[old]["linked_from"]:
            index[old]["linked_from"].remove(rel_path)
    index[rel_path]["links_to"] = []
    for target in extract_targets(vault, rel_path, content):
        if target not in index[rel_path]["links_to"]:
            index[rel_path]["links_to"].append(target)
        if target not in index:
            index[target] = {"links_to": [], "linked_from": []}
        if rel_path not in index[target]["linked_from"]:
            index[target]["linked_from"].append(rel_path)
    write_links_index(vault, index)


def bfs_links(index: dict[str, Any], start: str, hops: int) -> list[str]:
    """Return notes reachable within ``hops`` steps in the undirected link graph."""
    visited: set[str] = set()
    queue = deque([(start, 0)])
    while queue:
        node, depth = queue.popleft()
        if node in visited or depth >= hops:
            if node != start:
                visited.add(node)
            continue
        visited.add(node)
        entry = index.get(node, {})
        neighbors = entry.get("links_to", []) + entry.get("linked_from", [])
        for neighbor in neighbors:
            if neighbor not in visited:
                queue.append((neighbor, depth + 1))
    visited.discard(start)
    return list(visited)
