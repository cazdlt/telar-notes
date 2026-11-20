"""Obsidian Tasks-compatible parsing, incremental index, date edits, and block IDs."""

from __future__ import annotations

import calendar
import os
import pathlib
import re
import threading
import unicodedata
from datetime import datetime, timedelta
from typing import Any

from telar.config import atomic_write_text
from telar.links import update_links_index
from telar.vault import revision

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
        value = patch["priority"]
        if value not in (None, "", "⏫", "🔼", "🔺", "⏬", "🔽"):
            raise ValueError("invalid priority")
        line = _TASK_PRIORITY.sub("", line).rstrip()
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
    if new_status not in ("x", "-"):
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
    """Validate a ``TaskLocation`` and return its file lines if the task is unchanged."""
    if not isinstance(location, dict):
        raise TaskLocationError(400, "location and patch required")
    rel, line_number, expected = (
        location.get("path"),
        location.get("line"),
        location.get("expected"),
    )
    if (
        not isinstance(rel, str)
        or not isinstance(line_number, int)
        or not isinstance(expected, str)
    ):
        raise TaskLocationError(400, "invalid task location")
    target = vault / rel
    try:
        target.resolve().relative_to(vault.resolve())
    except ValueError:
        raise TaskLocationError(403, "forbidden") from None
    if not target.is_file():
        raise TaskLocationError(404, "not found")
    lines = target.read_text().splitlines(keepends=True)
    if (
        line_number < 1
        or line_number > len(lines)
        or lines[line_number - 1].rstrip("\r\n") != expected
        or not TASK_LINE_RE.match(expected)
    ):
        raise TaskLocationError(409, "task changed on disk")
    return rel, target, lines, line_number


def update_task_line(
    vault: pathlib.Path,
    location: object,
    patch: dict[str, Any],
    settings: dict[str, Any],
) -> dict[str, Any]:
    """Apply a task patch atomically, handling recurrence and index updates."""
    rel, target, lines, line_number = locate_task_line(vault, location)
    old = lines[line_number - 1].rstrip("\r\n")
    updated = replace_task_dates(old, patch, settings)
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
        else:
            lines[line_number - 1] = updated + line_ending
    else:
        lines[line_number - 1] = updated + line_ending

    new_content = "".join(lines)
    atomic_write_text(target, new_content)
    update_links_index(vault, rel, new_content)
    invalidate_tasks(vault, rel)
    return {
        "ok": True,
        "revision": revision(new_content),
        "old_status": original_status,
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
