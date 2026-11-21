"""Obsidian Tasks-compatible parsing, incremental index, date edits, and block IDs."""

from __future__ import annotations

import calendar
import difflib
import os
import pathlib
import re
import threading
import unicodedata
from datetime import datetime, timedelta
from typing import Any

from telar.config import atomic_write_text
from telar.links import update_links_index
from telar.vault import resolve_vault_path, revision

# Tasks' core statuses plus the Minimal/ITS theme collection; name and type follow Tasks.
TASK_STATUSES: dict[str, tuple[str, str]] = {
    " ": ("Todo", "TODO"),
    "x": ("Done", "DONE"),
    "/": ("In Progress", "IN_PROGRESS"),
    "-": ("Cancelled", "CANCELLED"),
    ">": ("delegated", "TODO"),
    "<": ("deferred", "TODO"),
    "?": ("question", "IN_PROGRESS"),
    "!": ("important", "TODO"),
    "*": ("star", "TODO"),
    '"': ("quote", "TODO"),
    "l": ("location", "TODO"),
    "b": ("bookmark", "TODO"),
    "i": ("information", "TODO"),
    "S": ("savings", "TODO"),
    "I": ("idea", "TODO"),
    "p": ("pros", "TODO"),
    "c": ("cons", "TODO"),
    "f": ("fire", "TODO"),
    "k": ("key", "TODO"),
    "w": ("win", "TODO"),
    "u": ("up", "TODO"),
    "d": ("down", "TODO"),
}
STATUS_CLASS = (
    "[" + "".join(re.escape(symbol) for symbol in [*TASK_STATUSES, "X"]) + "]"
)
TASK_LINE_RE = re.compile(
    rf"^(?P<indent>\s*)[-*+]\s+\[(?P<status>{STATUS_CLASS})\]\s*(?P<body>.*)$"
)
_TASK_DATE = re.compile(r"(?P<emoji>📅|⏳|🛫|✅|➕|❌)\s*(?P<date>\d{4}-\d{2}-\d{2})")
_TASK_PRIORITY = re.compile(r"[⏫🔼🔺⏬🔽]")
_TASK_RECURRENCE = re.compile(
    r"\s🔁\s*(?P<rule>.*?)(?=\s(?:🏁\s*delete|🆔|⛔|📅|⏳|🛫|✅|➕|❌|[⏫🔼🔺⏬🔽])|$)"
)
_TASK_ID = re.compile(r"\s🆔\s*\S+")
# Obsidian block ID; Tasks requires it to be the last token on the line.
_TASK_BLOCK_ID = re.compile(r" \^(?P<id>[A-Za-z0-9-]+)$")
_TASK_DEPENDENCY = re.compile(r"\s⛔\s*\S+(?:\s*,\s*\S+)*")

_SLUG_STOPWORDS = frozenset(
    "a al con de del el en la las lo los o para por que se su un una y"
    " an and for in of on or the to with".split()
)

_PRIORITY_NAME_TO_EMOJI: dict[str, str] = {
    "highest": "🔺",
    "high": "⏫",
    "medium": "🔼",
    "low": "🔽",
    "lowest": "⏬",
}
_VALID_PRIORITY_EMOJIS = frozenset(_PRIORITY_NAME_TO_EMOJI.values())

_DATE_EMOJIS: tuple[tuple[str, str], ...] = (
    ("due", "📅"),
    ("scheduled", "⏳"),
    ("start", "🛫"),
    ("done", "✅"),
    ("created", "➕"),
    ("cancelled", "❌"),
)
_DATE_KEYS = frozenset(key for key, _ in _DATE_EMOJIS)
_BLOCK_ID_RE = re.compile(r"^[A-Za-z0-9-]+$")
_VALID_ANCHORS = frozenset(
    {"end_of_section", "after_heading", "before_heading", "end_of_file"}
)
_HEADING_LINE_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
_FENCE_OPEN_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")

_TASK_INDEX_CACHE: dict[
    str, dict[str, tuple[tuple[int, int], list[dict[str, Any]]]]
] = {}


class TaskLocationError(ValueError):
    """A task location that cannot be resolved; carries the HTTP status."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def normalize_status_symbol(symbol: str) -> str:
    """Normalize only the case-insensitive completed marker."""
    return "x" if symbol in {"x", "X"} else symbol


def task_description(body: str) -> str:
    """Remove Tasks metadata from the user-authored description."""
    description = _TASK_DATE.sub("", body)
    description = _TASK_PRIORITY.sub("", description)
    description = _TASK_RECURRENCE.sub("", description)
    description = _TASK_ID.sub("", description)
    description = _TASK_DEPENDENCY.sub("", description)
    description = re.sub(r"\s🏁\s*delete\b", "", description)
    return re.sub(r"\s{2,}", " ", description).strip()


def task_date_map(body: str) -> dict[str, str]:
    """Extract Tasks emoji dates into a keyed mapping."""
    values: dict[str, str] = {}
    emoji_names = {
        "📅": "due",
        "⏳": "scheduled",
        "🛫": "start",
        "✅": "done",
        "➕": "created",
        "❌": "cancelled",
    }
    for match in _TASK_DATE.finditer(body):
        values[emoji_names[match.group("emoji")]] = match.group("date")
    return values


def parse_tasks(
    content: str, path: str, stat: os.stat_result | None = None
) -> list[dict[str, Any]]:
    """Parse Tasks-compatible list items without rewriting untouched Markdown."""
    records: list[dict[str, Any]] = []
    parents: list[tuple[int, int]] = []
    heading = ""
    for number, line in enumerate(content.splitlines(), start=1):
        heading_match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
        if heading_match:
            heading = heading_match.group(1)
        match = TASK_LINE_RE.match(line)
        if not match:
            continue
        indent = len(match.group("indent").expandtabs(2))
        while parents and parents[-1][0] >= indent:
            parents.pop()
        body = match.group("body")
        block_id = _TASK_BLOCK_ID.search(body)
        if block_id:
            body = body[: block_id.start()]
        symbol = normalize_status_symbol(match.group("status"))
        recurrence = _TASK_RECURRENCE.search(body)
        dates = task_date_map(body)
        priority = _TASK_PRIORITY.search(body)
        task = {
            "location": {"path": path, "line": number, "expected": line},
            "status": {
                "symbol": symbol,
                "name": TASK_STATUSES[symbol][0],
                "type": TASK_STATUSES[symbol][1],
            },
            "description": task_description(body),
            "heading": heading,
            "parent": parents[-1][1] if parents else None,
            "indent": indent,
            "dates": dates,
            "priority": priority.group(0) if priority else None,
            "tags": re.findall(r"(?<!\w)#([\w/-]+)", body),
            "recurrence": recurrence.group("rule").strip() if recurrence else None,
            "delete_when_done": "🏁 delete" in body,
            "block_id": block_id.group("id") if block_id else None,
            "mtime_ns": stat.st_mtime_ns if stat else None,
            "size": stat.st_size if stat else None,
        }
        records.append(task)
        parents.append((indent, number))
    return records


_TASK_CACHE_LOCK = threading.Lock()


def task_index(vault: pathlib.Path) -> list[dict[str, Any]]:
    """Incrementally reuse parsed task records for files whose stat is unchanged."""
    vault_root = vault.resolve()
    vault_key = str(vault_root)
    with _TASK_CACHE_LOCK:
        previous = dict(_TASK_INDEX_CACHE.get(vault_key, {}))
    current: dict[str, tuple[tuple[int, int], list[dict[str, Any]]]] = {}
    results: list[dict[str, Any]] = []
    root = str(vault)
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [
            name
            for name in dirnames
            if not name.startswith(".")
            and not os.path.islink(os.path.join(dirpath, name))
        ]
        prefix = os.path.relpath(dirpath, root)
        prefix = "" if prefix == "." else prefix.replace(os.sep, "/") + "/"
        for name in filenames:
            if name.startswith(".") or not name.endswith(".md"):
                continue
            path = os.path.join(dirpath, name)
            if os.path.islink(path):
                continue
            try:
                pathlib.Path(path).resolve().relative_to(vault_root)
            except ValueError:
                continue
            rel = prefix + name
            stat = os.stat(path)
            marker = (stat.st_mtime_ns, stat.st_size)
            entry = previous.get(rel)
            if entry and entry[0] == marker:
                records = entry[1]
            else:
                text = pathlib.Path(path).read_text(errors="replace")
                records = parse_tasks(text, rel, stat)
            current[rel] = (marker, records)
            results.extend(records)
    with _TASK_CACHE_LOCK:
        _TASK_INDEX_CACHE[vault_key] = current
    return results


def invalidate_tasks(vault: pathlib.Path, rel: str) -> None:
    """Drop cached task records for one modified note."""
    with _TASK_CACHE_LOCK:
        entry = _TASK_INDEX_CACHE.get(str(vault.resolve()))
        if entry:
            entry.pop(rel, None)


def parse_iso_date(value: str) -> datetime:
    """Parse a ``YYYY-MM-DD`` ISO date string."""
    return datetime.strptime(value, "%Y-%m-%d")


def next_recurrence(rule: str, date_str: str) -> str | None:
    """Return next used recurrence date; unsupported rules remain untouched."""
    lower = rule.lower().strip()
    current = parse_iso_date(date_str)
    if lower in {"every day", "daily", "cada día", "cada dia"}:
        return (current + timedelta(days=1)).strftime("%Y-%m-%d")
    if lower in {
        "every weekday",
        "weekdays",
        "cada día laborable",
        "cada dia laborable",
    }:
        next_day = current + timedelta(days=1)
        while next_day.weekday() >= 5:
            next_day += timedelta(days=1)
        return next_day.strftime("%Y-%m-%d")
    weekdays = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    for name, weekday in weekdays.items():
        if name in lower and ("week" in lower or "cada" in lower):
            days = (weekday - current.weekday()) % 7 or 7
            return (current + timedelta(days=days)).strftime("%Y-%m-%d")
    if lower in {"every month", "monthly", "cada mes"}:
        month = current.month % 12 + 1
        year = current.year + (current.month == 12)
        day = min(current.day, calendar.monthrange(year, month)[1])
        return current.replace(year=year, month=month, day=day).strftime("%Y-%m-%d")
    return None


def normalize_priority(value: Any) -> str | None:
    """Map an Obsidian priority emoji or English name to its canonical emoji."""
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError("invalid priority")
    stripped = value.strip()
    if not stripped:
        return None
    if stripped in _VALID_PRIORITY_EMOJIS:
        return stripped
    mapped = _PRIORITY_NAME_TO_EMOJI.get(stripped.lower())
    if mapped is not None:
        return mapped
    raise ValueError("invalid priority")


def _fold_heading(text: str) -> str:
    """Normalize a heading for case- and accent-insensitive NFC matching."""
    nfc = unicodedata.normalize("NFC", text.strip())
    nfkd = unicodedata.normalize("NFKD", nfc)
    stripped = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", stripped).casefold()


def _frontmatter_end(lines: list[str]) -> int:
    """Return the first line index after YAML frontmatter, or 0 if none."""
    if not lines or lines[0].rstrip("\r\n") != "---":
        return 0
    for idx in range(1, len(lines)):
        if lines[idx].rstrip("\r\n") in {"---", "..."}:
            return idx + 1
    return 0


def _find_heading_insert_index(
    lines: list[str], heading: str | None, anchor: str
) -> int:
    """Locate the 0-based line index where a task should be inserted."""
    if anchor not in _VALID_ANCHORS:
        raise ValueError("invalid anchor")
    if anchor == "end_of_file":
        return len(lines)
    if not isinstance(heading, str) or not heading.strip():
        raise ValueError("heading required for anchor")

    target_parts = [_fold_heading(part) for part in heading.split(">")]
    if any(not part for part in target_parts):
        raise ValueError("invalid heading")

    start = _frontmatter_end(lines)
    fence_char: str | None = None
    fence_len = 0
    stack: list[tuple[int, str]] = []
    matched_idx: int | None = None
    matched_level = 0
    section_end = len(lines)

    for idx in range(start, len(lines)):
        raw = lines[idx].rstrip("\r\n")
        if fence_char is not None:
            if re.match(rf"^\s{{0,3}}{re.escape(fence_char)}{{{fence_len},}}\s*$", raw):
                fence_char = None
                fence_len = 0
            continue
        fence_match = _FENCE_OPEN_RE.match(raw)
        if fence_match:
            token = fence_match.group(1)
            fence_char = token[0]
            fence_len = len(token)
            continue

        heading_match = _HEADING_LINE_RE.match(raw)
        if not heading_match:
            continue
        level = len(heading_match.group(1))
        title = _fold_heading(heading_match.group(2))

        if matched_idx is not None:
            if level <= matched_level:
                section_end = idx
                break
            continue

        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))

        if len(stack) >= len(target_parts):
            tail = [item[1] for item in stack[-len(target_parts) :]]
            if tail == target_parts:
                matched_idx = idx
                matched_level = level

    if matched_idx is None:
        raise TaskLocationError(404, f"heading not found: {heading}")

    if anchor == "before_heading":
        return matched_idx
    if anchor == "after_heading":
        return matched_idx + 1
    pos = section_end - 1
    while pos > matched_idx and lines[pos].strip() == "":
        pos -= 1
    return pos + 1


def _block_id_taken(content: str, block_id: str) -> bool:
    """Return whether ``^block_id`` already exists anywhere in ``content``."""
    return bool(re.search(rf"(?:^|\s)\^{re.escape(block_id)}(?=\s|$)", content, re.M))


def _unified_diff(rel: str, old_content: str, new_content: str) -> str:
    """Compute a unified diff between ``old_content`` and ``new_content``."""
    return "".join(
        difflib.unified_diff(
            old_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
        )
    )


def _replace_task_description(line: str, new_description: str) -> str:
    """Replace a task line's description while preserving metadata tokens."""
    if not isinstance(new_description, str) or not new_description.strip():
        raise ValueError("description must be a non-empty string")
    block_id = _TASK_BLOCK_ID.search(line)
    suffix = block_id.group(0) if block_id else ""
    head = line[: block_id.start()] if block_id else line
    match = TASK_LINE_RE.match(head)
    if not match:
        raise ValueError("invalid task line")
    indent, status, body = (
        match.group("indent"),
        match.group("status"),
        match.group("body"),
    )

    meta_matches: list[re.Match[str]] = []
    for pattern in (
        _TASK_RECURRENCE,
        _TASK_ID,
        _TASK_DEPENDENCY,
        re.compile(r"\s🏁\s*delete\b"),
        _TASK_PRIORITY,
        _TASK_DATE,
    ):
        meta_matches.extend(pattern.finditer(body))
    meta_matches.sort(key=lambda m: m.start())

    tokens: list[str] = []
    last_end = -1
    for m in meta_matches:
        if m.start() >= last_end:
            tokens.append(m.group(0).strip())
            last_end = m.end()

    meta_part = "".join(f" {tok}" for tok in tokens)
    return f"{indent}- [{status}] {new_description.strip()}{meta_part}{suffix}"


def replace_task_dates(
    line: str, patch: dict[str, Any], settings: dict[str, Any]
) -> str:
    """Apply editable status/date/priority fields while preserving all other bytes."""
    block_id = _TASK_BLOCK_ID.search(line)
    suffix = block_id.group(0) if block_id else ""
    if block_id:
        line = line[: block_id.start()]
    status = patch.get("status")
    if status is not None:
        if status not in TASK_STATUSES:
            raise ValueError("invalid task status")
        line = TASK_LINE_RE.sub(
            lambda match: f"{match.group('indent')}- [{status}] {match.group('body')}",
            line,
            count=1,
        )
    for key, emoji in (
        ("due", "📅"),
        ("scheduled", "⏳"),
        ("start", "🛫"),
        ("done", "✅"),
        ("created", "➕"),
        ("cancelled", "❌"),
    ):
        if key not in patch:
            continue
        value = patch[key]
        line = re.sub(rf"\s*{emoji}\s*\d{{4}}-\d{{2}}-\d{{2}}", "", line)
        if value:
            parse_iso_date(value)
            line += f" {emoji} {value}"
    if "priority" in patch:
        value = normalize_priority(patch["priority"])
        line = re.sub(r"\s*[⏫🔼🔺⏬🔽]", "", line).rstrip()
        if value:
            line += f" {value}"
    today = datetime.now().strftime("%Y-%m-%d")
    new_status = patch.get("status")
    if (
        new_status == "x"
        and settings.get("set_done_date")
        and "done" not in patch
        and "✅" not in line
    ):
        line += f" ✅ {today}"
    if (
        new_status == "-"
        and settings.get("set_cancelled_date")
        and "cancelled" not in patch
        and "❌" not in line
    ):
        line += f" ❌ {today}"
    if "status" in patch and new_status is not None and new_status not in ("x", "-"):
        line = re.sub(r"\s*(✅|❌)\s*\d{4}-\d{2}-\d{2}", "", line)
    return line.rstrip() + suffix


def block_id_slug(description: str, taken: set[str]) -> str:
    """Derive a short readable block ID from a task description, unique in ``taken``."""
    text = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", description)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)|https?://\S+", r"\1", text)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    words = [
        w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _SLUG_STOPWORDS
    ]
    base = "-".join(words[:4]) or "task"
    slug, counter = base, 2
    while slug in taken:
        slug, counter = f"{base}-{counter}", counter + 1
    return slug


def locate_task_line(
    vault: pathlib.Path, location: object
) -> tuple[str, pathlib.Path, list[str], int]:
    """Validate a ``TaskLocation`` and return its file lines if the task is resolved."""
    if not isinstance(location, dict):
        raise TaskLocationError(400, "location and patch required")
    rel = location.get("path")
    if not isinstance(rel, str) or not rel.strip():
        raise TaskLocationError(400, "invalid task location")
    try:
        target = resolve_vault_path(vault, rel)
    except ValueError:
        raise TaskLocationError(403, "forbidden") from None
    if not target.is_file():
        raise TaskLocationError(404, "not found")
    lines = target.read_text().splitlines(keepends=True)

    if "expected" in location:
        line_number, expected = location.get("line"), location.get("expected")
        if not isinstance(line_number, int) or not isinstance(expected, str):
            raise TaskLocationError(400, "invalid task location")
        if (
            line_number < 1
            or line_number > len(lines)
            or lines[line_number - 1].rstrip("\r\n") != expected
            or not TASK_LINE_RE.match(expected)
        ):
            raise TaskLocationError(409, "task changed on disk")
        return rel, target, lines, line_number

    if "block_id" in location and location.get("block_id") is not None:
        block_id = location.get("block_id")
        if not isinstance(block_id, str) or not block_id.strip():
            raise TaskLocationError(400, "invalid task location")
        task = next(
            (t for t in parse_tasks("".join(lines), rel) if t["block_id"] == block_id),
            None,
        )
        if task is None:
            raise TaskLocationError(404, "task not found")
        return rel, target, lines, task["location"]["line"]

    if "match" in location and location.get("match") is not None:
        needle = location.get("match")
        if not isinstance(needle, str) or not needle.strip():
            raise TaskLocationError(400, "invalid task location")
        needle_lower = needle.lower()
        matches = [
            idx
            for idx, raw in enumerate(lines, start=1)
            if TASK_LINE_RE.match(raw.rstrip("\r\n"))
            and needle_lower in raw.rstrip("\r\n").lower()
        ]
        if not matches:
            raise TaskLocationError(404, "task not found")
        if len(matches) > 1:
            raise TaskLocationError(409, "multiple tasks match")
        return rel, target, lines, matches[0]

    if "line" in location:
        line_number = location.get("line")
        if not isinstance(line_number, int):
            raise TaskLocationError(400, "invalid task location")
        if (
            line_number < 1
            or line_number > len(lines)
            or not TASK_LINE_RE.match(lines[line_number - 1].rstrip("\r\n"))
        ):
            raise TaskLocationError(409, "task changed on disk")
        return rel, target, lines, line_number

    raise TaskLocationError(400, "invalid task location")


def _insert_lines(lines: list[str], idx: int, new_lines: list[str]) -> list[str]:
    """Insert ``new_lines`` at ``idx``, ensuring a trailing newline on the prior line."""
    result = list(lines)
    if idx > 0 and not result[idx - 1].endswith("\n"):
        result[idx - 1] += "\n"
    return result[:idx] + new_lines + result[idx:]


def add_task_line(vault: pathlib.Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Format and insert a new Obsidian Tasks line into an existing note."""
    rel = payload.get("path")
    if not isinstance(rel, str) or not rel.strip():
        raise TaskLocationError(400, "path required")
    try:
        target = resolve_vault_path(vault, rel)
    except ValueError:
        raise TaskLocationError(403, "forbidden") from None
    if not target.is_file():
        raise TaskLocationError(404, "not found")
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise TaskLocationError(400, "file is not text") from None

    description = payload.get("description")
    if not isinstance(description, str) or not description.strip():
        raise ValueError("description required")
    if "\n" in description or "\r" in description:
        raise ValueError("description must be single-line")

    status = payload.get("status", " ")
    if status is None:
        status = " "
    if not isinstance(status, str) or status not in TASK_STATUSES:
        raise ValueError("invalid task status")

    priority = normalize_priority(payload.get("priority"))

    dates_raw = payload.get("dates")
    date_parts: list[str] = []
    if dates_raw is not None:
        if not isinstance(dates_raw, dict):
            raise ValueError("dates must be an object")
        unknown_keys = set(dates_raw) - _DATE_KEYS
        if unknown_keys:
            raise ValueError(f"invalid date key: {sorted(unknown_keys)[0]}")
        for key, emoji in _DATE_EMOJIS:
            val = dates_raw.get(key)
            if val is not None and val != "":
                if not isinstance(val, str):
                    raise ValueError(f"invalid date for {key}")
                parse_iso_date(val)
                date_parts.append(f" {emoji} {val}")

    tags_raw = payload.get("tags")
    tag_parts: list[str] = []
    if tags_raw is not None:
        if not isinstance(tags_raw, list):
            raise ValueError("tags must be a list")
        for tag in tags_raw:
            if not isinstance(tag, str) or not tag.strip():
                raise ValueError("invalid tag")
            cleaned = tag.strip()
            if not cleaned.startswith("#"):
                cleaned = f"#{cleaned}"
            tag_parts.append(f" {cleaned}")

    block_id = payload.get("block_id")
    if block_id == "":
        block_id = None
    if block_id is not None:
        if not isinstance(block_id, str) or not _BLOCK_ID_RE.fullmatch(block_id):
            raise ValueError("invalid block_id")
        if _block_id_taken(content, block_id):
            raise TaskLocationError(409, f"block_id already exists: {block_id}")

    children_raw = payload.get("children")
    child_lines: list[str] = []
    if children_raw is not None:
        if not isinstance(children_raw, list):
            raise ValueError("children must be a list")
        for child in children_raw:
            if not isinstance(child, str):
                raise ValueError("invalid child line")
            child_lines.append(f"  {child.rstrip()}\n")

    heading = payload.get("heading")
    anchor = payload.get("anchor")
    if anchor is None:
        anchor = "end_of_section" if heading is not None else "end_of_file"

    lines = content.splitlines(keepends=True)
    insert_idx = _find_heading_insert_index(lines, heading, anchor)

    task_line = (
        f"- [{status}] {description.strip()}"
        + "".join(tag_parts)
        + (f" {priority}" if priority else "")
        + "".join(date_parts)
        + (f" ^{block_id}" if block_id else "")
    )
    new_lines = _insert_lines(lines, insert_idx, [task_line + "\n", *child_lines])
    new_content = "".join(new_lines)
    diff = _unified_diff(rel, content, new_content)

    inserted_line_number = insert_idx + 1
    task_record = next(
        t
        for t in parse_tasks(new_content, rel)
        if t["location"]["line"] == inserted_line_number
    )
    embed = f"![[{pathlib.PurePosixPath(rel).stem}#^{block_id}]]" if block_id else None
    dry_run = bool(payload.get("dry_run", False))
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "task": task_record,
            "embed": embed,
            "revision": revision(content),
            "diff": diff,
        }

    atomic_write_text(target, new_content)
    update_links_index(vault, rel, new_content)
    invalidate_tasks(vault, rel)
    return {
        "ok": True,
        "task": task_record,
        "embed": embed,
        "revision": revision(new_content),
        "diff": diff,
    }


def update_task_line(
    vault: pathlib.Path,
    location: object,
    patch: dict[str, Any],
    settings: dict[str, Any],
    dry_run: bool = False,
) -> dict[str, Any]:
    """Apply a task patch atomically, handling recurrence and index updates."""
    rel, target, lines, line_number = locate_task_line(vault, location)
    old_content = "".join(lines)
    old = lines[line_number - 1].rstrip("\r\n")
    updated = old
    if "description" in patch and patch["description"] is not None:
        updated = _replace_task_description(updated, patch["description"])
    updated = replace_task_dates(updated, patch, settings)

    if "block_id" in patch and patch["block_id"] is not None:
        new_block_id = patch["block_id"]
        if not isinstance(new_block_id, str) or not _BLOCK_ID_RE.fullmatch(
            new_block_id
        ):
            raise ValueError("invalid block_id")
        if not _TASK_BLOCK_ID.search(updated):
            if _block_id_taken(old_content, new_block_id):
                raise TaskLocationError(409, f"block_id already exists: {new_block_id}")
            updated = f"{updated.rstrip()} ^{new_block_id}"

    old_task = TASK_LINE_RE.match(old)
    original_status = (
        normalize_status_symbol(old_task.group("status")) if old_task else " "
    )
    line_ending = "\n" if lines[line_number - 1].endswith("\n") else ""

    recurrence = _TASK_RECURRENCE.search(old) if patch.get("status") == "x" else None
    next_date = None
    if recurrence:
        base = (
            task_date_map(old).get("scheduled")
            or task_date_map(old).get("due")
            or datetime.now().date().isoformat()
        )
        next_date = next_recurrence(recurrence.group("rule").strip(), base)

    deleted_original = False
    if next_date:
        next_line = re.sub(rf"\[{STATUS_CLASS}\]", "[ ]", old, count=1)
        next_line = re.sub(r"\s*✅\s*\d{4}-\d{2}-\d{2}", "", next_line)
        next_line = _TASK_BLOCK_ID.sub("", next_line)
        if "📅" in next_line:
            next_line = re.sub(r"📅\s*\d{4}-\d{2}-\d{2}", f"📅 {next_date}", next_line)
        else:
            next_line += f" 📅 {next_date}"
        lines.insert(line_number, next_line + "\n")
        if "🏁 delete" in old:
            lines.pop(line_number - 1)
            deleted_original = True
        else:
            lines[line_number - 1] = updated + line_ending
    else:
        lines[line_number - 1] = updated + line_ending

    if "append_children" in patch and patch["append_children"] is not None:
        children_raw = patch["append_children"]
        if not isinstance(children_raw, list) or any(
            not isinstance(c, str) for c in children_raw
        ):
            raise ValueError("append_children must be a list of strings")
        if children_raw and not deleted_original:
            task_indent_str = old_task.group("indent") if old_task else ""
            task_indent_len = len(task_indent_str.expandtabs(2))
            scan = line_number
            while scan < len(lines):
                raw_child = lines[scan]
                if raw_child.strip() == "":
                    break
                lead = raw_child[: len(raw_child) - len(raw_child.lstrip(" \t"))]
                if len(lead.expandtabs(2)) <= task_indent_len:
                    break
                scan += 1
            child_lines = [f"{task_indent_str}  {c.rstrip()}\n" for c in children_raw]
            lines = _insert_lines(lines, scan, child_lines)

    new_content = "".join(lines)
    diff = _unified_diff(rel, old_content, new_content)
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "revision": revision(old_content),
            "old_status": original_status,
            "diff": diff,
        }

    atomic_write_text(target, new_content)
    update_links_index(vault, rel, new_content)
    invalidate_tasks(vault, rel)
    return {
        "ok": True,
        "revision": revision(new_content),
        "old_status": original_status,
        "diff": diff,
    }


def ensure_task_block_id(vault: pathlib.Path, location: object) -> dict[str, Any]:
    """Append a readable, file-unique ``^id`` to a task line if it has none."""
    rel, target, lines, line_number = locate_task_line(vault, location)
    content = "".join(lines)
    tasks = parse_tasks(content, rel)
    task = next(t for t in tasks if t["location"]["line"] == line_number)
    if not task["block_id"]:
        taken = set(re.findall(r" \^([A-Za-z0-9-]+)$", content, re.M))
        task["block_id"] = block_id_slug(task["description"], taken)
        old = lines[line_number - 1]
        stripped = old.rstrip("\r\n")
        lines[line_number - 1] = (
            f"{stripped.rstrip()} ^{task['block_id']}" + old[len(stripped) :]
        )
        content = "".join(lines)
        atomic_write_text(target, content)
        update_links_index(vault, rel, content)
        invalidate_tasks(vault, rel)
    return {
        "ok": True,
        "id": task["block_id"],
        "revision": revision(content),
    }
