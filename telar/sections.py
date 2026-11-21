"""Section-aware Markdown outline parsing, reading, and surgical patching."""

from __future__ import annotations

import difflib
import re
import unicodedata
from typing import Any

_HEADING_RE = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.+?)\s*$")
_TRAILING_HASH_RE = re.compile(r"[ \t]+#+$")
_FENCE_PREFIX_RE = re.compile(r"^(?:\s*(?:[-+*]|\d+[.)]|>)\s*)*\s*")
_FENCE_OPEN_RE = re.compile(r"^(`{3,}|~{3,})(.*)$")

_INSERT_ANCHORS = frozenset(
    {
        "after_heading",
        "end_of_section",
        "before_heading",
        "end_of_file",
        "start_of_file",
    }
)


class SectionError(Exception):
    """Typed error carrying an HTTP status code and optional structured details."""

    def __init__(self, status: int, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.extra = extra


def _frontmatter_end_line(lines: list[str]) -> int:
    """Return the 1-based closing line of YAML frontmatter, or 0 if absent."""
    if not lines or not re.match(r"^---\s*$", lines[0]):
        return 0
    for idx in range(1, len(lines)):
        if re.match(r"^---\s*$", lines[idx]):
            return idx + 1
    return 0


def _strip_fence_prefix(line: str) -> str:
    """Strip leading indentation, list markers, and blockquote markers."""
    return _FENCE_PREFIX_RE.sub("", line, count=1)


def _match_fence_open(line: str) -> tuple[str, int] | None:
    """Return ``(fence_char, fence_len)`` if ``line`` opens a fenced code block."""
    stripped = _strip_fence_prefix(line)
    match = _FENCE_OPEN_RE.match(stripped)
    if not match:
        return None
    marker, info = match.group(1), match.group(2)
    if marker[0] == "`" and "`" in info:
        return None
    return marker[0], len(marker)


def _is_fence_close(line: str, fence_char: str, fence_len: int) -> bool:
    """Return True if ``line`` closes the active fenced code block."""
    stripped = _strip_fence_prefix(line)
    return bool(re.match(rf"^{re.escape(fence_char)}{{{fence_len},}}\s*$", stripped))


def parse_outline(content: str) -> list[dict[str, Any]]:
    """Parse Markdown ATX headings, ignoring YAML frontmatter and fenced code blocks.

    Returns a list of ``{"level": int, "text": str, "line": int, "end_line": int}``
    dicts with 1-based inclusive line numbers.
    """
    lines = content.splitlines()
    total_lines = len(lines)
    if total_lines == 0:
        return []

    fm_end = _frontmatter_end_line(lines)
    headings: list[dict[str, Any]] = []
    active_fence: tuple[str, int] | None = None

    for idx in range(fm_end, total_lines):
        line = lines[idx]
        if active_fence is not None:
            if _is_fence_close(line, active_fence[0], active_fence[1]):
                active_fence = None
            continue

        opened = _match_fence_open(line)
        if opened is not None:
            active_fence = opened
            continue

        match = _HEADING_RE.match(line)
        if not match:
            continue
        text = _TRAILING_HASH_RE.sub("", match.group(2)).strip()
        if not text:
            continue
        headings.append(
            {
                "level": len(match.group(1)),
                "text": text,
                "line": idx + 1,
                "end_line": total_lines,
            }
        )

    for i, heading in enumerate(headings):
        for nxt in headings[i + 1 :]:
            if nxt["level"] <= heading["level"]:
                heading["end_line"] = nxt["line"] - 1
                break

    return headings


def _normalize_heading(text: str) -> str:
    """Normalize text with NFC, casefolding, and accent removal."""
    nfd = unicodedata.normalize("NFD", unicodedata.normalize("NFC", text.strip()))
    without_marks = "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")
    return unicodedata.normalize("NFC", without_marks).casefold()


def _heading_paths(headings: list[dict[str, Any]]) -> list[list[str]]:
    """Compute the full ancestor text path for each heading in ``headings``."""
    stack: list[dict[str, Any]] = []
    paths: list[list[str]] = []
    for heading in headings:
        while stack and stack[-1]["level"] >= heading["level"]:
            stack.pop()
        paths.append([item["text"] for item in stack] + [heading["text"]])
        stack.append(heading)
    return paths


def resolve_heading(content: str, section: str) -> dict[str, Any]:
    """Resolve a heading by bare text or ``Parent > Child`` path.

    Matching is NFC-normalized, case-folded, and accent-insensitive.
    Raises ``SectionError(404, ...)`` if not found or ``SectionError(409, ...)``
    with a ``candidates`` list if ambiguous.
    """
    query_parts = [_normalize_heading(part) for part in section.split(">")]
    if not any(query_parts) or any(not part for part in query_parts):
        raise SectionError(400, "invalid section query")

    headings = parse_outline(content)
    paths = _heading_paths(headings)
    matches: list[tuple[dict[str, Any], list[str]]] = []

    for heading, path in zip(headings, paths, strict=True):
        norm_path = [_normalize_heading(part) for part in path]
        if len(query_parts) == 1:
            if norm_path[-1] == query_parts[0]:
                matches.append((heading, path))
        elif (
            len(norm_path) >= len(query_parts)
            and norm_path[-len(query_parts) :] == query_parts
        ):
            matches.append((heading, path))

    if not matches:
        raise SectionError(404, "section not found")
    if len(matches) > 1:
        raise SectionError(
            409,
            "ambiguous section",
            candidates=[" > ".join(path) for _, path in matches],
        )
    return matches[0][0]


def read_section(content: str, section: str) -> dict[str, Any]:
    """Return the heading text, 1-based line bounds, and content of a section."""
    heading = resolve_heading(content, section)
    lines = content.splitlines()
    start_line = heading["line"]
    end_line = heading["end_line"]
    return {
        "section": heading["text"],
        "start_line": start_line,
        "end_line": end_line,
        "content": "\n".join(lines[start_line - 1 : end_line]),
    }


def read_lines(
    content: str,
    start_line: int | None,
    end_line: int | None,
) -> dict[str, Any]:
    """Return a 1-based inclusive line slice from ``content``."""
    if start_line is not None and start_line < 1:
        raise SectionError(400, "start_line must be >= 1")
    if end_line is not None and end_line < 1:
        raise SectionError(400, "end_line must be >= 1")
    if start_line is not None and end_line is not None and start_line > end_line:
        raise SectionError(400, "start_line must be <= end_line")

    lines = content.splitlines()
    total = len(lines)
    start = start_line if start_line is not None else 1
    end = min(end_line, total) if end_line is not None else total
    sliced = lines[start - 1 : end] if start <= total else []
    return {
        "start_line": start,
        "end_line": end,
        "content": "\n".join(sliced),
    }


def _join_lines(
    lines: list[str],
    line_ending: str,
    trailing_newline: bool,
) -> str:
    """Reconstruct note text while preserving line-ending and trailing-newline conventions."""
    if not lines:
        return ""
    joined = line_ending.join(lines)
    return f"{joined}{line_ending}" if trailing_newline else joined


def _unified_diff(old_content: str, new_content: str, rel_path: str) -> str:
    """Build a unified diff string for a note update."""
    diff_lines = list(
        difflib.unified_diff(
            old_content.splitlines(),
            new_content.splitlines(),
            fromfile=f"a/{rel_path}",
            tofile=f"b/{rel_path}",
            lineterm="",
        )
    )
    if not diff_lines:
        return ""
    return "\n".join(diff_lines) + "\n"


def patch_note(
    content: str,
    rel_path: str,
    payload: dict[str, Any],
) -> tuple[str, str]:
    """Apply a surgical patch operation and return ``(new_content, unified_diff)``."""
    op = payload.get("op")
    if op == "replace_text":
        old = payload.get("old")
        new = payload.get("new")
        if not isinstance(old, str) or not old:
            raise SectionError(400, "old must be a non-empty string")
        if not isinstance(new, str):
            raise SectionError(400, "new must be a string")
        count = content.count(old)
        if count == 0:
            raise SectionError(404, "text not found")
        if count > 1:
            raise SectionError(409, "text matched multiple times", count=count)
        new_content = content.replace(old, new, 1)
        return new_content, _unified_diff(content, new_content, rel_path)

    lines = content.splitlines()
    line_ending = "\r\n" if "\r\n" in content else "\n"

    if op == "insert":
        insert_text = payload.get("content")
        if not isinstance(insert_text, str):
            raise SectionError(400, "content must be a string")
        anchor = payload.get("anchor", "end_of_file")
        if not isinstance(anchor, str) or anchor not in _INSERT_ANCHORS:
            raise SectionError(400, "invalid anchor")

        if anchor == "start_of_file":
            idx = _frontmatter_end_line(lines)
        elif anchor == "end_of_file":
            idx = len(lines)
        else:
            heading_query = payload.get("heading")
            if not isinstance(heading_query, str) or not heading_query.strip():
                raise SectionError(400, "heading required")
            heading = resolve_heading(content, heading_query)
            if anchor == "after_heading":
                idx = heading["line"]
            elif anchor == "end_of_section":
                idx = heading["end_line"]
            else:  # before_heading
                idx = heading["line"] - 1

        insert_lines = insert_text.splitlines()
        new_lines = lines[:idx] + insert_lines + lines[idx:]
        trailing_nl = content.endswith("\n") if content else insert_text.endswith("\n")
        new_content = _join_lines(new_lines, line_ending, trailing_nl)
        return new_content, _unified_diff(content, new_content, rel_path)

    if op == "replace_section":
        heading_query = payload.get("heading")
        if not isinstance(heading_query, str) or not heading_query.strip():
            raise SectionError(400, "heading required")
        body_text = payload.get("content")
        if not isinstance(body_text, str):
            raise SectionError(400, "content must be a string")
        heading = resolve_heading(content, heading_query)
        body_lines = body_text.splitlines()
        new_lines = lines[: heading["line"]] + body_lines + lines[heading["end_line"] :]
        trailing_nl = content.endswith("\n") if content else body_text.endswith("\n")
        new_content = _join_lines(new_lines, line_ending, trailing_nl)
        return new_content, _unified_diff(content, new_content, rel_path)

    raise SectionError(400, "invalid op")
