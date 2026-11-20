"""Tests for file tree, note CRUD, recent files, raw bytes, attachments, and periodic notes."""

import base64
import json
import os

import pytest

from telar import vault as telar_vault


def _set_times(path, seconds):
    os.utime(path, (seconds, seconds))


def _save_attachment_folder(api, folder):
    _, settings = api.request("GET", "/api/settings")
    vault_settings = {
        **settings["vault_settings"],
        "files": {"attachment_folder": folder},
    }
    _, saved = api.request(
        "POST",
        "/api/settings",
        {"preferences": settings["preferences"], "vault_settings": vault_settings},
    )
    return saved["vault_settings"]["files"]["attachment_folder"]


def test_note_read_write_round_trip(api):
    content = "# New\nunsaved work\n"
    path = "diario/2026/08/2026-08-12.md"
    status, _ = api.request("POST", "/api/note", {"path": path, "content": content})
    assert status == 200
    status, body = api.request("GET", f"/api/note?path={path}")
    assert status == 200
    assert body["content"] == content


def test_note_revision_rejects_stale_write_and_allows_force(api):
    _, note = api.request("GET", "/api/note?path=daily/today.md")
    (api.work / "daily" / "today.md").write_text("# External\n")
    status, body = api.request(
        "POST",
        "/api/note",
        {
            "path": "daily/today.md",
            "content": "# Local\n",
            "base_revision": note["revision"],
        },
    )
    assert status == 409
    assert body["content"] == "# External\n"
    status, body = api.request(
        "POST",
        "/api/note",
        {
            "path": "daily/today.md",
            "content": "# Local\n",
            "base_revision": body["revision"],
            "force": True,
        },
    )
    assert status == 200
    assert body["revision"]


def test_note_create_only_rejects_existing_path(api):
    status, _ = api.request(
        "POST",
        "/api/note",
        {"path": "daily/today.md", "content": "x", "base_revision": None},
    )
    assert status == 409
    status, body = api.request(
        "POST", "/api/note", {"path": "fresh.md", "content": "x", "base_revision": None}
    )
    assert status == 200
    assert body["revision"]


def test_create_folder_and_tree(api):
    status, _ = api.request("POST", "/api/mkdir", {"path": "empty"})
    assert status == 200
    status, body = api.request("GET", "/api/files")
    assert status == 200
    assert "empty" in {entry["path"] for entry in body["tree"]}


def test_move_and_conflict_protection(api):
    status, _ = api.request(
        "POST", "/api/rename", {"from": "project.md", "to": "archive/project.md"}
    )
    assert status == 200
    assert (api.work / "archive" / "project.md").exists()
    (api.work / "existing.md").write_text("existing")
    status, _ = api.request(
        "POST", "/api/rename", {"from": "archive/project.md", "to": "existing.md"}
    )
    assert status == 409
    assert (api.work / "archive" / "project.md").exists()


def test_delete_is_recoverable_and_hidden(api):
    status, body = api.request("POST", "/api/delete", {"path": "project.md"})
    assert status == 200
    assert (api.work / body["trashed"]).exists()
    status, tree = api.request("GET", "/api/files")
    assert status == 200
    assert ".trash" not in {entry["path"] for entry in tree["tree"]}


def test_recent_files_order_by_modified(api):
    _set_times(api.work / "project.md", 1_000)
    _set_times(api.work / "daily" / "today.md", 2_000)
    status, body = api.request("GET", "/api/files/recent?sort=modified")
    assert status == 200
    assert [entry["path"] for entry in body["files"]] == [
        "daily/today.md",
        "project.md",
    ]
    assert body["files"][0] == {
        "path": "daily/today.md",
        "name": "today.md",
        "modified": 2_000_000,
        "created": body["files"][0]["created"],
    }


def test_recent_files_order_by_created(api, monkeypatch):
    births = {"project.md": 5.0, "today.md": 1.0}
    real_stat = os.stat

    class Stat:
        def __init__(self, path):
            result = real_stat(path)
            self.st_mtime = result.st_mtime
            self.st_birthtime = births[os.path.basename(path)]

    monkeypatch.setattr(telar_vault.os, "stat", Stat)
    files = telar_vault.recent_files(api.work, "created", 50)
    assert [(entry["path"], entry["created"]) for entry in files] == [
        ("project.md", 5_000),
        ("daily/today.md", 1_000),
    ]


def test_recent_files_created_falls_back_to_modified(api, monkeypatch):
    real_stat = os.stat

    class Stat:
        def __init__(self, path):
            self.st_mtime = real_stat(path).st_mtime

    _set_times(api.work / "project.md", 3_000)
    monkeypatch.setattr(telar_vault.os, "stat", Stat)
    files = telar_vault.recent_files(api.work, "created", 50)
    project = next(entry for entry in files if entry["path"] == "project.md")
    assert project["created"] == project["modified"] == 3_000_000


@pytest.mark.skipif(
    not hasattr(os.stat_result, "st_birthtime"), reason="no birth time on this OS"
)
def test_saving_a_note_keeps_its_creation_time(api):
    note = api.work / "project.md"
    os.utime(note, (1_000, 1_000))  # APFS lowers the birth time to match
    birth = os.stat(note).st_birthtime
    _, current = api.request("GET", "/api/note?path=project.md")
    status, _ = api.request(
        "POST",
        "/api/note",
        {
            "path": "project.md",
            "content": "edited",
            "base_revision": current["revision"],
        },
    )
    assert status == 200
    saved = os.stat(note)
    assert note.read_text() == "edited"
    assert saved.st_birthtime == birth
    assert saved.st_mtime > birth


def test_recent_files_list_only_openable_visible_files(api):
    (api.work / ".obsidian").mkdir()
    (api.work / ".obsidian" / "app.json").write_text("{}")
    (api.work / ".hidden.md").write_text("x")
    (api.work / "links-index.json").write_text("{}")
    (api.work / "scripts" / "__pycache__").mkdir(parents=True)
    (api.work / "scripts" / "__pycache__" / "cli.cpython-312.pyc").write_bytes(b"x")
    (api.work / "scripts" / "cli.py").write_text("x")
    (api.work / "scripts" / "vault").write_text("x")
    status, body = api.request("POST", "/api/delete", {"path": "project.md"})
    assert status == 200
    status, body = api.request("GET", "/api/files/recent?sort=modified")
    assert status == 200
    assert [entry["path"] for entry in body["files"]] == ["daily/today.md"]


def test_recent_files_limit_is_clamped_and_validated(api):
    for index in range(3):
        (api.work / f"extra-{index}.md").write_text("x")
    (api.work / "drawing.excalidraw").write_text("{}")
    (api.work / "image.PNG").write_bytes(b"x")
    status, body = api.request("GET", "/api/files/recent?sort=modified&limit=0")
    assert status == 200
    assert len(body["files"]) == 1
    status, body = api.request("GET", "/api/files/recent?sort=modified&limit=9999")
    assert status == 200
    assert len(body["files"]) == 7
    status, _ = api.request("GET", "/api/files/recent?limit=abc")
    assert status == 400


def test_raw_bytes_and_binary_note_rejection(api):
    payload = b"\x89PNG\r\n\x1a\n"
    (api.work / "image.png").write_bytes(payload)
    assert api.request("GET", "/api/raw?path=image.png") == (200, payload)
    status, _ = api.request("GET", "/api/note?path=image.png")
    assert status == 415


def test_attachment_round_trip(api):
    payload = b"image bytes"
    status, body = api.request(
        "POST",
        "/api/attach",
        {
            "note": "daily/today.md",
            "filename": "image.png",
            "data_b64": base64.b64encode(payload).decode(),
        },
    )
    assert status == 200
    # Default attachment folder is the vault root, like Obsidian; embedded by bare name.
    assert body["embed"] == "image.png"
    assert body["path"] == "image.png"
    assert (api.work / body["path"]).read_bytes() == payload


def test_attached_drawing_keeps_its_compound_extension_on_collision(api):
    body = {
        "note": "project.md",
        "filename": "project 2026-09-28 10.00.00.excalidraw.md",
        "data_b64": base64.b64encode(b"x").decode(),
    }
    _, first = api.request("POST", "/api/attach", body)
    _, second = api.request("POST", "/api/attach", body)
    assert first["embed"] == "project 2026-09-28 10.00.00.excalidraw.md"
    assert second["embed"] == "project 2026-09-28 10.00.00-1.excalidraw.md"


def test_attachment_names_do_not_collide(api):
    def attach(payload: bytes):
        return api.request(
            "POST",
            "/api/attach",
            {
                "note": "daily/today.md",
                "filename": "image.png",
                "data_b64": base64.b64encode(payload).decode(),
            },
        )

    _, first = attach(b"first")
    _, second = attach(b"second")
    assert first["embed"] == "image.png"
    assert second["embed"] == "image-1.png"
    assert (api.work / first["path"]).read_bytes() == b"first"
    assert (api.work / second["path"]).read_bytes() == b"second"


def test_attachment_folder_setting_uses_obsidian_semantics(api):
    cases = {
        "./adjuntos": "daily/adjuntos/a.png",
        ".": "daily/a.png",
        "/": "a.png",
        "assets": "assets/a.png",
    }
    for setting, expected in cases.items():
        assert _save_attachment_folder(api, setting) == setting
        status, body = api.request(
            "POST",
            "/api/attach",
            {
                "note": "daily/today.md",
                "filename": "a.png",
                "data_b64": base64.b64encode(b"x").decode(),
            },
        )
        assert status == 200, setting
        assert body["path"] == expected, setting


def test_attachment_folder_rejects_traversal(api):
    for invalid in ("../outside", "a/../../b", "a\\b", 3):
        assert _save_attachment_folder(api, invalid) == "/"


def test_attachment_folder_is_only_read_from_obsidian_on_import(api):
    obsidian = api.work / ".obsidian"
    obsidian.mkdir(exist_ok=True)
    (obsidian / "app.json").write_text(
        json.dumps({"attachmentFolderPath": "./adjuntos"})
    )
    _, settings = api.request("GET", "/api/settings")
    assert settings["vault_settings"]["files"]["attachment_folder"] == "/"
    _, imported = api.request("POST", "/api/settings/import-obsidian", {})
    assert imported["vault_settings"]["files"]["attachment_folder"] == "./adjuntos"
