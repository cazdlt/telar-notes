#!/usr/bin/env python3
"""Zero-dependency CLI client for the Telar Notes HTTP API."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Sequence

DEFAULT_URL = "http://127.0.0.1:7731"


class TelarError(Exception):
    """Raised when an HTTP or transport error occurs talking to Telar."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.payload = payload if payload is not None else {"error": message}


class TelarClient:
    """Minimal HTTP client for the Telar Notes API using Python stdlib only."""

    def __init__(
        self,
        base_url: str | None = None,
        vault: str | None = None,
        opener: Callable[[urllib.request.Request], Any] | None = None,
    ) -> None:
        resolved_url = base_url if base_url is not None else os.environ.get("TELAR_URL")
        self.base_url = (resolved_url or DEFAULT_URL).rstrip("/")
        resolved_vault = vault if vault is not None else os.environ.get("TELAR_VAULT")
        self.vault = resolved_vault or None
        self.opener = opener or urllib.request.urlopen

    def request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        """Send an HTTP request to Telar and return the decoded JSON response."""
        url = f"{self.base_url}{path}"
        if query:
            filtered = [(k, str(v)) for k, v in query.items() if v is not None]
            if filtered:
                url = f"{url}?{urllib.parse.urlencode(filtered)}"

        headers: dict[str, str] = {"Accept": "application/json"}
        if self.vault:
            headers["X-Vault"] = self.vault

        data: bytes | None = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self.opener(req) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw_err = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw_err)
                if not isinstance(parsed, dict):
                    parsed = {"error": raw_err or str(exc)}
            except json.JSONDecodeError:
                parsed = {"error": raw_err or str(exc)}
            msg = str(parsed.get("error") or str(exc))
            raise TelarError(msg, status=exc.code, payload=parsed) from exc
        except urllib.error.URLError as exc:
            raise TelarError(str(exc.reason)) from exc


def _parse_lines_arg(value: str) -> tuple[int, int]:
    """Parse a START:END 1-based inclusive line range."""
    parts = value.split(":")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("expected START:END (e.g. 10:25)")
    try:
        start = int(parts[0])
        end = int(parts[1])
    except ValueError as exc:
        raise argparse.ArgumentTypeError("line numbers must be integers") from exc
    if start < 1 or end < 1 or start > end:
        raise argparse.ArgumentTypeError("expected 1 <= START <= END")
    return start, end


def _read_content_arg(
    parser: argparse.ArgumentParser,
    content: str | None,
    use_stdin: bool,
    *,
    required: bool = False,
) -> str | None:
    """Resolve --content or --stdin into a string."""
    if use_stdin:
        return sys.stdin.read()
    if content is not None:
        return content
    if required:
        parser.error("one of --content or --stdin is required")
    return None


def _flatten_tree(nodes: list[dict[str, Any]]) -> list[str]:
    """Flatten FileNode tree into sorted vault-relative file paths."""
    paths: list[str] = []
    for node in nodes:
        if node.get("type") == "dir":
            paths.extend(_flatten_tree(node.get("children", [])))
        elif "path" in node:
            paths.append(str(node["path"]))
    return paths


def _format_output(command: str, data: Any) -> str:
    """Format an API response for human/agent terminal reading."""
    if command == "files":
        if "files" in data:
            return "\n".join(str(item.get("path", "")) for item in data["files"])
        return "\n".join(_flatten_tree(data.get("tree", [])))

    if command == "search":
        lines = []
        for item in data.get("results", []):
            path = item.get("path", "")
            detail = (
                item.get("snippet")
                or item.get("match")
                or item.get("direction")
                or (", ".join(item["tags"]) if item.get("tags") else "")
            )
            lines.append(f"{path}: {detail}".rstrip(": "))
        return "\n".join(lines)

    if command == "note_outline":
        lines = []
        for h in data.get("headings", []):
            hashes = "#" * int(h.get("level", 1))
            lines.append(
                f"L{h.get('line')}-{h.get('end_line')}  {hashes} {h.get('text')}"
            )
        return "\n".join(lines)

    if command == "note_read":
        return str(data.get("content", "")).rstrip("\n")

    if command == "note_create":
        return f"Created {data.get('path', '')} (revision: {data.get('revision', '')})"

    if command in ("note_patch", "task_add", "task_update"):
        parts = []
        if data.get("dry_run"):
            parts.append("[dry-run]")
        if "revision" in data:
            parts.append(f"revision: {data['revision']}")
        if data.get("embed"):
            parts.append(f"embed: {data['embed']}")
        header = " ".join(parts)
        diff = str(data.get("diff", "")).rstrip("\n")
        if header and diff:
            return f"{header}\n{diff}"
        return diff or header or json.dumps(data)

    if command == "task_query":
        tasks = data.get("tasks", data if isinstance(data, list) else [])
        lines = []
        for t in tasks:
            raw_status = t.get("status", " ")
            status = (
                raw_status.get("symbol", " ")
                if isinstance(raw_status, dict)
                else str(raw_status)
            )
            loc = t.get("location") if isinstance(t.get("location"), dict) else {}
            path = loc.get("path", t.get("path", ""))
            line = loc.get("line", t.get("line", ""))
            desc = t.get("description", "")
            meta: list[str] = []
            if t.get("priority"):
                meta.append(str(t["priority"]))
            dates = t.get("dates")
            if isinstance(dates, dict):
                for key, emoji in (
                    ("due", "📅"),
                    ("scheduled", "⏳"),
                    ("start", "🛫"),
                    ("done", "✅"),
                    ("cancelled", "❌"),
                ):
                    if dates.get(key):
                        meta.append(f"{emoji} {dates[key]}")
            if t.get("block_id"):
                meta.append(f"^{t['block_id']}")
            suffix = f" {' '.join(meta)}" if meta else ""
            lines.append(f"[{status}] {desc}{suffix}  ({path}:{line})")
        return "\n".join(lines)

    return json.dumps(data, indent=2, ensure_ascii=False)


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="telar_cli.py",
        description="CLI client for the Telar Notes HTTP API.",
    )
    parser.add_argument(
        "--url",
        default=None,
        help=f"Telar server URL (default: TELAR_URL or {DEFAULT_URL})",
    )
    parser.add_argument(
        "--vault",
        default=None,
        help="Target vault name sent as X-Vault header (default: TELAR_VAULT)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="raw_json",
        help="Print raw JSON response",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # files
    p_files = sub.add_parser("files", help="List vault files")
    p_files.add_argument("--recent", action="store_true", help="List recent files")
    p_files.add_argument(
        "--sort", choices=["modified", "created"], help="Sort order for --recent"
    )
    p_files.add_argument("--limit", type=int, help="Maximum recent files to return")

    # search
    p_search = sub.add_parser("search", help="Search vault notes")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument(
        "--mode",
        choices=["all", "title", "content", "tags", "links"],
        help="Search mode",
    )

    # note
    p_note = sub.add_parser("note", help="Read, create, outline, or patch notes")
    note_sub = p_note.add_subparsers(dest="note_command", required=True)

    p_outline = note_sub.add_parser("outline", help="Get heading outline of a note")
    p_outline.add_argument("path", help="Vault-relative note path")

    p_read = note_sub.add_parser("read", help="Read a note, section, or line range")
    p_read.add_argument("path", help="Vault-relative note path")
    read_scope = p_read.add_mutually_exclusive_group()
    read_scope.add_argument("--section", help="Heading text or 'Parent > Child' path")
    read_scope.add_argument(
        "--lines", type=_parse_lines_arg, help="1-based inclusive range START:END"
    )

    p_create = note_sub.add_parser("create", help="Create a new note")
    p_create.add_argument("path", help="Vault-relative note path")
    create_src = p_create.add_mutually_exclusive_group()
    create_src.add_argument("--content", help="Note content")
    create_src.add_argument(
        "--stdin", action="store_true", help="Read content from stdin"
    )

    p_patch = note_sub.add_parser("patch", help="Surgically patch an existing note")
    p_patch.add_argument("path", help="Vault-relative note path")
    patch_op = p_patch.add_mutually_exclusive_group(required=True)
    patch_op.add_argument(
        "--insert-after", metavar="HEADING", help="Insert immediately after heading"
    )
    patch_op.add_argument(
        "--append-section", metavar="HEADING", help="Insert at end of section"
    )
    patch_op.add_argument(
        "--insert-before", metavar="HEADING", help="Insert immediately before heading"
    )
    patch_op.add_argument(
        "--append-file", action="store_true", help="Append to end of file"
    )
    patch_op.add_argument(
        "--prepend-file",
        action="store_true",
        help="Prepend at start of file (after frontmatter)",
    )
    patch_op.add_argument(
        "--replace-section", metavar="HEADING", help="Replace body of section"
    )
    patch_op.add_argument(
        "--replace",
        nargs=2,
        metavar=("OLD", "NEW"),
        help="Replace exact unique text",
    )
    patch_src = p_patch.add_mutually_exclusive_group()
    patch_src.add_argument("--content", help="Content for insert/replace-section")
    patch_src.add_argument(
        "--stdin", action="store_true", help="Read content from stdin"
    )
    p_patch.add_argument("--base-revision", help="Expected current revision")
    p_patch.add_argument(
        "--dry-run", action="store_true", help="Preview diff without writing"
    )

    # task
    p_task = sub.add_parser("task", help="Query, add, or update Markdown tasks")
    task_sub = p_task.add_subparsers(dest="task_command", required=True)

    p_tquery = task_sub.add_parser("query", help="Query tasks")
    p_tquery.add_argument("query", nargs="?", default=None, help="Tasks query string")
    p_tquery.add_argument("--source", help="Filter by source note path")

    p_tadd = task_sub.add_parser("add", help="Add a task line to a note")
    p_tadd.add_argument("path", help="Vault-relative note path")
    p_tadd.add_argument("--text", required=True, help="Task description text")
    p_tadd.add_argument("--status", help="Task status char (default: space)")
    p_tadd.add_argument("--priority", help="Priority emoji or name (highest..lowest)")
    p_tadd.add_argument("--due", help="Due date (YYYY-MM-DD)")
    p_tadd.add_argument("--start", help="Start date (YYYY-MM-DD)")
    p_tadd.add_argument("--scheduled", help="Scheduled date (YYYY-MM-DD)")
    p_tadd.add_argument("--tag", action="append", help="Tag (repeatable)")
    p_tadd.add_argument("--id", dest="block_id", help="Block ID without ^")
    p_tadd.add_argument("--section", help="Target heading")
    p_tadd.add_argument(
        "--anchor",
        choices=["end_of_section", "after_heading", "before_heading", "end_of_file"],
        help="Insertion anchor",
    )
    p_tadd.add_argument(
        "--child", action="append", help="Indented child line (repeatable)"
    )
    p_tadd.add_argument(
        "--dry-run", action="store_true", help="Preview diff without writing"
    )

    p_tupd = task_sub.add_parser("update", help="Update an existing task")
    p_tupd.add_argument("path", help="Vault-relative note path")
    loc_group = p_tupd.add_mutually_exclusive_group(required=True)
    loc_group.add_argument("--id", dest="block_id", help="Locate by ^block_id")
    loc_group.add_argument("--match", help="Locate by unique substring match")
    loc_group.add_argument("--line", type=int, help="Locate by 1-based line number")
    p_tupd.add_argument("--status", help="New task status char")
    p_tupd.add_argument("--text", help="New task description")
    p_tupd.add_argument("--priority", help="New priority emoji/name, or empty to clear")
    p_tupd.add_argument("--due", help="New due date (YYYY-MM-DD) or empty")
    p_tupd.add_argument("--start", help="New start date (YYYY-MM-DD) or empty")
    p_tupd.add_argument("--scheduled", help="New scheduled date (YYYY-MM-DD) or empty")
    p_tupd.add_argument("--set-id", help="Assign a ^block_id if task has none")
    p_tupd.add_argument(
        "--child", action="append", help="Append indented child line (repeatable)"
    )
    p_tupd.add_argument(
        "--dry-run", action="store_true", help="Preview diff without writing"
    )

    return parser


def _dispatch(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    client: TelarClient,
) -> tuple[str, Any]:
    """Execute the parsed CLI command via TelarClient."""
    if args.command == "files":
        if args.recent:
            data = client.request(
                "GET",
                "/api/files/recent",
                query={"sort": args.sort, "limit": args.limit},
            )
        else:
            data = client.request("GET", "/api/files")
        return "files", data

    if args.command == "search":
        data = client.request(
            "GET",
            "/api/search",
            query={"q": args.query, "mode": args.mode},
        )
        return "search", data

    if args.command == "note":
        if args.note_command == "outline":
            data = client.request("GET", "/api/note/outline", query={"path": args.path})
            return "note_outline", data

        if args.note_command == "read":
            query: dict[str, Any] = {"path": args.path}
            if args.section is not None:
                query["section"] = args.section
            elif args.lines is not None:
                query["start_line"] = args.lines[0]
                query["end_line"] = args.lines[1]
            data = client.request("GET", "/api/note", query=query)
            return "note_read", data

        if args.note_command == "create":
            content = _read_content_arg(parser, args.content, args.stdin)
            data = client.request(
                "POST",
                "/api/note",
                body={
                    "path": args.path,
                    "content": content if content is not None else "",
                    "base_revision": None,
                },
            )
            if isinstance(data, dict) and "path" not in data:
                data["path"] = args.path
            return "note_create", data

        if args.note_command == "patch":
            body: dict[str, Any] = {"path": args.path}
            if args.replace is not None:
                if args.content is not None or args.stdin:
                    parser.error("--content/--stdin cannot be used with --replace")
                body["op"] = "replace_text"
                body["old"] = args.replace[0]
                body["new"] = args.replace[1]
            elif args.replace_section is not None:
                body["op"] = "replace_section"
                body["heading"] = args.replace_section
                body["content"] = _read_content_arg(
                    parser, args.content, args.stdin, required=True
                )
            else:
                body["op"] = "insert"
                if args.insert_after is not None:
                    body["anchor"] = "after_heading"
                    body["heading"] = args.insert_after
                elif args.append_section is not None:
                    body["anchor"] = "end_of_section"
                    body["heading"] = args.append_section
                elif args.insert_before is not None:
                    body["anchor"] = "before_heading"
                    body["heading"] = args.insert_before
                elif args.append_file:
                    body["anchor"] = "end_of_file"
                elif args.prepend_file:
                    body["anchor"] = "start_of_file"
                body["content"] = _read_content_arg(
                    parser, args.content, args.stdin, required=True
                )

            if args.base_revision is not None:
                body["base_revision"] = args.base_revision
            if args.dry_run:
                body["dry_run"] = True
            data = client.request("POST", "/api/note/patch", body=body)
            return "note_patch", data

    if args.command == "task":
        if args.task_command == "query":
            data = client.request(
                "GET",
                "/api/tasks",
                query={"query": args.query, "source": args.source},
            )
            return "task_query", data

        if args.task_command == "add":
            body = {"path": args.path, "description": args.text}
            if args.status is not None:
                body["status"] = args.status
            if args.priority is not None:
                body["priority"] = args.priority
            dates = {
                k: v
                for k, v in (
                    ("due", args.due),
                    ("start", args.start),
                    ("scheduled", args.scheduled),
                )
                if v is not None
            }
            if dates:
                body["dates"] = dates
            if args.tag:
                body["tags"] = args.tag
            if args.block_id is not None:
                body["block_id"] = args.block_id
            if args.section is not None:
                body["heading"] = args.section
            if args.anchor is not None:
                body["anchor"] = args.anchor
            if args.child:
                body["children"] = args.child
            if args.dry_run:
                body["dry_run"] = True
            data = client.request("POST", "/api/tasks/add", body=body)
            return "task_add", data

        if args.task_command == "update":
            location: dict[str, Any] = {"path": args.path}
            if args.block_id is not None:
                location["block_id"] = args.block_id
            elif args.match is not None:
                location["match"] = args.match
            elif args.line is not None:
                location["line"] = args.line

            patch: dict[str, Any] = {}
            if args.status is not None:
                patch["status"] = args.status
            if args.text is not None:
                patch["description"] = args.text
            if args.priority is not None:
                patch["priority"] = args.priority
            if args.due is not None:
                patch["due"] = args.due
            if args.start is not None:
                patch["start"] = args.start
            if args.scheduled is not None:
                patch["scheduled"] = args.scheduled
            if args.set_id is not None:
                patch["block_id"] = args.set_id
            if args.child:
                patch["append_children"] = args.child

            if not patch:
                parser.error("task update requires at least one patch option")

            body = {"location": location, "patch": patch}
            if args.dry_run:
                body["dry_run"] = True
            data = client.request("POST", "/api/tasks/update", body=body)
            return "task_update", data

    parser.error("unknown command")
    return "", {}


def main(
    argv: Sequence[str] | None = None,
    *,
    client: TelarClient | None = None,
) -> int:
    """CLI entrypoint returning an exit code."""
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    resolved_client = client or TelarClient(base_url=args.url, vault=args.vault)
    try:
        cmd_key, data = _dispatch(parser, args, resolved_client)
    except TelarError as exc:
        print(json.dumps(exc.payload, ensure_ascii=False), file=sys.stderr)
        return 1

    if args.raw_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(_format_output(cmd_key, data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
