"""Unit tests for the bundled telar_cli.py client."""

from __future__ import annotations

import email.message
import importlib.util
import io
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import pytest

_CLI_PATH = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "telar-vault"
    / "scripts"
    / "telar_cli.py"
)
_SPEC = importlib.util.spec_from_file_location("telar_cli", _CLI_PATH)
assert _SPEC is not None and _SPEC.loader is not None
telar_cli = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(telar_cli)


class _FakeResponse:
    def __init__(self, payload: dict[str, Any], status: int = 200) -> None:
        self._raw = json.dumps(payload).encode("utf-8")
        self.status = status

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


class _Recorder:
    def __init__(self, response_payload: dict[str, Any] | None = None) -> None:
        self.requests: list[dict[str, Any]] = []
        self.response_payload = response_payload or {"ok": True}

    def __call__(self, req: urllib.request.Request) -> _FakeResponse:
        parsed = urllib.parse.urlparse(req.full_url)
        body = (
            json.loads(req.data.decode("utf-8"))
            if isinstance(req.data, bytes)
            else None
        )
        self.requests.append(
            {
                "method": req.get_method(),
                "url": req.full_url,
                "path": parsed.path,
                "query": urllib.parse.parse_qs(parsed.query),
                "headers": {k.lower(): v for k, v in req.header_items()},
                "body": body,
            }
        )
        return _FakeResponse(self.response_payload)


def _run(
    argv: list[str],
    *,
    payload: dict[str, Any] | None = None,
    url: str | None = None,
    vault: str | None = None,
) -> tuple[int, list[dict[str, Any]]]:
    rec = _Recorder(payload)
    client = telar_cli.TelarClient(base_url=url, vault=vault, opener=rec)
    code = telar_cli.main(argv, client=client)
    return code, rec.requests


def test_client_config_env_and_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELAR_URL", "http://127.0.0.1:8888/")
    monkeypatch.setenv("TELAR_VAULT", "notes")
    rec = _Recorder({"tree": []})
    client = telar_cli.TelarClient(opener=rec)
    client.request("GET", "/api/files")
    assert rec.requests[0]["url"] == "http://127.0.0.1:8888/api/files"
    assert rec.requests[0]["headers"]["x-vault"] == "notes"


def test_files_and_recent_files(capsys: pytest.CaptureFixture[str]) -> None:
    code, reqs = _run(
        ["files"],
        payload={
            "tree": [
                {
                    "path": "dir",
                    "type": "dir",
                    "children": [{"path": "dir/a.md", "type": "file", "name": "a.md"}],
                }
            ]
        },
    )
    assert code == 0
    assert reqs[0]["method"] == "GET"
    assert reqs[0]["path"] == "/api/files"
    assert capsys.readouterr().out.strip() == "dir/a.md"

    code, reqs = _run(
        ["files", "--recent", "--sort", "created", "--limit", "15"],
        payload={"files": [{"path": "b.md"}]},
    )
    assert code == 0
    assert reqs[0]["path"] == "/api/files/recent"
    assert reqs[0]["query"] == {"sort": ["created"], "limit": ["15"]}


def test_search_and_json_flag(capsys: pytest.CaptureFixture[str]) -> None:
    payload = {"results": [{"path": "note.md", "snippet": "match"}]}
    code, reqs = _run(
        ["--json", "search", "roadmap", "--mode", "content"], payload=payload
    )
    assert code == 0
    assert reqs[0]["path"] == "/api/search"
    assert reqs[0]["query"] == {"q": ["roadmap"], "mode": ["content"]}
    assert json.loads(capsys.readouterr().out) == payload


def test_note_outline_and_read(capsys: pytest.CaptureFixture[str]) -> None:
    code, reqs = _run(
        ["note", "outline", "a/b.md"],
        payload={"headings": [{"level": 2, "text": "Intro", "line": 3, "end_line": 9}]},
    )
    assert code == 0
    assert reqs[0]["path"] == "/api/note/outline"
    assert reqs[0]["query"] == {"path": ["a/b.md"]}
    assert "L3-9  ## Intro" in capsys.readouterr().out

    code, reqs = _run(
        ["note", "read", "a/b.md", "--section", "Parent > Child"],
        payload={"content": "hello"},
    )
    assert code == 0
    assert reqs[0]["path"] == "/api/note"
    assert reqs[0]["query"] == {"path": ["a/b.md"], "section": ["Parent > Child"]}

    code, reqs = _run(
        ["note", "read", "a/b.md", "--lines", "10:25"],
        payload={"content": "slice"},
    )
    assert code == 0
    assert reqs[0]["query"] == {
        "path": ["a/b.md"],
        "start_line": ["10"],
        "end_line": ["25"],
    }


def test_note_create_content_and_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    code, reqs = _run(
        ["note", "create", "new.md", "--content", "# Hi"],
        payload={"ok": True, "revision": "r1"},
    )
    assert code == 0
    assert reqs[0]["method"] == "POST"
    assert reqs[0]["path"] == "/api/note"
    assert reqs[0]["body"] == {
        "path": "new.md",
        "content": "# Hi",
        "base_revision": None,
    }

    monkeypatch.setattr(sys, "stdin", io.StringIO("line1\nline2\n"))
    code, reqs = _run(
        ["note", "create", "stdin.md", "--stdin"],
        payload={"ok": True, "revision": "r2"},
    )
    assert code == 0
    assert reqs[0]["body"]["content"] == "line1\nline2\n"


@pytest.mark.parametrize(
    ("extra_args", "expected_body"),
    [
        (
            ["--insert-after", "H1", "--content", "x"],
            {
                "op": "insert",
                "anchor": "after_heading",
                "heading": "H1",
                "content": "x",
            },
        ),
        (
            ["--append-section", "H1", "--content", "x"],
            {
                "op": "insert",
                "anchor": "end_of_section",
                "heading": "H1",
                "content": "x",
            },
        ),
        (
            ["--insert-before", "H1", "--content", "x"],
            {
                "op": "insert",
                "anchor": "before_heading",
                "heading": "H1",
                "content": "x",
            },
        ),
        (
            ["--append-file", "--content", "x"],
            {"op": "insert", "anchor": "end_of_file", "content": "x"},
        ),
        (
            ["--prepend-file", "--content", "x"],
            {"op": "insert", "anchor": "start_of_file", "content": "x"},
        ),
        (
            ["--replace-section", "H1", "--content", "x"],
            {"op": "replace_section", "heading": "H1", "content": "x"},
        ),
        (
            ["--replace", "old", "new"],
            {"op": "replace_text", "old": "old", "new": "new"},
        ),
    ],
)
def test_note_patch_ops(extra_args: list[str], expected_body: dict[str, Any]) -> None:
    code, reqs = _run(
        ["note", "patch", "n.md", *extra_args, "--base-revision", "rev1", "--dry-run"],
        payload={"ok": True, "dry_run": True, "revision": "rev1", "diff": "--- a/n.md"},
    )
    assert code == 0
    assert reqs[0]["method"] == "POST"
    assert reqs[0]["path"] == "/api/note/patch"
    assert reqs[0]["body"] == {
        "path": "n.md",
        **expected_body,
        "base_revision": "rev1",
        "dry_run": True,
    }


def test_note_patch_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("body\n"))
    code, reqs = _run(["note", "patch", "n.md", "--append-file", "--stdin"])
    assert code == 0
    assert reqs[0]["body"]["content"] == "body\n"


def test_task_query_and_add() -> None:
    code, reqs = _run(
        ["task", "query", "not done", "--source", "daily.md"],
        payload={"tasks": []},
    )
    assert code == 0
    assert reqs[0]["path"] == "/api/tasks"
    assert reqs[0]["query"] == {"query": ["not done"], "source": ["daily.md"]}

    code, reqs = _run(
        [
            "task",
            "add",
            "daily.md",
            "--text",
            "Ship it",
            "--status",
            " ",
            "--priority",
            "high",
            "--due",
            "2026-11-25",
            "--start",
            "2026-11-21",
            "--scheduled",
            "2026-11-22",
            "--tag",
            "work",
            "--tag",
            "#urgent",
            "--id",
            "ship1",
            "--section",
            "Today",
            "--anchor",
            "end_of_section",
            "--child",
            "sub 1",
            "--child",
            "sub 2",
            "--dry-run",
        ],
        payload={
            "ok": True,
            "dry_run": True,
            "revision": "r1",
            "diff": "+ - [ ] Ship it",
        },
    )
    assert code == 0
    assert reqs[0]["path"] == "/api/tasks/add"
    assert reqs[0]["body"] == {
        "path": "daily.md",
        "description": "Ship it",
        "status": " ",
        "priority": "high",
        "dates": {
            "due": "2026-11-25",
            "start": "2026-11-21",
            "scheduled": "2026-11-22",
        },
        "tags": ["work", "#urgent"],
        "block_id": "ship1",
        "heading": "Today",
        "anchor": "end_of_section",
        "children": ["sub 1", "sub 2"],
        "dry_run": True,
    }


@pytest.mark.parametrize(
    ("locator_args", "expected_loc"),
    [
        (["--id", "b1"], {"path": "t.md", "block_id": "b1"}),
        (["--match", "Buy milk"], {"path": "t.md", "match": "Buy milk"}),
        (["--line", "12"], {"path": "t.md", "line": 12}),
    ],
)
def test_task_update_locators_and_patch(
    locator_args: list[str], expected_loc: dict[str, Any]
) -> None:
    code, reqs = _run(
        [
            "task",
            "update",
            "t.md",
            *locator_args,
            "--status",
            "x",
            "--text",
            "Updated",
            "--priority",
            "medium",
            "--due",
            "2026-11-30",
            "--start",
            "2026-11-20",
            "--scheduled",
            "2026-11-21",
            "--set-id",
            "newid",
            "--child",
            "note 1",
            "--child",
            "note 2",
            "--dry-run",
        ],
        payload={"ok": True, "revision": "r2", "diff": "..."},
    )
    assert code == 0
    assert reqs[0]["path"] == "/api/tasks/update"
    assert reqs[0]["body"] == {
        "location": expected_loc,
        "patch": {
            "status": "x",
            "description": "Updated",
            "priority": "medium",
            "due": "2026-11-30",
            "start": "2026-11-20",
            "scheduled": "2026-11-21",
            "block_id": "newid",
            "append_children": ["note 1", "note 2"],
        },
        "dry_run": True,
    }


def test_http_error_handling(capsys: pytest.CaptureFixture[str]) -> None:
    def failing_opener(req: urllib.request.Request) -> Any:
        raise urllib.error.HTTPError(
            req.full_url,
            409,
            "Conflict",
            hdrs=email.message.Message(),
            fp=io.BytesIO(json.dumps({"error": "revision mismatch"}).encode("utf-8")),
        )

    client = telar_cli.TelarClient(
        base_url="http://127.0.0.1:7731", opener=failing_opener
    )
    code = telar_cli.main(["files"], client=client)
    assert code == 1
    err = capsys.readouterr().err.strip()
    assert json.loads(err) == {"error": "revision mismatch"}


def test_cli_end_to_end_against_fastapi(
    api: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exercise telar_cli end-to-end against the real FastAPI routes."""

    def live_opener(req: urllib.request.Request) -> _FakeResponse:
        parsed = urllib.parse.urlparse(req.full_url)
        target = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        headers = {k: v for k, v in req.header_items()}
        resp = api.client.request(
            req.get_method(),
            target,
            content=req.data,
            headers=headers,
        )
        if resp.status_code >= 400:
            raise urllib.error.HTTPError(
                req.full_url,
                resp.status_code,
                resp.reason_phrase,
                hdrs=email.message.Message(),
                fp=io.BytesIO(resp.content),
            )
        return _FakeResponse(resp.json())

    client = telar_cli.TelarClient(
        base_url="http://127.0.0.1:7731", vault="personal", opener=live_opener
    )

    assert (
        telar_cli.main(
            [
                "note",
                "create",
                "pendientes.md",
                "--content",
                "# Pendientes\n\n## Trámites\n",
            ],
            client=client,
        )
        == 0
    )
    capsys.readouterr()

    assert telar_cli.main(["note", "outline", "pendientes.md"], client=client) == 0
    outline = capsys.readouterr().out
    assert "# Pendientes" in outline
    assert "## Trámites" in outline

    assert (
        telar_cli.main(
            [
                "note",
                "patch",
                "pendientes.md",
                "--append-section",
                "Tramites",
                "--content",
                "Nota inicial.",
            ],
            client=client,
        )
        == 0
    )
    capsys.readouterr()

    assert (
        telar_cli.main(
            [
                "task",
                "add",
                "pendientes.md",
                "--text",
                "Pagar predial",
                "--priority",
                "high",
                "--due",
                "2026-11-30",
                "--id",
                "pagar-predial",
                "--section",
                "Trámites",
                "--child",
                "- 2026-11-20: Factura descargada",
            ],
            client=client,
        )
        == 0
    )
    add_out = capsys.readouterr().out
    assert "![[pendientes#^pagar-predial]]" in add_out

    assert telar_cli.main(["task", "query", "not done"], client=client) == 0
    query_out = capsys.readouterr().out
    assert (
        "[ ] Pagar predial ⏫ 📅 2026-11-30 ^pagar-predial  (pendientes.md:"
        in query_out
    )

    assert (
        telar_cli.main(
            [
                "task",
                "update",
                "pendientes.md",
                "--id",
                "pagar-predial",
                "--status",
                "/",
                "--child",
                "- 2026-11-21: Pago programado",
            ],
            client=client,
        )
        == 0
    )
    capsys.readouterr()

    assert (
        telar_cli.main(
            ["note", "read", "pendientes.md", "--section", "Trámites"], client=client
        )
        == 0
    )
    section_out = capsys.readouterr().out
    assert "- [/] Pagar predial" in section_out
    assert "  - 2026-11-20: Factura descargada" in section_out
    assert "  - 2026-11-21: Pago programado" in section_out
