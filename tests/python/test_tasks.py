"""Tests for task parsing, query DSL, recurrence, and block IDs."""

import datetime
from urllib.parse import quote

import pytest

from telar import task_query, tasks


def test_tasks_parse_query_and_compare_and_swap(api):
    path = api.work / "daily" / "today.md"
    path.write_text("# Tasks\n- [ ] First #work 📅 2026-08-15\n- [?] Ask\n")
    status, result = api.request("GET", "/api/tasks?query=status%20is%20%3F")
    assert status == 200
    assert result["tasks"][0]["description"] == "Ask"
    status, result = api.request("GET", "/api/tasks?query=not%20done")
    task = next(
        item for item in result["tasks"] if item["description"].startswith("First")
    )
    status, _ = api.request(
        "POST",
        "/api/tasks/update",
        {"location": task["location"], "patch": {"status": "x"}},
    )
    assert status == 200
    assert "[x] First" in path.read_text()
    status, _ = api.request(
        "POST",
        "/api/tasks/update",
        {"location": task["location"], "patch": {"status": " "}},
    )
    assert status == 409


def test_daily_template_task_filters_groups_and_context(api):
    task_file = api.work / "work" / "acme" / "LLMs" / "tasks.md"
    task_file.parent.mkdir(parents=True)
    task_file.write_text(
        "# Work\n"
        "- [ ] ➕ 2026-08-14\n"
        "- [I] Idea\n"
        "- [?] Ask\n"
        "- [>] Delegate [[people/Ada]]\n"
        "- [/] Cooking ⏳ 2000-01-01\n"
        "- [ ] Recurring 📅 2999-01-01 🔁 every day when done\n"
        "- [ ] Future 📅 2999-01-01\n"
        "- [x] Done ✅ 2026-08-14\n"
    )
    tasks._TASK_INDEX_CACHE.clear()

    def run_query(query, source=None):
        path = f"/api/tasks?query={quote(query, safe='')}"
        if source:
            path += f"&source={quote(source, safe='')}"
        status, result = api.request("GET", path)
        assert status == 200
        return result

    result = run_query("description regex does not match /^$/")
    assert result["errors"] == []
    assert all(task["description"] for task in result["tasks"])
    assert next(task for task in result["tasks"] if task["description"] == "Idea")[
        "status"
    ] == {"symbol": "I", "name": "idea", "type": "TODO"}
    assert (
        next(task for task in result["tasks"] if task["description"] == "Recurring")[
            "recurrence"
        ]
        == "every day when done"
    )

    result = run_query(
        "not done\n"
        "filter by function task.status.name !== 'idea' && task.status.symbol !== '?' && task.status.symbol !== '>' && task.status.symbol !== '<'\n"
        "description regex does not match /^$/"
    )
    assert {task["description"] for task in result["tasks"]} == {
        "Cooking",
        "Recurring",
        "Future",
    }

    result = run_query(
        "not done\n"
        "group by root reverse\n"
        "group by function task.file.folder.slice(0, -1).split('/')[2] + \"/\"\n"
        "group by function '[[' + task.file.path.slice(0, -3) + '|' + task.file.folder.slice(0, -1).split('/').pop() + '/' + task.file.filename.slice(0, -3) + ']]'\n"
        "group by heading\n"
        "sort by priority"
    )
    grouped = next(task for task in result["tasks"] if task["description"] == "Cooking")
    assert result["errors"] == []
    assert grouped["groups"] == [
        "work",
        "LLMs/",
        "[[work/acme/LLMs/tasks|LLMs/tasks]]",
        "Work",
    ]

    result = run_query(
        "filter by function task.status.symbol === '>'\n"
        "group by function const m = task.description.match(/\\[\\[([^\\]|#]+)/); return m ? '[[' + m[1].trim() + ']]' : 'Sin persona';\n"
        "group by function '[[' + task.file.path.slice(0, -3) + '|' + task.file.filename.slice(0, -3) + ']]'"
    )
    assert result["errors"] == []
    assert result["tasks"][0]["groups"] == [
        "[[people/Ada]]",
        "[[work/acme/LLMs/tasks|tasks]]",
    ]

    result = run_query(
        "description regex does not match /^$/\n"
        "group by function task.isRecurring?'%%1%%Diarias':((task.happens.moment?.isBefore(moment(), 'day') && task.status.type != 'IN_PROGRESS') || false)?'%%3%%Pendiente':'%%2%%En progreso'"
    )
    assert result["errors"] == []
    assert next(task for task in result["tasks"] if task["description"] == "Recurring")[
        "groups"
    ] == ["Diarias"]

    result = run_query(
        "done on {{query.file.filenameWithoutExtension}}",
        "diario/2026/08/2026-08-14.md",
    )
    assert [task["description"] for task in result["tasks"]] == ["Done"]

    result = run_query(
        "filter by function task.status.symbol !== '?' || window.location"
    )
    assert result == {
        "tasks": [],
        "errors": [
            "Unsupported instruction: filter by function task.status.symbol !== '?' || window.location "
            "(only allowlisted functions are evaluated)"
        ],
    }


def test_person_groups_match_their_javascript_regex():
    task = {"description": "review ![[diagram.png]] with [[ Ada |Ada L.]]"}
    today = datetime.date(2026, 10, 9)
    with_embeds, _ = task_query.compile_group(task_query._PERSON_GROUP, today)
    without_embeds, _ = task_query.compile_group(
        task_query._PERSON_NO_EMBED_GROUP, today
    )

    assert with_embeds(task)[1] == "[[diagram.png]]"
    assert without_embeds(task)[1] == "[[Ada]]"
    assert without_embeds({"description": "no links"})[1] == "Sin persona"


def test_tasks_query_supports_vault_filters_groups_and_sorts(api):
    person = api.work / "people" / "Ada.md"
    person.parent.mkdir()
    person.write_text(
        "# Ada\n"
        "- [ ] Ask [[Ada]] about CPT 🔼\n"
        "\t- [ ] Nested for [[Ada]]\n"
        "- [x] Reviewed with [[Ada]] ✅ 2026-08-10\n"
        "- [ ] Unrelated 📅 2026-08-12 🔺\n"
        "- [-] Dropped [[Ada]] ❌ 2026-08-11\n"
        "- [I] Idea\n"
    )
    tasks._TASK_INDEX_CACHE.clear()

    def run_query(query, source="people/Ada.md"):
        status, result = api.request(
            "GET",
            f"/api/tasks?query={quote(query, safe='')}&source={quote(source, safe='')}",
        )
        assert status == 200
        return result

    def descriptions(result):
        return [task["description"] for task in result["tasks"]]

    result = run_query(
        "not done\n"
        "description includes [[{{query.file.filenameWithoutExtension}}\n"
        "exclude sub-items\n"
        "# hide edit button\n"
        "hide toolbar"
    )
    assert result["errors"] == []
    assert descriptions(result) == ["Ask [[Ada]] about CPT"]

    result = run_query("done\ndescription includes [[Ada\nsort by done reverse")
    assert descriptions(result) == ["Dropped [[Ada]]", "Reviewed with [[Ada]]"]

    result = run_query(
        "(happens in 2026-W33) OR (status.type is CANCELLED)\n"
        "path does not include diario/"
    )
    assert descriptions(result) == ["Unrelated", "Dropped [[Ada]]"]

    result = run_query("not done\nNOT (status is I)\nsort by priority\nlimit 2")
    assert descriptions(result) == ["Unrelated", "Ask [[Ada]] about CPT"]

    result = run_query(
        "path includes people/\n"
        "group by filename\n"
        "group by status.type reverse\n"
        "group by happens"
    )
    assert result["errors"] == []
    unrelated = next(
        task for task in result["tasks"] if task["description"] == "Unrelated"
    )
    assert unrelated["groups"] == ["[[people/Ada|Ada]]", "TODO", "2026-08-12 Wednesday"]
    assert descriptions(result)[0] == "Dropped [[Ada]]"

    result = run_query(
        "not done\n"
        "group by function task.isRecurring?'%%3%%Diarias':(task.happens.moment?.isBefore(moment(), 'day') || false)?'%%1%%Pendiente':'%%2%%En progreso'"
    )
    assert result["errors"] == []
    assert result["tasks"][0]["description"] == "Unrelated"
    assert result["tasks"][0]["groups"] == ["Pendiente"]

    result = run_query("description includes [[{{query.file.filename}}", source="")
    assert result == {
        "tasks": [],
        "errors": [
            "Unsupported instruction: description includes [[{{query.file.filename}} "
            "(placeholders need a source note)"
        ],
    }

    result = run_query("not done\npriority is urgent\ngroup by tags")
    assert result["tasks"] == []
    assert len(result["errors"]) == 2


def test_tasks_accept_every_known_status_symbol(api):
    path = api.work / "statuses.md"
    path.write_text(
        "".join(
            f"- [{symbol}] Task {index}\n"
            for index, symbol in enumerate(tasks.TASK_STATUSES)
        )
    )
    tasks._TASK_INDEX_CACHE.clear()
    status, result = api.request(
        "GET", f"/api/tasks?query={quote('path includes statuses', safe='')}"
    )
    assert status == 200
    assert [task["status"]["symbol"] for task in result["tasks"]] == list(
        tasks.TASK_STATUSES
    )
    question = next(task for task in result["tasks"] if task["status"]["symbol"] == "?")
    status, _ = api.request(
        "POST",
        "/api/tasks/update",
        {"location": question["location"], "patch": {"status": "!"}},
    )
    assert status == 200
    assert "- [!] Task 6" in path.read_text()


def test_task_block_id_survives_status_updates_and_resolves(api):
    path = api.work / "project.md"
    path.write_text("# Project\n- [ ] Ship report 📅 2026-10-10 ^ship-report\n")
    status, result = api.request(
        "GET", "/api/tasks/block?path=project.md&id=ship-report"
    )
    assert status == 200
    task = result["task"]
    assert task["block_id"] == "ship-report"
    assert task["description"] == "Ship report"
    status, _ = api.request(
        "POST",
        "/api/tasks/update",
        {"location": task["location"], "patch": {"status": "x", "done": "2026-10-11"}},
    )
    assert status == 200
    assert path.read_text().splitlines()[1] == (
        "- [x] Ship report 📅 2026-10-10 ✅ 2026-10-11 ^ship-report"
    )
    status, _ = api.request("GET", "/api/tasks/block?path=project.md&id=missing")
    assert status == 404
    status, _ = api.request("GET", "/api/tasks/block?path=../x.md&id=ship-report")
    assert status == 403


def test_recurring_task_copy_does_not_duplicate_block_id(api):
    path = api.work / "project.md"
    path.write_text("- [ ] Water 🔁 every day 📅 2026-10-10 ^water\n")
    status, result = api.request("GET", "/api/tasks/block?path=project.md&id=water")
    status, _ = api.request(
        "POST",
        "/api/tasks/update",
        {"location": result["task"]["location"], "patch": {"status": "x"}},
    )
    assert status == 200
    assert path.read_text().count("^water") == 1


def test_task_block_id_is_created_once_with_a_unique_readable_slug(api):
    path = api.work / "project.md"
    path.write_text(
        "- [ ] Revisar la generación v3 de [[Alice Smith|Alice]] 📅 2026-10-09\n"
        "- [ ] Other ^revisar-generacion-v3-alice\n"
    )
    location = {
        "path": "project.md",
        "line": 1,
        "expected": path.read_text().splitlines()[0],
    }
    status, result = api.request("POST", "/api/tasks/block-id", {"location": location})
    assert status == 200
    assert result["id"] == "revisar-generacion-v3-alice-2"
    first = path.read_text().splitlines()[0]
    assert first.endswith("📅 2026-10-09 ^revisar-generacion-v3-alice-2")
    location["expected"] = first
    status, again = api.request("POST", "/api/tasks/block-id", {"location": location})
    assert status == 200
    assert again["id"] == result["id"]
    assert path.read_text().count("^revisar-generacion-v3-alice-2") == 1
    status, _ = api.request(
        "POST",
        "/api/tasks/block-id",
        {"location": {"path": "project.md", "line": 1, "expected": "stale"}},
    )
    assert status == 409


def test_next_recurrence_rules():
    assert tasks.next_recurrence("every day", "2026-12-31") == "2027-01-01"
    assert tasks.next_recurrence("  Cada Día  ", "2026-10-09") == "2026-10-10"
    assert tasks.next_recurrence("every weekday", "2026-10-08") == "2026-10-09"
    assert tasks.next_recurrence("weekdays", "2026-10-09") == "2026-10-12"
    assert tasks.next_recurrence("cada día laborable", "2026-10-10") == "2026-10-12"
    assert tasks.next_recurrence("every week on friday", "2026-10-09") == "2026-10-16"
    assert tasks.next_recurrence("cada monday", "2026-10-09") == "2026-10-12"
    assert tasks.next_recurrence("monthly", "2026-12-15") == "2027-01-15"
    assert tasks.next_recurrence("every month", "2026-01-31") == "2026-02-28"
    assert tasks.next_recurrence("cada mes", "2024-01-31") == "2024-02-29"
    for unsupported in ("every year", "yearly", "every week", "every monday", "bogus"):
        assert tasks.next_recurrence(unsupported, "2026-10-09") is None
    with pytest.raises(ValueError):
        tasks.next_recurrence("every day", "not-a-date")


def test_date_range_resolves_relative_and_explicit_ranges():
    friday = datetime.date(2026, 10, 9)
    cases = {
        "yesterday": ("2026-10-08", "2026-10-08"),
        "  TODAY ": ("2026-10-09", "2026-10-09"),
        "tomorrow": ("2026-10-10", "2026-10-10"),
        "last week": ("2026-09-28", "2026-10-04"),
        "this week": ("2026-10-05", "2026-10-11"),
        "next week": ("2026-10-12", "2026-10-18"),
        "this month": ("2026-10-01", "2026-10-31"),
        "this quarter": ("2026-10-01", "2026-12-31"),
        "next quarter": ("2027-01-01", "2027-03-31"),
        "last year": ("2025-01-01", "2025-12-31"),
        "this year": ("2026-01-01", "2026-12-31"),
        "next year": ("2027-01-01", "2027-12-31"),
        "2026-08-01 2026-08-15": ("2026-08-01", "2026-08-15"),
        "2026-08-12": ("2026-08-12", "2026-08-12"),
        "2026-W33": ("2026-08-10", "2026-08-16"),
        "2024-02": ("2024-02-01", "2024-02-29"),
        "2026-Q2": ("2026-04-01", "2026-06-30"),
        "2026": ("2026-01-01", "2026-12-31"),
    }
    for expr, expected in cases.items():
        assert task_query.date_range(expr, friday) == expected
    assert task_query.date_range("last month", datetime.date(2026, 1, 15)) == (
        "2025-12-01",
        "2025-12-31",
    )
    assert task_query.date_range("next month", datetime.date(2026, 12, 15)) == (
        "2027-01-01",
        "2027-01-31",
    )
    for invalid in ("2026-02-30", "2026-W99", "next friday", ""):
        with pytest.raises(task_query.UnsupportedInstruction):
            task_query.date_range(invalid, friday)
