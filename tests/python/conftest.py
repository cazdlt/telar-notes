"""Shared pytest fixtures and FastAPI TestClient harness for Telar Notes."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from telar.app import create_app
from telar.config import TelarConfig


class ApiHarness:
    """Manage the shared FastAPI TestClient and its isolated vaults."""

    def __init__(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.work = self.root / "work"
        self.personal = self.root / "personal"
        self.work.mkdir()
        self.personal.mkdir()
        self.config = TelarConfig(self.root / "config.json")
        self.session = self.root / ".session"
        self.app = create_app(str(self.work), self.config, str(self.session))
        self.client = TestClient(self.app, base_url="http://127.0.0.1:7731")
        self.port = 7731

    def reset(self) -> None:
        """Restore the reference contents before a test."""
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
                shutil.rmtree(child) if child.is_dir() else child.unlink()
        self.session.write_text(json.dumps({"active_vault": "work"}))
        (self.work / "daily").mkdir()
        (self.work / "daily" / "today.md").write_text(
            "---\ntitle: Daily focus\ntags: [daily, work]\n---\n# Today\nneedle\n[[project]]\n"
        )
        (self.work / "project.md").write_text("# Project\n[[daily/today]]\n")
        (self.personal / "private.md").write_text("# Private\n")

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, Any]:
        """Perform one HTTP request and decode JSON responses."""
        response = self.client.request(
            method,
            path,
            json=body,
            headers=headers,
        )
        content_type = response.headers.get("content-type", "")
        data: Any = (
            response.json() if "application/json" in content_type else response.content
        )
        return response.status_code, data

    def close(self) -> None:
        """Close the TestClient and delete temporary data."""
        self.client.close()
        self.tmp.cleanup()


@pytest.fixture(scope="session")
def api_server():
    harness = ApiHarness()
    yield harness
    harness.close()


@pytest.fixture
def api(api_server: ApiHarness) -> ApiHarness:
    api_server.reset()
    return api_server
