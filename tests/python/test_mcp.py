"""Integration tests for the Telar Notes Streamable HTTP MCP endpoint (/mcp)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from telar import config as telar_config
from telar.app import create_app
from telar.config import TelarConfig

MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


class McpHarness:
    """Isolated Telar FastAPI + MCP TestClient with lifespan enabled."""

    def __init__(self, allowed_hosts: list[str] | None = None) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self._orig_config_dir = telar_config.CONFIG_DIR
        telar_config.CONFIG_DIR = self.root
        self.work = self.root / "work"
        self.personal = self.root / "personal"
        self.work.mkdir()
        self.personal.mkdir()
        self.config = TelarConfig(self.root / "config.json")
        self.session = self.root / ".session"
        self.app = create_app(
            str(self.work),
            self.config,
            str(self.session),
            allowed_hosts=allowed_hosts,
        )
        self._cm = TestClient(self.app, base_url="http://127.0.0.1:7731")
        self.client = self._cm.__enter__()
        self._req_id = 0
        self.reset()

    def reset(self) -> None:
        """Restore reference vault contents before a test."""
        self.config.save(
            {
                "vaults": [
                    {"name": "work", "path": str(self.work)},
                    {"name": "personal", "path": str(self.personal)},
                ],
                "default_vault": "work",
            }
        )
        for vault in (self.work, self.personal):
            for child in vault.iterdir():
                if child.is_dir():
                    import shutil

                    shutil.rmtree(child)
                else:
                    child.unlink()
        self.session.write_text(json.dumps({"active_vault": "work"}))
        (self.work / "daily").mkdir()
        (self.work / "daily" / "today.md").write_text(
            "---\ntitle: Daily focus\ntags: [daily, work]\n---\n"
            "# Today\n\n## Summary\nneedle\n[[project]]\n\n## Tasks\n"
            "- [ ] Review spec ^rev-1\n"
        )
        (self.work / "project.md").write_text("# Project\n[[daily/today]]\n")
        (self.personal / "private.md").write_text("# Private\nSecret note.\n")

    def rpc(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        """Send one JSON-RPC request to ``/mcp``."""
        self._req_id += 1
        req_headers = {**MCP_HEADERS, **(headers or {})}
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": self._req_id,
            "method": method,
        }
        if params is not None:
            payload["params"] = params
        response = self.client.post("/mcp", json=payload, headers=req_headers)
        return response.status_code, response.json()

    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[bool, Any]:
        """Call an MCP tool and return ``(is_error, decoded_payload_or_text)``."""
        status, body = self.rpc(
            "tools/call",
            {"name": name, "arguments": arguments or {}},
            headers=headers,
        )
        assert status == 200, body
        result = body["result"]
        is_error = bool(result.get("isError", False))
        if is_error:
            text = "".join(
                block.get("text", "")
                for block in result.get("content", [])
                if block.get("type") == "text"
            )
            return True, text
        if "structuredContent" in result and result["structuredContent"] is not None:
            return False, result["structuredContent"]
        text = "".join(
            block.get("text", "")
            for block in result.get("content", [])
            if block.get("type") == "text"
        )
        return False, json.loads(text) if text else {}

    def close(self) -> None:
        self._cm.__exit__(None, None, None)
        telar_config.CONFIG_DIR = self._orig_config_dir
        self.tmp.cleanup()


@pytest.fixture
def mcp_harness():
    harness = McpHarness()
    try:
        yield harness
    finally:
        harness.close()


def test_initialize_and_list_tools(mcp_harness: McpHarness) -> None:
    status, body = mcp_harness.rpc(
        "initialize",
        {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "1.0"},
        },
    )
    assert status == 200
    result = body["result"]
    assert result["serverInfo"]["name"] == "telar-notes"
    assert "CLAUDE.md" in result["instructions"]

    status, tools_body = mcp_harness.rpc("tools/list")
    assert status == 200
    names = {tool["name"] for tool in tools_body["result"]["tools"]}
    assert names == {
        "list_vaults",
        "list_files",
        "recent_files",
        "search_notes",
        "note_outline",
        "read_note",
        "create_note",
        "patch_note",
        "open_daily_note",
        "query_tasks",
        "add_task",
        "update_task",
    }


def test_list_vaults_omits_filesystem_paths(mcp_harness: McpHarness) -> None:
    is_err, data = mcp_harness.call_tool("list_vaults")
    assert not is_err
    assert data["active"] == "work"
    assert data["default"] == "work"
    assert [v["name"] for v in data["vaults"]] == ["work", "personal"]
    assert all("path" not in v for v in data["vaults"])


def test_files_recent_and_search(mcp_harness: McpHarness) -> None:
    is_err, files = mcp_harness.call_tool("list_files")
    assert not is_err
    assert any(node["path"] == "project.md" for node in files["tree"])

    is_err, recent = mcp_harness.call_tool("recent_files", {"limit": 5})
    assert not is_err
    assert len(recent["files"]) >= 2

    is_err, search = mcp_harness.call_tool(
        "search_notes", {"query": "needle", "mode": "content"}
    )
    assert not is_err
    assert any(r["path"] == "daily/today.md" for r in search["results"])


def test_outline_and_selective_read(mcp_harness: McpHarness) -> None:
    is_err, outline = mcp_harness.call_tool("note_outline", {"path": "daily/today.md"})
    assert not is_err
    texts = [h["text"] for h in outline["headings"]]
    assert texts == ["Today", "Summary", "Tasks"]

    is_err, section = mcp_harness.call_tool(
        "read_note", {"path": "daily/today.md", "section": "Today > Summary"}
    )
    assert not is_err
    assert "needle" in section["content"]
    assert "Review spec" not in section["content"]

    is_err, lines = mcp_harness.call_tool(
        "read_note", {"path": "daily/today.md", "start_line": 5, "end_line": 7}
    )
    assert not is_err
    assert "# Today" in lines["content"]

    is_err, err_msg = mcp_harness.call_tool(
        "read_note",
        {"path": "daily/today.md", "section": "Summary", "start_line": 1},
    )
    assert is_err
    assert "cannot combine" in err_msg


def test_create_and_patch_note_with_optimistic_locking(
    mcp_harness: McpHarness,
) -> None:
    is_err, created = mcp_harness.call_tool(
        "create_note", {"path": "notes/new.md", "content": "# New\n\n## Log\n"}
    )
    assert not is_err
    assert created["ok"] is True
    rev = created["revision"]

    # Create-only refuses overwrite
    is_err, err_msg = mcp_harness.call_tool(
        "create_note", {"path": "notes/new.md", "content": "overwrite"}
    )
    assert is_err
    assert "already exists" in err_msg

    # Dry-run patch previews diff without writing
    is_err, preview = mcp_harness.call_tool(
        "patch_note",
        {
            "path": "notes/new.md",
            "op": "insert",
            "anchor": "end_of_section",
            "heading": "Log",
            "content": "- Entry 1",
            "base_revision": rev,
            "dry_run": True,
        },
    )
    assert not is_err
    assert preview["dry_run"] is True
    assert "+- Entry 1" in preview["diff"]

    # Real patch writes and advances revision
    is_err, patched = mcp_harness.call_tool(
        "patch_note",
        {
            "path": "notes/new.md",
            "op": "insert",
            "anchor": "end_of_section",
            "heading": "Log",
            "content": "- Entry 1",
            "base_revision": rev,
        },
    )
    assert not is_err
    assert patched["revision"] != rev

    # Stale base_revision fails with conflict
    is_err, conflict = mcp_harness.call_tool(
        "patch_note",
        {
            "path": "notes/new.md",
            "op": "replace_text",
            "old": "Entry 1",
            "new": "Entry 2",
            "base_revision": rev,
        },
    )
    assert is_err
    assert "changed on disk" in conflict


def test_tasks_query_add_and_update(mcp_harness: McpHarness) -> None:
    is_err, queried = mcp_harness.call_tool("query_tasks", {"query": "not done"})
    assert not is_err
    assert len(queried["tasks"]) == 1

    is_err, added = mcp_harness.call_tool(
        "add_task",
        {
            "path": "daily/today.md",
            "description": "Ship MCP endpoint",
            "priority": "high",
            "dates": {"due": "2026-11-25"},
            "tags": ["work"],
            "block_id": "mcp-1",
            "anchor": "end_of_section",
            "heading": "Tasks",
        },
    )
    assert not is_err
    assert added["ok"] is True
    assert added["task"]["block_id"] == "mcp-1"
    assert "^mcp-1" in added["embed"]

    is_err, updated = mcp_harness.call_tool(
        "update_task",
        {
            "path": "daily/today.md",
            "block_id": "mcp-1",
            "status": "x",
        },
    )
    assert not is_err
    assert updated["ok"] is True
    assert updated["old_status"] == " "


def test_open_daily_note(mcp_harness: McpHarness) -> None:
    (mcp_harness.work / "templates").mkdir()
    (mcp_harness.work / "templates" / "daily.md").write_text("# {{title}}\n\n## Log\n")
    cfg = mcp_harness.config.load()
    cfg["vault_settings"] = {
        str(mcp_harness.work.resolve()): {
            "plugins": {
                "periodic-notes": {
                    "enabled": True,
                    "folder": "daily",
                    "format": "YYYY-MM-DD",
                    "template": "templates/daily.md",
                }
            }
        }
    }
    mcp_harness.config.save(cfg)

    is_err, created = mcp_harness.call_tool("open_daily_note", {"date": "2026-11-20"})
    assert not is_err
    assert created["created"] is True
    assert created["path"] == "daily/2026-11-20.md"
    assert "# 2026-11-20" in created["content"]

    is_err, reopened = mcp_harness.call_tool("open_daily_note", {"date": "2026-11-20"})
    assert not is_err
    assert reopened["created"] is False


def test_multi_vault_header_and_argument(mcp_harness: McpHarness) -> None:
    # Header override
    is_err, note = mcp_harness.call_tool(
        "read_note",
        {"path": "private.md"},
        headers={"X-Vault": "personal"},
    )
    assert not is_err
    assert "Secret note." in note["content"]

    # Explicit tool argument override
    is_err, note2 = mcp_harness.call_tool(
        "read_note",
        {"path": "private.md", "vault": "personal"},
    )
    assert not is_err
    assert "Secret note." in note2["content"]

    # Unknown explicit vault fails fast
    is_err, err_msg = mcp_harness.call_tool(
        "read_note",
        {"path": "private.md", "vault": "does-not-exist"},
    )
    assert is_err
    assert "unknown vault" in err_msg


def test_mcp_security_boundary(mcp_harness: McpHarness) -> None:
    # Path traversal rejected
    is_err, err_msg = mcp_harness.call_tool("read_note", {"path": "../secret.txt"})
    assert is_err
    assert "outside the vault" in err_msg

    # Disallowed Host rejected by Telar boundary middleware
    status, body = mcp_harness.rpc(
        "tools/list",
        headers={"Host": "evil.example.com"},
    )
    assert status == 403
    assert body == {"error": "forbidden"}

    # Disallowed Origin rejected
    status, body = mcp_harness.rpc(
        "tools/list",
        headers={"Origin": "https://evil.example.com"},
    )
    assert status == 403
    assert body == {"error": "forbidden"}


def test_mcp_allows_configured_tailscale_host() -> None:
    harness = McpHarness(allowed_hosts=["telar.tailnet.ts.net"])
    try:
        status, body = harness.rpc(
            "tools/list",
            headers={"Host": "telar.tailnet.ts.net"},
        )
        assert status == 200
        assert "tools" in body["result"]
    finally:
        harness.close()
