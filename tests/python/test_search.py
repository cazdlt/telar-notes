"""Tests for note search endpoints."""


def test_search_contracts(api):
    cases = {
        "title": ("Daily", "daily/today.md"),
        "content": ("needle", "daily/today.md"),
        "tags": ("work", "daily/today.md"),
        "all": ("project", "project.md"),
    }
    for mode, (query, expected) in cases.items():
        status, body = api.request("GET", f"/api/search?q={query}&mode={mode}")
        assert status == 200
        assert expected in {result["path"] for result in body["results"]}, mode


def test_search_all_combines_title_and_content_matches(api):
    (api.work / "alpha.md").write_text("unrelated body\n")
    (api.work / "beta.md").write_text("---\ntitle: Alpha Note\n---\nbody with alpha\n")
    (api.work / "gamma.md").write_text("only body mentions alpha here\n")

    status, body = api.request("GET", "/api/search?q=alpha&mode=all")
    assert status == 200
    by_path = {r["path"]: r for r in body["results"]}
    assert by_path["alpha.md"] == {"path": "alpha.md", "match": "alpha"}
    assert by_path["beta.md"] == {
        "path": "beta.md",
        "match": "Alpha Note",
        "snippet": "title: Alpha Note",
    }
    assert by_path["gamma.md"] == {
        "path": "gamma.md",
        "snippet": "only body mentions alpha here",
    }


def test_tags_endpoint_collects_frontmatter_and_inline_tags(api):
    (api.work / "tagged.md").write_text(
        "---\n"
        "tags: [project/alpha, work]\n"
        "---\n"
        "# Heading Not A Tag\n"
        "- [ ] Ship #urgent and #project/alpha (#backend)\n"
        "See https://example.com#anchor and #1234 and `#code-tag`\n"
        "```python\n"
        "#fenced-tag\n"
        "```\n"
    )

    status, body = api.request("GET", "/api/tags")
    assert status == 200
    by_tag = {entry["tag"]: entry["count"] for entry in body["tags"]}
    assert by_tag["project/alpha"] == 1
    assert by_tag["urgent"] == 1
    assert by_tag["backend"] == 1
    assert by_tag["work"] >= 2
    assert "Heading" not in by_tag
    assert "anchor" not in by_tag
    assert "1234" not in by_tag
    assert "code-tag" not in by_tag
    assert "fenced-tag" not in by_tag

    # Editing the file invalidates its cached entry via stat marker.
    (api.work / "tagged.md").write_text("- [ ] Updated #fresh-tag\n")
    status, body = api.request("GET", "/api/tags")
    assert status == 200
    updated_tags = {entry["tag"] for entry in body["tags"]}
    assert "fresh-tag" in updated_tags
    assert "urgent" not in updated_tags
