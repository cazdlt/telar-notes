"""Tests for path traversal, Host/Origin checks, static build boundary, and error codes."""

import re
from pathlib import Path

from fastapi.testclient import TestClient

from telar import config as telar_config
from telar.app import create_app


def test_recent_files_rejects_invalid_sort_and_foreign_origin(api):
    status, body = api.request("GET", "/api/files/recent?sort=size")
    assert status == 400
    assert body == {"error": "invalid sort"}
    status, _ = api.request(
        "GET", "/api/files/recent", headers={"Origin": "https://example.com"}
    )
    assert status == 403
    status, _ = api.request("GET", "/api/files/recent", headers={"Host": "evil.test"})
    assert status == 403


def test_vault_paths_cannot_escape(api):
    requests = [
        ("GET", "/api/note?path=../secret.md", None),
        ("GET", "/api/raw?path=../secret.png", None),
        ("POST", "/api/note", {"path": "../secret.md", "content": "x"}),
        ("POST", "/api/mkdir", {"path": "../secret"}),
        ("POST", "/api/rename", {"from": "project.md", "to": "../secret.md"}),
        ("POST", "/api/delete", {"path": "../secret.md"}),
        (
            "POST",
            "/api/attach",
            {
                "note": "daily/today.md",
                "filename": "../../../../secret",
                "data_b64": "eA==",
            },
        ),
    ]
    for method, path, body in requests:
        status, _ = api.request(method, path, body)
        assert status in (400, 403), path


def test_cross_origin_requests_are_blocked(api):
    status, _ = api.request(
        "GET", "/api/files", headers={"Origin": "https://example.com"}
    )
    assert status == 403


def test_svelte_is_default_and_migration_routes_are_removed(api):
    status, html = api.request("GET", "/")
    assert status == 200
    assert b'<div id="telar-root"></div>' in html
    assert b"/assets/index-" in html
    match = re.search(rb'href="(/assets/favicon-[^"]+\.svg)"', html)
    assert match
    favicon_path = match.group(1).decode()
    status, favicon = api.request("GET", favicon_path)
    assert status == 200
    assert favicon.startswith(b"<svg")

    for path in ("/legacy", "/svelte"):
        status, _ = api.request("GET", path)
        assert status == 404


def test_only_build_files_are_served_as_static(api, monkeypatch):
    dist = api.root / "dist"
    dist.mkdir()
    monkeypatch.setattr(telar_config, "DIST_DIR", dist)
    status, _ = api.request("GET", "/excalidraw-editor.html")
    assert status == 404
    for path in ("/styles.css", "/excalidraw-format.js"):
        status, _ = api.request("GET", path)
        assert status == 404
    (dist / "excalidraw-editor.html").write_text("<p>bundled</p>")
    status, page = api.request("GET", "/excalidraw-editor.html")
    assert status == 200
    assert page == b"<p>bundled</p>"


def test_host_and_origin_boundary_checks(api):
    for headers in (
        {"Host": f"localhost:{api.port}"},
        {"Host": f"localhost:{api.port}", "Origin": f"http://localhost:{api.port}"},
        {"Host": f"127.0.0.1:{api.port}", "Origin": f"http://127.0.0.1:{api.port}"},
    ):
        status, _ = api.request("GET", "/api/vaults", headers=headers)
        assert status == 200, headers
    status, _ = api.request(
        "POST",
        "/api/mkdir",
        {"path": "ok-origin"},
        headers={"Host": f"localhost:{api.port}", "Origin": "http://localhost:5173"},
    )
    assert status == 200

    blocked_headers = [
        {"Host": "evil.test:8080"},
        {"Origin": "null"},
        {"Origin": "https://localhost.evil.com"},
    ]
    for headers in blocked_headers:
        assert api.request("GET", "/api/vaults", headers=headers)[0] == 403, headers
        assert (
            api.request("POST", "/api/mkdir", {"path": "x"}, headers=headers)[0] == 403
        ), headers


def test_endpoints_return_expected_error_statuses(api):
    _, settings = api.request("GET", "/api/settings")
    valid_prefs = settings["preferences"]
    valid_vs = settings["vault_settings"]

    def save_periodic(periodic):
        plugins = {**valid_vs["plugins"], "periodic-notes": periodic}
        status, _ = api.request(
            "POST",
            "/api/settings",
            {"preferences": valid_prefs, "vault_settings": {"plugins": plugins}},
        )
        assert status == 200

    cases = [
        ("GET", "/api/note", None, 400),
        ("GET", "/api/note?path=missing.md", None, 404),
        ("GET", "/api/raw", None, 400),
        ("GET", "/api/raw?path=missing.png", None, 404),
        ("GET", "/api/tasks/block?path=missing.md&id=x", None, 404),
        ("GET", "/assets/..%2F..%2Fsecret", None, 403),
        ("GET", "/assets/missing.js", None, 404),
        ("POST", "/api/unknown", {}, 404),
        ("POST", "/api/note", {"content": "x"}, 400),
        (
            "POST",
            "/api/note",
            {"path": "gone.md", "content": "x", "base_revision": "1"},
            409,
        ),
        ("POST", "/api/settings", {}, 400),
        ("POST", "/api/periodic/today", {"date": "not-a-date"}, 400),
        ("POST", "/api/periodic/today", {"date": "2026-08-12"}, 409),
        ("POST", "/api/tasks/update", {"location": {}}, 400),
        (
            "POST",
            "/api/tasks/update",
            {"location": {"path": 1}, "patch": {}},
            400,
        ),
        (
            "POST",
            "/api/tasks/update",
            {
                "location": {"path": "../x.md", "line": 1, "expected": "- [ ] a"},
                "patch": {},
            },
            403,
        ),
        (
            "POST",
            "/api/tasks/update",
            {
                "location": {"path": "missing.md", "line": 1, "expected": "- [ ] a"},
                "patch": {},
            },
            404,
        ),
        (
            "POST",
            "/api/tasks/update",
            {
                "location": {"path": "daily/today.md", "line": 1, "expected": "---"},
                "patch": {"status": "bad"},
            },
            409,
        ),
        ("POST", "/api/tasks/block-id", {"location": "bad"}, 400),
        (
            "POST",
            "/api/tasks/block-id",
            {"location": {"path": "../x.md", "line": 1, "expected": "- [ ] a"}},
            403,
        ),
        (
            "POST",
            "/api/tasks/block-id",
            {"location": {"path": "missing.md", "line": 1, "expected": "- [ ] a"}},
            404,
        ),
        ("POST", "/api/session/vault", {}, 400),
        ("POST", "/api/vaults/add", {"path": " "}, 400),
        ("POST", "/api/vaults/add", {"path": str(api.root), "name": "   "}, 400),
        ("POST", "/api/vaults/default", {"vault": "missing"}, 404),
        ("POST", "/api/attach", {"note": "project.md", "filename": "a.png"}, 400),
        (
            "POST",
            "/api/attach",
            {"dir": "../out", "filename": "a.png", "data_b64": "eA=="},
            403,
        ),
        ("POST", "/api/mkdir", {}, 400),
        ("POST", "/api/mkdir", {"path": "daily"}, 409),
        ("POST", "/api/rename", {"from": "project.md"}, 400),
        ("POST", "/api/rename", {"from": "missing.md", "to": "other.md"}, 404),
        ("POST", "/api/delete", {}, 400),
        ("POST", "/api/delete", {"path": "missing.md"}, 404),
        ("POST", "/api/reveal", {}, 400),
        ("POST", "/api/reveal", {"path": "../secret.md"}, 400),
        ("POST", "/api/reveal", {"path": "missing.md"}, 404),
    ]
    for method, path, body, expected in cases:
        status, _ = api.request(method, path, body)
        assert status == expected, (method, path, body)

    # Invalid task status (400) on a valid task line.
    (api.work / "project.md").write_text("- [ ] Valid\n")
    status, _ = api.request(
        "POST",
        "/api/tasks/update",
        {
            "location": {"path": "project.md", "line": 1, "expected": "- [ ] Valid"},
            "patch": {"status": "bad"},
        },
    )
    assert status == 400

    # Remaining /api/periodic/today 400/409 guards.
    save_periodic({**valid_vs["plugins"]["periodic-notes"], "enabled": False})
    assert api.request("POST", "/api/periodic/today", {})[0] == 409
    save_periodic({**valid_vs["plugins"]["periodic-notes"], "folder": "/abs"})
    assert api.request("POST", "/api/periodic/today", {})[0] == 400
    save_periodic({**valid_vs["plugins"]["periodic-notes"], "template": "../evil.md"})
    assert api.request("POST", "/api/periodic/today", {})[0] == 400


def test_payload_over_50mib_returns_413(api):
    status, body = api.request(
        "POST",
        "/api/note",
        {"path": "big.md", "content": "x"},
        headers={"Content-Length": str(50 * 1024 * 1024 + 1)},
    )
    assert status == 413
    assert body == {"error": "payload too large"}


def test_attach_rejects_dot_filename_and_vault_root_paths(api):
    assert (
        api.request(
            "POST", "/api/attach", {"dir": ".", "filename": ".", "data_b64": "QQ=="}
        )[0]
        == 400
    )
    assert api.request("POST", "/api/note", {"path": ".", "content": "x"})[0] == 400


def test_raw_sets_sandbox_headers_and_attachment_for_html(api):
    (api.work / "page.html").write_text("<script>alert(1)</script>")
    resp = api.client.get("/api/raw?path=page.html")
    assert resp.status_code == 200
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in resp.headers["content-security-policy"]
    assert "attachment" in resp.headers["content-disposition"]


def _client_with_allowed_hosts(
    tmp_path: Path, allowed_hosts: list[str] | None = None
) -> TestClient:
    """Create a TestClient for an isolated app with optional allowed_hosts."""
    vault = tmp_path / "vault"
    vault.mkdir(exist_ok=True)
    app = create_app(
        str(vault),
        telar_config.TelarConfig(tmp_path / "config.json"),
        str(tmp_path / ".session"),
        allowed_hosts=allowed_hosts,
    )
    return TestClient(app, base_url="http://127.0.0.1:7731")


def _assert_allowed_hosts_boundary(client: TestClient) -> None:
    """Assert configured hosts/origins succeed and unlisted ones return 403."""
    for headers in (
        {"Host": "telar.zamoradelatorre.com"},
        {"Host": "FLORESTA.LOCAL:7731"},
        {"Origin": "https://telar.zamoradelatorre.com"},
    ):
        assert client.get("/api/config", headers=headers).status_code == 200, headers
    for headers in (
        {"Host": "evil.test"},
        {"Origin": "https://evil.test"},
    ):
        assert client.get("/api/config", headers=headers).status_code == 403, headers


def test_allowed_hosts_parameter_permits_configured_hosts(tmp_path):
    with _client_with_allowed_hosts(
        tmp_path, ["telar.zamoradelatorre.com", "floresta.local"]
    ) as client:
        _assert_allowed_hosts_boundary(client)


def test_allowed_hosts_env_var_permits_configured_hosts(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "TELAR_ALLOWED_HOSTS", "telar.zamoradelatorre.com, floresta.local "
    )
    with _client_with_allowed_hosts(tmp_path) as client:
        _assert_allowed_hosts_boundary(client)
