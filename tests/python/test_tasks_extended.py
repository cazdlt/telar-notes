"""Tests for extended Tasks HTTP API: /api/tasks/add and flexible /api/tasks/update."""

from __future__ import annotations

import pytest


def test_tasks_add_canonical_order_priority_dates_tags_block_id(api):
    note = api.work / "project.md"
    note.write_text("# Project\n")

    status, res = api.request(
        "POST",
        "/api/tasks/add",
        {
            "path": "project.md",
            "status": "/",
            "description": "Ship API",
            "tags": ["work", "#api"],
            "priority": "high",
            "dates": {"due": "2026-12-01", "scheduled": "2026-11-25"},
            "block_id": "ship-api",
        },
    )
    assert status == 200
    assert res["ok"] is True
    assert res["embed"] == "![[project#^ship-api]]"
    assert res["task"]["block_id"] == "ship-api"
    assert res["task"]["priority"] == "⏫"
    assert res["task"]["tags"] == ["work", "api"]
    assert res["task"]["dates"] == {"due": "2026-12-01", "scheduled": "2026-11-25"}
    assert "--- a/project.md" in res["diff"]
    assert "+++ b/project.md" in res["diff"]
    assert (
        note.read_text().splitlines()[-1]
        == "- [/] Ship API #work #api ⏫ 📅 2026-12-01 ⏳ 2026-11-25 ^ship-api"
    )

    # Duplicate block_id in same file -> 409
    status, _ = api.request(
        "POST",
        "/api/tasks/add",
        {"path": "project.md", "description": "Another", "block_id": "ship-api"},
    )
    assert status == 409


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("highest", "🔺"),
        ("high", "⏫"),
        ("medium", "🔼"),
        ("low", "🔽"),
        ("lowest", "⏬"),
        ("🔺", "🔺"),
        ("⏫", "⏫"),
        ("🔼", "🔼"),
        ("🔽", "🔽"),
        ("⏬", "⏬"),
    ],
)
def test_tasks_add_accepts_priority_names_and_emojis(api, raw, expected):
    note = api.work / "project.md"
    note.write_text("# Project\n")
    status, res = api.request(
        "POST",
        "/api/tasks/add",
        {"path": "project.md", "description": "Item", "priority": raw},
    )
    assert status == 200
    assert res["task"]["priority"] == expected


def test_tasks_add_children_and_section_anchors(api):
    note = api.work / "notes.md"
    note.write_text(
        "---\n"
        "title: # FakeHeading\n"
        "---\n"
        "```markdown\n"
        "# Fenced\n"
        "```\n"
        "# Planificación\n"
        "## Tareas\n"
        "- [ ] Existing\n\n"
        "# Otros\n"
    )

    # Case/accent-insensitive NFC fold + Parent > Child + end_of_section default
    status, _ = api.request(
        "POST",
        "/api/tasks/add",
        {
            "path": "notes.md",
            "description": "Child task",
            "heading": "planificacion > tareas",
            "children": ["- [ ] Sub 1", "Note line"],
        },
    )
    assert status == 200

    # after_heading & before_heading
    status, _ = api.request(
        "POST",
        "/api/tasks/add",
        {
            "path": "notes.md",
            "description": "Top of otros",
            "heading": "OTROS",
            "anchor": "after_heading",
        },
    )
    assert status == 200
    status, _ = api.request(
        "POST",
        "/api/tasks/add",
        {
            "path": "notes.md",
            "description": "Before otros",
            "heading": "Otros",
            "anchor": "before_heading",
        },
    )
    assert status == 200

    lines = note.read_text().splitlines()
    assert lines == [
        "---",
        "title: # FakeHeading",
        "---",
        "```markdown",
        "# Fenced",
        "```",
        "# Planificación",
        "## Tareas",
        "- [ ] Existing",
        "- [ ] Child task",
        "  - [ ] Sub 1",
        "  Note line",
        "",
        "- [ ] Before otros",
        "# Otros",
        "- [ ] Top of otros",
    ]

    # Heading inside code fence should not match
    status, _ = api.request(
        "POST",
        "/api/tasks/add",
        {"path": "notes.md", "description": "Nope", "heading": "Fenced"},
    )
    assert status == 404


def test_tasks_add_dry_run_and_validation_errors(api):
    note = api.work / "project.md"
    original = "# Project\n"
    note.write_text(original)

    status, res = api.request(
        "POST",
        "/api/tasks/add",
        {
            "path": "project.md",
            "description": "Preview only",
            "block_id": "preview-only",
            "dry_run": True,
        },
    )
    assert status == 200
    assert res["dry_run"] is True
    assert res["embed"] == "![[project#^preview-only]]"
    assert "+- [ ] Preview only ^preview-only" in res["diff"]
    assert note.read_text() == original

    # Path traversal -> 403
    status, _ = api.request(
        "POST",
        "/api/tasks/add",
        {"path": "../outside.md", "description": "Escape"},
    )
    assert status == 403

    # Missing file -> 404
    status, _ = api.request(
        "POST",
        "/api/tasks/add",
        {"path": "missing.md", "description": "Missing"},
    )
    assert status == 404

    # Empty description -> 400
    status, _ = api.request(
        "POST",
        "/api/tasks/add",
        {"path": "project.md", "description": "   "},
    )
    assert status == 400


def test_tasks_update_flexible_locations(api):
    note = api.work / "project.md"
    note.write_text(
        "# Project\n"
        "- [ ] Alpha task ^alpha-id\n"
        "- [ ] Beta one\n"
        "- [ ] Beta two\n"
        "Plain paragraph\n"
    )

    # Locate by block_id
    status, res = api.request(
        "POST",
        "/api/tasks/update",
        {
            "location": {"path": "project.md", "block_id": "alpha-id"},
            "patch": {"status": "x"},
        },
    )
    assert status == 200
    assert res["old_status"] == " "
    assert "+- [x] Alpha task" in res["diff"]
    assert "^alpha-id" in res["diff"]

    # Missing block_id -> 404
    status, _ = api.request(
        "POST",
        "/api/tasks/update",
        {
            "location": {"path": "project.md", "block_id": "missing"},
            "patch": {"status": "x"},
        },
    )
    assert status == 404

    # Locate by unique match (case-insensitive)
    status, _ = api.request(
        "POST",
        "/api/tasks/update",
        {
            "location": {"path": "project.md", "match": "beta ONE"},
            "patch": {"status": "/"},
        },
    )
    assert status == 200
    assert "- [/] Beta one" in note.read_text()

    # Non-unique match -> 409, no match -> 404
    status, _ = api.request(
        "POST",
        "/api/tasks/update",
        {"location": {"path": "project.md", "match": "beta"}, "patch": {"status": "x"}},
    )
    assert status == 409
    status, _ = api.request(
        "POST",
        "/api/tasks/update",
        {
            "location": {"path": "project.md", "match": "gamma"},
            "patch": {"status": "x"},
        },
    )
    assert status == 404

    # Locate by line-only
    status, _ = api.request(
        "POST",
        "/api/tasks/update",
        {"location": {"path": "project.md", "line": 4}, "patch": {"status": "x"}},
    )
    assert status == 200
    assert "- [x] Beta two" in note.read_text()

    # Line out of range or non-task line -> 409
    status, _ = api.request(
        "POST",
        "/api/tasks/update",
        {"location": {"path": "project.md", "line": 5}, "patch": {"status": "x"}},
    )
    assert status == 409
    status, _ = api.request(
        "POST",
        "/api/tasks/update",
        {"location": {"path": "project.md", "line": 99}, "patch": {"status": "x"}},
    )
    assert status == 409


def test_tasks_update_extended_patch_fields_and_dry_run(api):
    note = api.work / "project.md"
    note.write_text(
        "- [ ] Old desc 🔁 every day 🆔 abc 🔼 📅 2026-10-10 ^keep-me\n"
        "- [ ] Second task\n"
        "  - existing child\n"
        "- [ ] Third task ^taken\n"
    )

    # Patch description + priority by name + clear priority + preserve metadata & block_id
    status, _ = api.request(
        "POST",
        "/api/tasks/update",
        {
            "location": {"path": "project.md", "block_id": "keep-me"},
            "patch": {
                "description": "New desc",
                "priority": "highest",
                "block_id": "ignored-new-id",
            },
        },
    )
    assert status == 200
    assert (
        note.read_text().splitlines()[0]
        == "- [ ] New desc 🔁 every day 🆔 abc 📅 2026-10-10 🔺 ^keep-me"
    )

    # Clear priority with ""
    status, _ = api.request(
        "POST",
        "/api/tasks/update",
        {
            "location": {"path": "project.md", "block_id": "keep-me"},
            "patch": {"priority": ""},
        },
    )
    assert status == 200
    assert "🔺" not in note.read_text().splitlines()[0]

    # Set block_id when absent, reject 409 when taken
    status, _ = api.request(
        "POST",
        "/api/tasks/update",
        {
            "location": {"path": "project.md", "match": "Second task"},
            "patch": {"block_id": "taken"},
        },
    )
    assert status == 409

    # append_children preserving existing children + set block_id
    status, _ = api.request(
        "POST",
        "/api/tasks/update",
        {
            "location": {"path": "project.md", "match": "Second task"},
            "patch": {
                "block_id": "second-id",
                "append_children": ["- added child"],
            },
        },
    )
    assert status == 200
    lines = note.read_text().splitlines()
    assert lines[1] == "- [ ] Second task ^second-id"
    assert lines[2] == "  - existing child"
    assert lines[3] == "  - added child"

    # dry_run does not mutate file
    before = note.read_text()
    status, res = api.request(
        "POST",
        "/api/tasks/update",
        {
            "location": {"path": "project.md", "block_id": "second-id"},
            "patch": {"status": "x"},
            "dry_run": True,
        },
    )
    assert status == 200
    assert res["dry_run"] is True
    assert res["old_status"] == " "
    assert "+- [x] Second task" in res["diff"]
    assert "^second-id" in res["diff"]
    assert note.read_text() == before

    # Backward compatibility with expected -> 409 when stale
    status, _ = api.request(
        "POST",
        "/api/tasks/update",
        {
            "location": {"path": "project.md", "line": 2, "expected": "- [ ] Wrong"},
            "patch": {"status": "x"},
        },
    )
    assert status == 409
