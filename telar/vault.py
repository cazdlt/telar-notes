"""Vault filesystem operations, path security, tree/recent files, and periodic notes."""

from __future__ import annotations

import hashlib
import heapq
import itertools
import os
import pathlib
import re
from collections.abc import Iterator
from datetime import datetime
from typing import Any

import yaml

from telar.config import TelarConfig

RECENT_SORTS = ("modified", "created")
RECENT_LIMIT_MAX = 500
# Only files Telar Notes renders: notes, drawings (.excalidraw/.excalidraw.md), images.
RECENT_EXTENSIONS = (
    ".md",
    ".markdown",
    ".excalidraw",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
)


def resolve_vault_path(vault: pathlib.Path, rel: str) -> pathlib.Path:
    """Resolve a vault-relative path and reject any escape outside ``vault``."""
    vault_root = vault.resolve()
    target = vault / rel
    resolved = target.resolve()
    resolved.relative_to(vault_root)
    if resolved == vault_root:
        raise ValueError("path must point inside vault")
    return target


def unique_dest(dest: pathlib.Path) -> pathlib.Path:
    """Return dest, or dest with a numeric suffix if that name is already taken."""
    if not dest.exists() and not dest.is_symlink():
        return dest
    stem, suffix = dest.stem, dest.suffix
    if dest.name.lower().endswith(".excalidraw.md"):  # keep the compound extension
        stem, suffix = (
            dest.name[: -len(".excalidraw.md")],
            dest.name[-len(".excalidraw.md") :],
        )
    for counter in itertools.count(1):
        candidate = dest.with_name(f"{stem}-{counter}{suffix}")
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
    raise AssertionError("unreachable")


def attachment_dir(vault: pathlib.Path, note_rel: str, setting: str) -> pathlib.Path:
    """Resolve the attachment folder setting for a note.

    Same semantics as Obsidian's attachmentFolderPath: "" or "/" means the vault root,
    "." the note's own folder, "./sub" a subfolder beside the note, and a bare "sub" a
    vault-absolute folder.
    """
    setting = setting.strip() or "/"
    note_dir = vault / pathlib.PurePosixPath(note_rel).parent
    if setting in ("/", "."):
        return vault if setting == "/" else note_dir
    if setting.startswith("./"):
        return note_dir / setting[2:]
    return vault / setting.lstrip("/")


def revision(content: str) -> str:
    """Return an opaque content revision suitable for optimistic concurrency."""
    return hashlib.sha256(content.encode()).hexdigest()


def parse_frontmatter(content: str) -> dict[str, Any]:
    """Parse a YAML frontmatter mapping without mutating its source."""
    match = re.match(r"^---\s*\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)", content)
    if not match:
        return {}
    try:
        parsed = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def hidden_from_explorer(name: str) -> bool:
    """Dotfiles (including .trash) and the links index never appear as vault files."""
    return name.startswith(".") or name == "links-index.json"


def is_hidden(vault: pathlib.Path, path: pathlib.Path) -> bool:
    """Dot-prefixed folders (.trash, .obsidian, .venv, ...) are hidden from the tree."""
    return any(part.startswith(".") for part in path.relative_to(vault).parts)


def is_note(vault: pathlib.Path, path: pathlib.Path) -> bool:
    """Notes are visible Markdown files; Excalidraw drawings (.excalidraw.md) are not."""
    if (
        path.is_symlink()
        or path.name.endswith(".excalidraw.md")
        or is_hidden(vault, path)
    ):
        return False
    try:
        path.resolve().relative_to(vault.resolve())
    except ValueError:
        return False
    return True


def iter_notes(vault: pathlib.Path) -> Iterator[tuple[pathlib.Path, str]]:
    """Yield ``(path, rel_posix)`` for every visible Markdown note in ``vault``."""
    stack: list[tuple[pathlib.Path, str]] = [(vault, "")]
    while stack:
        current_dir, prefix = stack.pop()
        try:
            with os.scandir(current_dir) as it:
                for entry in it:
                    name = entry.name
                    if name.startswith("."):
                        continue
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append((pathlib.Path(entry.path), f"{prefix}{name}/"))
                        elif (
                            name.endswith(".md")
                            and not name.endswith(".excalidraw.md")
                            and entry.is_file(follow_symlinks=False)
                        ):
                            yield pathlib.Path(entry.path), f"{prefix}{name}"
                    except OSError:
                        continue
        except OSError:
            continue


def _scan_tree(dir_path: pathlib.Path, rel_prefix: str) -> list[dict[str, Any]]:
    """Recursively build file tree entries using ``os.scandir``."""
    scanned: list[tuple[bool, str, os.DirEntry[str], bool]] = []
    try:
        with os.scandir(dir_path) as it:
            for entry in it:
                if hidden_from_explorer(entry.name):
                    continue
                try:
                    if entry.is_symlink():
                        continue
                    is_dir = entry.is_dir(follow_symlinks=False)
                except OSError:
                    continue
                scanned.append((not is_dir, entry.name.lower(), entry, is_dir))
    except PermissionError:
        return []
    scanned.sort(key=lambda item: (item[0], item[1]))
    entries: list[dict[str, Any]] = []
    for _, _, entry, is_dir in scanned:
        rel = f"{rel_prefix}{entry.name}"
        if is_dir:
            entries.append(
                {
                    "path": rel,
                    "type": "dir",
                    "children": _scan_tree(pathlib.Path(entry.path), f"{rel}/"),
                }
            )
        else:
            entries.append({"path": rel, "type": "file", "name": entry.name})
    return entries


def build_tree(
    vault_path: pathlib.Path, rel_base: pathlib.Path | None = None
) -> list[dict[str, Any]]:
    """Recursively build file tree, skipping hidden files, symlinks, and links-index."""
    if rel_base is None or rel_base == vault_path:
        rel_prefix = ""
    else:
        rel_prefix = f"{vault_path.relative_to(rel_base)}/"
    return _scan_tree(vault_path, rel_prefix)


def recent_files(vault: pathlib.Path, sort: str, limit: int) -> list[dict[str, Any]]:
    """Return the ``limit`` openable files with the newest ``sort`` time.

    ``created`` is the birth time where the platform records one (macOS, Windows);
    elsewhere it falls back to the modification time. Timestamps are epoch ms.
    """
    entries: list[tuple[float, float, str, str]] = []
    for root, dirs, files in os.walk(vault):
        dirs[:] = [name for name in dirs if not hidden_from_explorer(name)]
        rel_root = pathlib.Path(root).relative_to(vault).as_posix()
        prefix = "" if rel_root == "." else f"{rel_root}/"
        for name in files:
            if hidden_from_explorer(name) or not name.lower().endswith(
                RECENT_EXTENSIONS
            ):
                continue
            try:
                stat = os.stat(os.path.join(root, name))
            except FileNotFoundError:
                continue  # deleted mid-walk or a dangling symlink
            birth = getattr(stat, "st_birthtime", stat.st_mtime)
            entries.append((stat.st_mtime, birth, prefix + name, name))
    column = RECENT_SORTS.index(sort)
    top = heapq.nlargest(limit, entries, key=lambda entry: entry[column])
    return [
        {
            "path": path,
            "name": name,
            "modified": int(modified * 1000),
            "created": int(created * 1000),
        }
        for modified, created, path, name in top
    ]


def format_periodic_date(dt: datetime, fmt: str) -> str:
    """Format the intentionally small Moment subset used by daily notes."""
    values = {
        "YYYY": f"{dt.year:04d}",
        "MM": f"{dt.month:02d}",
        "DD": f"{dt.day:02d}",
        "HH": f"{dt.hour:02d}",
        "mm": f"{dt.minute:02d}",
        "dddd": dt.strftime("%A"),
    }
    output, cursor = "", 0
    for match in re.finditer(r"\[([^]]*)\]|YYYY|MM|DD|HH|mm|dddd", fmt):
        output += fmt[cursor : match.start()]
        output += (
            match.group(1) if match.group(1) is not None else values[match.group(0)]
        )
        cursor = match.end()
    return output + fmt[cursor:]


def render_periodic_template(template: str, dt: datetime) -> str:
    """Expand ``{{title}}``, ``{{date}}``, and ``{{time}}`` placeholders."""
    title = format_periodic_date(dt, "YYYY-MM-DD")

    def replacement(match: re.Match[str]) -> str:
        name, fmt = match.group(1), match.group(2)
        if name == "title":
            return title
        return format_periodic_date(
            dt, fmt or ("HH:mm" if name == "time" else "YYYY-MM-DD")
        )

    return re.sub(r"\{\{(title|date|time)(?::([^}]+))?\}\}", replacement, template)


def active_vault(
    fallback_vault: pathlib.Path,
    config: TelarConfig,
    session_path: str,
    override: str | None = None,
) -> pathlib.Path:
    """Return the session vault, or the registered vault named by a per-window override."""
    if override:
        cfg = config.load()
        named = next((v for v in cfg.get("vaults", []) if v["name"] == override), None)
        if named:
            return pathlib.Path(named["path"])
    try:
        v = config.get_active_vault(session_path)
        if v and v.get("path"):
            return pathlib.Path(v["path"])
    except Exception:
        pass
    return fallback_vault


def registered_vaults(
    fallback_vault: pathlib.Path, cfg: dict[str, Any]
) -> list[dict[str, Any]]:
    """Return configured vaults, or the launch vault when none are configured."""
    vaults = cfg.get("vaults") or []
    return vaults or [{"name": fallback_vault.name, "path": str(fallback_vault)}]


def vaults_payload(
    fallback_vault: pathlib.Path,
    config: TelarConfig,
    session_path: str,
    cfg: dict[str, Any],
    override: str | None = None,
) -> dict[str, Any]:
    """Describe registered vaults with the active and default names."""
    vaults = registered_vaults(fallback_vault, cfg)
    active = active_vault(fallback_vault, config, session_path, override).resolve()
    names = [v["name"] for v in vaults]
    default = cfg.get("default_vault")
    return {
        "vaults": vaults,
        "active": next(
            (v["name"] for v in vaults if pathlib.Path(v["path"]).resolve() == active),
            None,
        ),
        "default": default if default in names else names[0],
    }


def materialize_vaults(
    fallback_vault: pathlib.Path, cfg: dict[str, Any]
) -> list[dict[str, Any]]:
    """Persist the implicit launch vault before the first registry change."""
    if not cfg.get("vaults"):
        cfg["vaults"] = registered_vaults(fallback_vault, cfg)
        cfg["default_vault"] = cfg["vaults"][0]["name"]
    return cfg["vaults"]
