"""Tests for section-aware outline parsing, sliced note reads, and surgical patches."""

from __future__ import annotations

import unicodedata
from urllib.parse import quote

from telar.sections import parse_outline


def test_parse_outline_ignores_frontmatter_fences_and_tags():
    content = (
        "---\n"
        "title: Note\n"
        "# not a heading in frontmatter\n"
        "---\n"
        "# Top\n"
        "Intro #tag-not-heading\n"
        "```python\n"
        "# comment inside backtick fence\n"
        "```\n"
        "- item\n"
        "  ~~~markdown\n"
        "  ## heading inside list tilde fence\n"
        "  ~~~\n"
        "## Child A\n"
        "Body A\n"
        "### Grandchild\n"
        "Deep\n"
        "## Child B\n"
        "Body B\n"
    )
    outline = parse_outline(content)
    assert outline == [
        {"level": 1, "text": "Top", "line": 5, "end_line": 19},
        {"level": 2, "text": "Child A", "line": 14, "end_line": 17},
        {"level": 3, "text": "Grandchild", "line": 16, "end_line": 17},
        {"level": 2, "text": "Child B", "line": 18, "end_line": 19},
    ]


def test_outline_endpoint_and_validation(api):
    status, body = api.request("GET", "/api/note/outline?path=daily/today.md")
    assert status == 200
    assert body["path"] == "daily/today.md"
    assert body["revision"]
    assert body["headings"] == [{"level": 1, "text": "Today", "line": 5, "end_line": 7}]

    status, _ = api.request("GET", "/api/note/outline")
    assert status == 400
    status, _ = api.request("GET", "/api/note/outline?path=../secret.md")
    assert status == 403
    status, _ = api.request("GET", "/api/note/outline?path=missing.md")
    assert status == 404
    (api.work / "bin.dat").write_bytes(b"\xff\xfe\x00\x01")
    status, _ = api.request("GET", "/api/note/outline?path=bin.dat")
    assert status == 415


def test_read_section_accents_paths_and_errors(api):
    note = (
        "# Proyecto\n"
        "## Configuración\n"
        "detalle 1\n"
        "## Trabajo\n"
        "### Tareas\n"
        "work task\n"
        "## Personal\n"
        "### Tareas\n"
        "personal task\n"
    )
    (api.work / "structured.md").write_text(note)

    # Accent- and case-insensitive match (also NFD query vs NFC heading)
    nfd_query = quote(unicodedata.normalize("NFD", "configuracion"))
    status, body = api.request(
        "GET", f"/api/note?path=structured.md&section={nfd_query}"
    )
    assert status == 200
    assert body["section"] == "Configuración"
    assert body["start_line"] == 2
    assert body["end_line"] == 3
    assert body["content"] == "## Configuración\ndetalle 1"

    # Ambiguous bare heading -> 409 with candidates
    status, body = api.request("GET", "/api/note?path=structured.md&section=tareas")
    assert status == 409
    assert body["candidates"] == [
        "Proyecto > Trabajo > Tareas",
        "Proyecto > Personal > Tareas",
    ]

    # Disambiguated via Parent > Child
    path_query = quote("Personal > Tareas")
    status, body = api.request(
        "GET", f"/api/note?path=structured.md&section={path_query}"
    )
    assert status == 200
    assert body["section"] == "Tareas"
    assert body["content"] == "### Tareas\npersonal task"

    # Not found -> 404
    status, _ = api.request("GET", "/api/note?path=structured.md&section=Inexistente")
    assert status == 404

    # Cannot combine section with start_line / end_line
    status, _ = api.request(
        "GET", "/api/note?path=structured.md&section=Proyecto&start_line=1"
    )
    assert status == 400


def test_read_lines_and_if_none_match_unchanged(api):
    status, full = api.request("GET", "/api/note?path=daily/today.md")
    assert status == 200
    status, _ = api.request(
        "GET",
        "/api/note?path=daily/today.md",
        headers={"If-None-Match": full["revision"]},
    )
    assert status == 304

    status, sliced = api.request(
        "GET", "/api/note?path=daily/today.md&start_line=5&end_line=6"
    )
    assert status == 200
    assert sliced["start_line"] == 5
    assert sliced["end_line"] == 6
    assert sliced["content"] == "# Today\nneedle"

    status, _ = api.request("GET", "/api/note?path=daily/today.md&start_line=0")
    assert status == 400
    status, _ = api.request(
        "GET", "/api/note?path=daily/today.md&start_line=5&end_line=2"
    )
    assert status == 400


def test_patch_insert_all_anchors_and_start_of_file_frontmatter(api):
    initial = "---\ntitle: Demo\n---\n# First\nalpha\n## Sub\nbeta\n# Second\ngamma\n"
    (api.work / "patch.md").write_text(initial)

    # start_of_file inserts after frontmatter
    status, body = api.request(
        "POST",
        "/api/note/patch",
        {
            "path": "patch.md",
            "op": "insert",
            "anchor": "start_of_file",
            "content": "preamble",
        },
    )
    assert status == 200
    assert (
        "---\ntitle: Demo\n---\npreamble\n# First\n"
        in (api.work / "patch.md").read_text()
    )
    assert "--- a/patch.md" in body["diff"]
    assert "+++ b/patch.md" in body["diff"]

    # after_heading
    status, _ = api.request(
        "POST",
        "/api/note/patch",
        {
            "path": "patch.md",
            "op": "insert",
            "anchor": "after_heading",
            "heading": "First",
            "content": "right after first",
        },
    )
    assert status == 200
    assert "# First\nright after first\nalpha\n" in (api.work / "patch.md").read_text()

    # end_of_section (includes Sub under First)
    status, _ = api.request(
        "POST",
        "/api/note/patch",
        {
            "path": "patch.md",
            "op": "insert",
            "anchor": "end_of_section",
            "heading": "First",
            "content": "end of first",
        },
    )
    assert status == 200
    assert "beta\nend of first\n# Second\n" in (api.work / "patch.md").read_text()

    # before_heading
    status, _ = api.request(
        "POST",
        "/api/note/patch",
        {
            "path": "patch.md",
            "op": "insert",
            "anchor": "before_heading",
            "heading": "Second",
            "content": "before second",
        },
    )
    assert status == 200
    assert "before second\n# Second\n" in (api.work / "patch.md").read_text()

    # end_of_file (default anchor)
    status, _ = api.request(
        "POST",
        "/api/note/patch",
        {"path": "patch.md", "op": "insert", "content": "tail"},
    )
    assert status == 200
    assert (api.work / "patch.md").read_text().endswith("gamma\ntail\n")

    # start_of_file without frontmatter inserts at line 1
    (api.work / "plain.md").write_text("# Heading\nbody\n")
    status, _ = api.request(
        "POST",
        "/api/note/patch",
        {
            "path": "plain.md",
            "op": "insert",
            "anchor": "start_of_file",
            "content": "top",
        },
    )
    assert status == 200
    assert (api.work / "plain.md").read_text() == "top\n# Heading\nbody\n"


def test_patch_replace_section_and_replace_text(api):
    (api.work / "doc.md").write_text(
        "# One\nold 1\n## Nested\nnested old\n# Two\nkeep two\n"
    )

    status, _ = api.request(
        "POST",
        "/api/note/patch",
        {
            "path": "doc.md",
            "op": "replace_section",
            "heading": "One",
            "content": "new body",
        },
    )
    assert status == 200
    assert (api.work / "doc.md").read_text() == "# One\nnew body\n# Two\nkeep two\n"

    # replace_text 404
    status, _ = api.request(
        "POST",
        "/api/note/patch",
        {"path": "doc.md", "op": "replace_text", "old": "absent", "new": "x"},
    )
    assert status == 404

    # replace_text 409 with count
    (api.work / "dup.md").write_text("repeat\nrepeat\n")
    status, body = api.request(
        "POST",
        "/api/note/patch",
        {"path": "dup.md", "op": "replace_text", "old": "repeat", "new": "once"},
    )
    assert status == 409
    assert body["count"] == 2

    # replace_text success
    status, _ = api.request(
        "POST",
        "/api/note/patch",
        {"path": "doc.md", "op": "replace_text", "old": "keep two", "new": "kept"},
    )
    assert status == 200
    assert (api.work / "doc.md").read_text() == "# One\nnew body\n# Two\nkept\n"


def test_patch_concurrency_dry_run_traversal_and_links_index(api):
    _, note = api.request("GET", "/api/note?path=daily/today.md")
    rev = note["revision"]

    # dry_run returns diff without touching disk
    status, dry = api.request(
        "POST",
        "/api/note/patch",
        {
            "path": "daily/today.md",
            "base_revision": rev,
            "dry_run": True,
            "op": "insert",
            "content": "[[new-target]]",
        },
    )
    assert status == 200
    assert dry["dry_run"] is True
    assert dry["revision"] == rev
    assert "+[[new-target]]" in dry["diff"]
    assert "[[new-target]]" not in (api.work / "daily" / "today.md").read_text()

    # stale base_revision -> 409 with current revision
    status, conflict = api.request(
        "POST",
        "/api/note/patch",
        {
            "path": "daily/today.md",
            "base_revision": "stale-rev",
            "op": "insert",
            "content": "x",
        },
    )
    assert status == 409
    assert conflict["revision"] == rev

    # path traversal rejected
    status, _ = api.request(
        "POST",
        "/api/note/patch",
        {"path": "../outside.md", "op": "insert", "content": "x"},
    )
    assert status == 403

    # real patch updates links index
    (api.work / "new-target.md").write_text("# Target\n")
    status, patched = api.request(
        "POST",
        "/api/note/patch",
        {
            "path": "daily/today.md",
            "base_revision": rev,
            "op": "insert",
            "content": "[[new-target]]",
        },
    )
    assert status == 200
    assert patched["revision"] != rev
    status, links = api.request("GET", "/api/links")
    assert status == 200
    assert "daily/today.md" in links["new-target.md"]["linked_from"]
