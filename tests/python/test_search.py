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
