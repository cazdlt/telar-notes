"""Tests for wikilinks, backlinks, link index storage, and link resolution."""

import json

from telar.links import build_links_index, links_index_path


def test_links_and_backlinks_are_symmetric(api):
    status, index = api.request("GET", "/api/links")
    assert status == 200
    assert "project.md" in index["daily/today.md"]["links_to"]
    assert "daily/today.md" in index["project.md"]["linked_from"]
    assert links_index_path(api.work).exists()
    assert not (api.work / "links-index.json").exists()


def test_links_rebuild_picks_up_external_edits(api):
    api.request("GET", "/api/links")
    (api.work / "daily/today.md").write_text("no links anymore")

    status, stale = api.request("GET", "/api/links")
    assert status == 200
    assert "project.md" in stale["daily/today.md"]["links_to"]

    status, index = api.request("POST", "/api/links/rebuild", {})
    assert status == 200
    assert index["daily/today.md"]["links_to"] == []
    assert "daily/today.md" not in index["project.md"]["linked_from"]
    assert not (api.work / "links-index.json").exists()
    status, again = api.request("GET", "/api/links")
    assert again == index


def test_hidden_folders_are_not_indexed_or_searched(api):
    for rel in (".trash/old.md", ".venv/pkg/README.md"):
        (api.work / rel).parent.mkdir(parents=True, exist_ok=True)
        (api.work / rel).write_text("hiddenword [[project]]")
    idx_path = links_index_path(api.work)
    idx_path.parent.mkdir(parents=True, exist_ok=True)
    idx_path.write_text(
        json.dumps({".trash/old.md": {"links_to": ["project.md"], "linked_from": []}})
    )

    status, index = api.request("GET", "/api/links")
    assert status == 200
    assert not any(path.startswith(".") for path in index)
    assert not any(src.startswith(".") for src in index["project.md"]["linked_from"])
    for mode in ("title", "content", "all"):
        query = "old" if mode == "title" else "hiddenword"
        status, body = api.request("GET", f"/api/search?q={query}&mode={mode}")
        assert status == 200
        assert body["results"] == []


def test_links_ignore_escaped_table_pipe(api):
    status, _ = api.request(
        "POST",
        "/api/note",
        {"path": "table.md", "content": "| who |\n| --- |\n| [[project\\|Proj]] |\n"},
    )
    assert status == 200

    status, index = api.request("GET", "/api/links")
    assert status == 200
    assert index["table.md"]["links_to"] == ["project.md"]
    assert "table.md" in index["project.md"]["linked_from"]


def test_links_resolve_obsidian_short_paths(api):
    people = api.work / "teams" / "people"
    people.mkdir(parents=True)
    (people / "Eve.md").write_text("# Eve\n")
    (api.work / "daily" / "today.md").write_text("# Today\n[[Eve]]\n")

    status, index = api.request("GET", "/api/links")

    assert status == 200
    assert index["daily/today.md"]["links_to"] == ["teams/people/Eve.md"]
    assert index["teams/people/Eve.md"]["linked_from"] == ["daily/today.md"]


def test_links_resolve_equivalent_unicode_compositions(api):
    people = api.work / "teams" / "people"
    people.mkdir(parents=True)
    decomposed = "Omar Castan\u0303o.md"
    (people / decomposed).write_text("# Omar Castaño\n")
    (api.work / "daily" / "today.md").write_text("# Today\n[[Omar Castaño|Omar]]\n")

    status, index = api.request("GET", "/api/links")

    resolved = f"teams/people/{decomposed}"
    assert status == 200
    assert index["daily/today.md"]["links_to"] == [resolved]
    assert index[resolved]["linked_from"] == ["daily/today.md"]

    (people / "team.md").write_text("# Team\n[[Omar Castaño]]\n")
    links_index_path(api.work).unlink()
    status, index = api.request("GET", "/api/links")

    assert status == 200
    assert index["teams/people/team.md"]["links_to"] == [resolved]
    assert "teams/people/Omar Castaño.md" not in index


def test_stale_unicode_alias_in_links_cache_is_rebuilt(api):
    people = api.work / "teams" / "people"
    people.mkdir(parents=True)
    decomposed = "Pablo Garci\u0301a.md"
    actual = f"teams/people/{decomposed}"
    (people / decomposed).write_text("# Pablo García\n")
    (api.work / "daily" / "today.md").write_text("# Today\n[[Pablo García]]\n")
    idx_path = links_index_path(api.work)
    idx_path.parent.mkdir(parents=True, exist_ok=True)
    idx_path.write_text(
        json.dumps(
            {
                "daily/today.md": {
                    "links_to": ["Pablo García.md"],
                    "linked_from": [],
                },
                "project.md": {"links_to": [], "linked_from": []},
                actual: {"links_to": [], "linked_from": []},
                "Pablo García.md": {
                    "links_to": [],
                    "linked_from": ["daily/today.md"],
                },
            }
        )
    )

    status, index = api.request("GET", "/api/links")

    assert status == 200
    assert index["daily/today.md"]["links_to"] == [actual]
    assert "Pablo García.md" not in index


def test_partial_links_cache_is_rebuilt(api):
    idx_path = links_index_path(api.work)
    idx_path.parent.mkdir(parents=True, exist_ok=True)
    idx_path.write_text(
        json.dumps({"daily/today.md": {"links_to": [], "linked_from": []}})
    )

    status, index = api.request("GET", "/api/links")

    assert status == 200
    assert "project.md" in index
    assert index["project.md"]["linked_from"] == ["daily/today.md"]


def test_save_updates_backlinks_incrementally(api):
    api.request("GET", "/api/links")
    _, note = api.request("GET", "/api/note?path=daily/today.md")
    status, _ = api.request(
        "POST",
        "/api/note",
        {
            "path": "daily/today.md",
            "content": "# Today\n[[new-target]]\n",
            "base_revision": note["revision"],
        },
    )
    assert status == 200
    assert not (api.work / "links-index.json").exists()
    status, results = api.request("GET", "/api/search?q=new-target&mode=links")
    assert status == 200
    assert results["results"] == [
        {"path": "daily/today.md", "direction": "linked_from"}
    ]


def test_code_and_drawings_do_not_pollute_index(tmp_path):
    (tmp_path / "note.md").write_text("[[real]] `[[inline]]`\n```\n[[fenced]]\n```\n")
    (tmp_path / "drawing.excalidraw.md").write_text("[[ignored]]")

    index = build_links_index(tmp_path)

    assert index["note.md"]["links_to"] == ["real.md"]
    assert "drawing.excalidraw.md" not in index


def test_embeds_count_as_links(tmp_path):
    (tmp_path / "B.md").write_text("- task ^some-block-id\n")
    (tmp_path / "A.md").write_text(
        "- ![[B#^some-block-id]]\n![[embed]]\n![[photo.png]]\n`![[inline]]`\n"
    )

    index = build_links_index(tmp_path)

    assert index["A.md"]["links_to"] == ["B.md", "embed.md", "photo.png"]
    assert index["B.md"]["linked_from"] == ["A.md"]


def test_self_links_are_not_indexed(tmp_path):
    (tmp_path / "A.md").write_text("- ![[A#^own-block]] [[A]]\n- task ^own-block\n")

    index = build_links_index(tmp_path)

    assert index["A.md"]["links_to"] == []
    assert index["A.md"]["linked_from"] == []


def test_empty_catalog_is_not_rebuilt(tmp_path, monkeypatch):
    from telar import links

    (tmp_path / "note.md").write_text("hello\n")

    def fail_build(_vault):
        raise AssertionError("build_link_catalog should not be called")

    monkeypatch.setattr(links, "build_link_catalog", fail_build)
    assert (
        links.resolve_link(tmp_path, "note.md", "missing", catalog={}) == "missing.md"
    )
    assert links.extract_targets(tmp_path, "note.md", "[[missing]]", catalog={}) == [
        "missing.md"
    ]
