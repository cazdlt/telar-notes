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
