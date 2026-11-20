"""Obsidian Tasks query DSL compiler: filters, grouping, sorting, and placeholders."""

from __future__ import annotations

import pathlib
import re
from datetime import date, datetime, timedelta
from typing import Any, Callable

from telar.tasks import STATUS_CLASS, normalize_status_symbol, task_index


class UnsupportedInstruction(ValueError):
    """A Tasks query line outside the implemented subset."""


_STATUS_TYPE_ORDER = ["IN_PROGRESS", "TODO", "ON_HOLD", "DONE", "CANCELLED", "NON_TASK"]
_PRIORITY_RANK: dict[str | None, int] = {
    "🔺": 0,
    "⏫": 1,
    "🔼": 2,
    None: 3,
    "🔽": 4,
    "⏬": 5,
}
_PRIORITY_NAMES = {
    "highest": 0,
    "high": 1,
    "medium": 2,
    "none": 3,
    "low": 4,
    "lowest": 5,
}
_WEEKDAYS = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]
_DATE_FIELDS = {
    "done": "done",
    "created": "created",
    "starts": "start",
    "start": "start",
    "scheduled": "scheduled",
    "due": "due",
    "cancelled": "cancelled",
    "happens": "happens",
}
_QUERY_LAYOUT = re.compile(
    r"(?:short|full) mode|show tree|explain|ignore global query|"
    r"(?:hide|show) (?:tree|toolbar|task count|backlinks?|edit button|"
    r"postpone button|priority|urgency|tags|id|depends on|on completion|"
    r"recurrence rule|(?:created|start|scheduled|due|done|cancelled) date)",
    re.I,
)
_QUERY_PLACEHOLDER = re.compile(r"\{\{\s*query\.file\.(\w+)\s*\}\}")

_HAPPENS_WITHIN_WEEK = (
    "!task.happens.moment || "
    "task.happens.moment.isSameOrBefore(moment().add(7, 'days'), 'day')"
)
_RECURRING_GROUP = re.compile(
    r"group by function task\.isRecurring\s*\?\s*'(?P<recurring>[^']*)'\s*:\s*"
    r"\((?P<condition>.+)\|\|\s*false\s*\)\s*\?\s*'(?P<overdue>[^']*)'\s*:\s*'(?P<current>[^']*)'"
)
_OVERDUE_CONDITIONS = {
    "task.happens.moment?.isBefore(moment(), 'day')": False,
    "(task.happens.moment?.isBefore(moment(), 'day') && task.status.type != 'IN_PROGRESS')": True,
}
_PERSON_GROUP = (
    "group by function const m = task.description.match(/\\[\\[([^\\]|#]+)/); "
    "return m ? '[[' + m[1].trim() + ']]' : 'Sin persona';"
)
_PERSON_NO_EMBED_GROUP = (
    "group by function const m = task.description.match(/(?<!!)\\[\\[([^\\]|#]+)/); "
    "return m ? '[[' + m[1].trim() + ']]' : 'Sin persona';"
)
# Same regexes as the JavaScript in the queries above.
_PERSON_LINK = re.compile(r"\[\[([^\]|#]+)")
_PERSON_NO_EMBED_LINK = re.compile(r"(?<!!)\[\[([^\]|#]+)")
_FOLDER_GROUP = "group by function task.file.folder.slice(0, -1).split('/')[2] + \"/\""
_FOLDER_SEGMENT_GROUP = (
    "group by function task.file.folder.split('/')[2] ?? "
    "task.file.folder.split('/')[1] ?? task.file.folder.split('/')[0]"
)
_FILE_GROUP = (
    "group by function '[[' + task.file.path.slice(0, -3) + '|' + "
    "task.file.filename.slice(0, -3) + ']]'"
)
_FOLDER_FILE_GROUP = (
    "group by function '[[' + task.file.path.slice(0, -3) + '|' + "
    "task.file.folder.slice(0, -1).split('/').pop() + '/' + "
    "task.file.filename.slice(0, -3) + ']]'"
)


def file_properties(path: str) -> dict[str, str]:
    """Return Tasks' file properties; folders and roots keep a trailing slash."""
    pure = pathlib.PurePosixPath(path)
    folder = "/" if str(pure.parent) == "." else f"{pure.parent}/"
    return {
        "path": path,
        "pathWithoutExtension": re.sub(r"\.md$", "", path),
        "filename": pure.name,
        "filenameWithoutExtension": re.sub(r"\.md$", "", pure.name),
        "folder": folder,
        "root": f"{pure.parts[0]}/" if len(pure.parts) > 1 else "/",
    }


def expand_placeholders(line: str, source: str | None) -> str:
    """Expand ``{{query.file.*}}`` placeholders from the source note path."""

    def replace(match: re.Match[str]) -> str:
        if not source:
            raise UnsupportedInstruction("placeholders need a source note")
        properties = file_properties(source)
        if match.group(1) not in properties:
            raise UnsupportedInstruction(f"unknown placeholder {match.group(0)}")
        return properties[match.group(1)]

    return _QUERY_PLACEHOLDER.sub(replace, line)


def task_happens(task: dict[str, Any]) -> str | None:
    """Return the earliest start, scheduled, or due date."""
    dates = [task["dates"].get(key) for key in ("start", "scheduled", "due")]
    present = [d for d in dates if d]
    return min(present) if present else None


def task_date(task: dict[str, Any], field: str) -> str | None:
    """Return a task's date for ``field``, including virtual ``happens``."""
    return task_happens(task) if field == "happens" else task["dates"].get(field)


def _shift_months(year: int, month: int, offset: int) -> tuple[date, date]:
    index = year * 12 + month - 1 + offset
    start = date(index // 12, index % 12 + 1, 1)
    following = date((index + 1) // 12, (index + 1) % 12 + 1, 1)
    return start, following - timedelta(days=1)


def date_range(value: str, today: date) -> tuple[str, str]:
    """Resolve a Tasks date or date range to inclusive ISO bounds."""
    text = value.strip().lower()
    single = {"yesterday": -1, "today": 0, "tomorrow": 1}
    try:
        if text in single:
            day = today + timedelta(days=single[text])
            return day.isoformat(), day.isoformat()
        if relative := re.fullmatch(
            r"(last|this|next) (week|month|quarter|year)", text
        ):
            offset = {"last": -1, "this": 0, "next": 1}[relative.group(1)]
            unit = relative.group(2)
            if unit == "week":
                start = (
                    today - timedelta(days=today.weekday()) + timedelta(weeks=offset)
                )
                return start.isoformat(), (start + timedelta(days=6)).isoformat()
            if unit == "month":
                start, end = _shift_months(today.year, today.month, offset)
            elif unit == "quarter":
                first = (today.month - 1) // 3 * 3 + 1
                start, _ = _shift_months(today.year, first, offset * 3)
                _, end = _shift_months(start.year, start.month, 2)
            else:
                start, end = (
                    date(today.year + offset, 1, 1),
                    date(today.year + offset, 12, 31),
                )
            return start.isoformat(), end.isoformat()
        if bounds := re.fullmatch(r"(\d{4}-\d{2}-\d{2})\s+(\d{4}-\d{2}-\d{2})", text):
            start, end = (date.fromisoformat(bounds.group(n)) for n in (1, 2))
            return start.isoformat(), end.isoformat()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            iso = date.fromisoformat(text).isoformat()
            return iso, iso
        if week := re.fullmatch(r"(\d{4})-w(\d{2})", text):
            start = date.fromisocalendar(int(week.group(1)), int(week.group(2)), 1)
            return start.isoformat(), (start + timedelta(days=6)).isoformat()
        if month := re.fullmatch(r"(\d{4})-(\d{2})", text):
            start, end = _shift_months(int(month.group(1)), int(month.group(2)), 0)
            return start.isoformat(), end.isoformat()
        if quarter := re.fullmatch(r"(\d{4})-q([1-4])", text):
            start, _ = _shift_months(
                int(quarter.group(1)), int(quarter.group(2)) * 3 - 2, 0
            )
            _, end = _shift_months(start.year, start.month, 2)
            return start.isoformat(), end.isoformat()
        if re.fullmatch(r"\d{4}", text):
            return f"{text}-01-01", f"{text}-12-31"
    except ValueError as error:
        raise UnsupportedInstruction(f"invalid date {value!r}") from error
    raise UnsupportedInstruction(f"unrecognized date {value!r}")


def _compile_regex(literal: str) -> re.Pattern[str]:
    match = re.fullmatch(r"/(.*)/([gimsuy]*)", literal.strip())
    if not match:
        raise UnsupportedInstruction("regex must be written as /pattern/flags")
    flags = 0
    for flag, value in (("i", re.I), ("m", re.M), ("s", re.S)):
        if flag in match.group(2):
            flags |= value
    try:
        return re.compile(match.group(1), flags)
    except re.error as error:
        raise UnsupportedInstruction(f"invalid regex: {error}") from error


def _text_field(task: dict[str, Any], field: str) -> list[str]:
    if field in {"tag", "tags"}:
        return [f"#{tag}" for tag in task["tags"]]
    if field in {"path", "filename", "folder", "root"}:
        return [file_properties(task["location"]["path"])[field]]
    values = {
        "description": task["description"],
        "heading": task["heading"],
        "recurrence": task["recurrence"] or "",
        "status.name": task["status"]["name"],
    }
    return [values[field]]


def _status_function(expression: str) -> Callable[[dict[str, Any]], bool] | None:
    """Compile an allowlisted disjunction of conjunctions over status fields."""
    alternatives: list[list[tuple[str, bool, str]]] = []
    for clause in expression.split(" || "):
        conditions: list[tuple[str, bool, str]] = []
        for atom in clause.split(" && "):
            match = re.fullmatch(
                rf"task\.status\.(symbol|name|type) (===|!==|==|!=) '({STATUS_CLASS}|[\w -]+)'",
                atom.strip(),
            )
            if not match:
                return None
            field, operator, expected = match.groups()
            if field == "symbol":
                expected = normalize_status_symbol(expected)
            conditions.append((field, operator.startswith("="), expected))
        alternatives.append(conditions)

    def matches(task: dict[str, Any]) -> bool:
        return any(
            all(
                (task["status"][field] == expected) == equal
                for field, equal, expected in clause
            )
            for clause in alternatives
        )

    return matches


def _compile_leaf_filter(text: str, today: date) -> Callable[[dict[str, Any]], bool]:
    """Compile one declarative Tasks filter into a task predicate."""
    lower = text.lower()
    if lower in {"done"}:
        return lambda task: task["status"]["type"] in {"DONE", "CANCELLED", "NON_TASK"}
    if lower in {"not done", "hide done"}:
        return lambda task: task["status"]["type"] in {"TODO", "IN_PROGRESS", "ON_HOLD"}
    if lower in {"is recurring", "has recurrence"}:
        return lambda task: bool(task["recurrence"])
    if lower in {"is not recurring", "no recurrence"}:
        return lambda task: not task["recurrence"]
    if lower == "exclude sub-items":
        return lambda task: task["indent"] == 0
    if lower in {"has tags", "no tags"}:
        return lambda task: bool(task["tags"]) == (lower == "has tags")
    if status := re.fullmatch(rf"status is ({STATUS_CLASS})", text):
        symbol = normalize_status_symbol(status.group(1))
        return lambda task: task["status"]["symbol"] == symbol
    if status_type := re.fullmatch(r"status\.type (is|is not) (\w+)", text, re.I):
        expected = status_type.group(2).upper()
        if expected not in _STATUS_TYPE_ORDER:
            raise UnsupportedInstruction(f"unknown status type {expected}")
        negate = status_type.group(1).lower() == "is not"
        return lambda task: (task["status"]["type"] == expected) != negate
    if priority := re.fullmatch(
        r"priority is (?:(above|below|not) )?(lowest|low|none|medium|high|highest)",
        text,
        re.I,
    ):
        wanted = _PRIORITY_NAMES[priority.group(2).lower()]
        modifier = priority.group(1).lower() if priority.group(1) else None
        compare = {
            None: lambda rank: rank == wanted,
            "not": lambda rank: rank != wanted,
            "above": lambda rank: rank < wanted,
            "below": lambda rank: rank > wanted,
        }[modifier]
        return lambda task: compare(_PRIORITY_RANK.get(task["priority"], 3))
    if presence := re.fullmatch(
        rf"(has|no) ({'|'.join(_DATE_FIELDS)}) date", text, re.I
    ):
        field = _DATE_FIELDS[presence.group(2).lower()]
        present = presence.group(1).lower() == "has"
        return lambda task: bool(task_date(task, field)) == present
    if dated := re.fullmatch(
        rf"({'|'.join(_DATE_FIELDS)})(?: (on or before|on or after|before|after|on|in))? (.+)",
        text,
        re.I,
    ):
        field = _DATE_FIELDS[dated.group(1).lower()]
        start, end = date_range(dated.group(3), today)
        modifier = dated.group(2).lower() if dated.group(2) else None
        check = {
            None: lambda day: start <= day <= end,
            "on": lambda day: start <= day <= end,
            "in": lambda day: start <= day <= end,
            "before": lambda day: day < start,
            "after": lambda day: day > end,
            "on or before": lambda day: day <= end,
            "on or after": lambda day: day >= start,
        }[modifier]
        keys = ("start", "scheduled", "due") if field == "happens" else (field,)
        return lambda task: any(
            check(task["dates"][key]) for key in keys if task["dates"].get(key)
        )
    if textual := re.fullmatch(
        r"(description|path|filename|folder|root|heading|recurrence|status\.name|tags?) "
        r"(includes|include|does not include|do not include|regex matches|regex does not match) (.+)",
        text,
        re.I,
    ):
        field, operator, needle = textual.groups()
        field, operator = field.lower(), operator.lower()
        negate = "not" in operator
        if "regex" in operator:
            pattern = _compile_regex(needle)
            return lambda task: (
                any(pattern.search(value) for value in _text_field(task, field))
                != negate
            )
        folded = needle.strip().casefold()
        return lambda task: (
            any(folded in value.casefold() for value in _text_field(task, field))
            != negate
        )
    if lower.startswith("filter by function "):
        expression = " ".join(text[len("filter by function ") :].split())
        if expression == _HAPPENS_WITHIN_WEEK:
            limit = (today + timedelta(days=7)).isoformat()
            return lambda task: (task_happens(task) or "") <= limit
        if matcher := _status_function(expression):
            return matcher
        raise UnsupportedInstruction("only allowlisted functions are evaluated")
    raise UnsupportedInstruction("unknown filter")


def _boolean_tokens(text: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    index = 0
    while index < len(text):
        if text[index].isspace():
            index += 1
            continue
        if text[index] == "(":
            depth, end = 0, index
            for end in range(index, len(text)):
                depth += {"(": 1, ")": -1}.get(text[end], 0)
                if depth == 0:
                    break
            if depth:
                raise UnsupportedInstruction("unbalanced parentheses")
            tokens.append(("filter", text[index + 1 : end].strip()))
            index = end + 1
            continue
        operator = re.match(r"(AND|OR|XOR|NOT)\b", text[index:])
        if not operator:
            raise UnsupportedInstruction("expected AND, OR, XOR, NOT, or (filter)")
        tokens.append(("operator", operator.group(1)))
        index += operator.end()
    return tokens


def compile_filter(text: str, today: date) -> Callable[[dict[str, Any]], bool]:
    """Compile a filter, including Tasks' parenthesized boolean combinations."""
    if not (text.startswith("(") or text.startswith("NOT ")):
        return _compile_leaf_filter(text, today)
    tokens, position = _boolean_tokens(text), 0

    def peek() -> tuple[str, str] | None:
        return tokens[position] if position < len(tokens) else None

    def binary(
        operator: str,
        operand: Callable[[], Callable[[dict[str, Any]], bool]],
        combine: Callable[[bool, bool], bool],
    ) -> Callable[[], Callable[[dict[str, Any]], bool]]:
        def parse() -> Callable[[dict[str, Any]], bool]:
            nonlocal position
            left = operand()
            while peek() == ("operator", operator):
                position += 1
                right = operand()
                left = (lambda a, b: lambda task: combine(a(task), b(task)))(
                    left, right
                )
            return left

        return parse

    def unary() -> Callable[[dict[str, Any]], bool]:
        nonlocal position
        token = peek()
        if token == ("operator", "NOT"):
            position += 1
            inner = unary()
            return lambda task: not inner(task)
        if token and token[0] == "filter":
            position += 1
            return compile_filter(token[1], today)
        raise UnsupportedInstruction("expected (filter)")

    conjunction = binary("AND", unary, lambda a, b: a and b)
    exclusive = binary("XOR", conjunction, lambda a, b: a != b)
    disjunction = binary("OR", exclusive, lambda a, b: a or b)
    predicate = disjunction()
    if position != len(tokens):
        raise UnsupportedInstruction("unexpected boolean operator")
    return predicate


def _date_group(task: dict[str, Any], field: str) -> tuple[str, str]:
    value = task_date(task, field)
    if not value:
        return "~", f"No {field} date"
    try:
        weekday = _WEEKDAYS[date.fromisoformat(value).weekday()]
    except ValueError:
        return "!", f"Invalid {field} date"
    return value, f"{value} {weekday}"


def compile_group(
    directive: str, today: date
) -> tuple[Callable[[dict[str, Any]], tuple[str, str]], bool]:
    """Return a grouping function yielding (sort key, label) and its direction."""
    value = " ".join(directive.split())
    if recurring := _RECURRING_GROUP.fullmatch(value):
        condition = " ".join(recurring.group("condition").split())
        if condition not in _OVERDUE_CONDITIONS:
            raise UnsupportedInstruction("only allowlisted functions are evaluated")
        skip_in_progress = _OVERDUE_CONDITIONS[condition]

        def recurring_group(task: dict[str, Any]) -> str:
            if task["recurrence"]:
                return recurring.group("recurring")
            happens = task_happens(task)
            overdue = bool(happens and happens < today.isoformat()) and not (
                skip_in_progress and task["status"]["type"] == "IN_PROGRESS"
            )
            return recurring.group("overdue" if overdue else "current")

        return lambda task: (recurring_group(task), recurring_group(task)), False

    def path_stem(task: dict[str, Any]) -> pathlib.PurePosixPath:
        return pathlib.PurePosixPath(task["location"]["path"].removesuffix(".md"))

    def folder_segment(task: dict[str, Any]) -> str:
        parts = file_properties(task["location"]["path"])["folder"].split("/")
        return parts[2] if len(parts) > 2 else parts[1] if len(parts) > 1 else parts[0]

    def person(pattern: re.Pattern[str]) -> Callable[[dict[str, Any]], str]:
        def group(task: dict[str, Any]) -> str:
            match = pattern.search(task["description"])
            return f"[[{match.group(1).strip()}]]" if match else "Sin persona"

        return group

    functions: dict[str, Callable[[dict[str, Any]], str]] = {
        _PERSON_GROUP: person(_PERSON_LINK),
        _PERSON_NO_EMBED_GROUP: person(_PERSON_NO_EMBED_LINK),
        _FOLDER_GROUP: lambda task: (
            (lambda parts: parts[2] if len(parts) > 2 else parts[-1] if parts else "")(
                path_stem(task).parent.parts
            )
            + "/"
        ),
        _FOLDER_SEGMENT_GROUP: folder_segment,
        _FILE_GROUP: lambda task: f"[[{path_stem(task)}|{path_stem(task).name}]]",
        _FOLDER_FILE_GROUP: lambda task: (
            f"[[{path_stem(task)}|{path_stem(task).parent.name}/{path_stem(task).name}]]"
        ),
    }
    if value in functions:
        function = functions[value]
        return lambda task: (function(task), function(task)), False
    if value.startswith("group by function "):
        raise UnsupportedInstruction("only allowlisted functions are evaluated")
    declarative = re.fullmatch(r"group by (\S+)( reverse)?", value, re.I)
    if not declarative:
        raise UnsupportedInstruction("unknown group")
    field, reverse = declarative.group(1).lower(), bool(declarative.group(2))

    def labelled(
        label: Callable[[dict[str, Any]], str],
    ) -> Callable[[dict[str, Any]], tuple[str, str]]:
        return lambda task: (label(task), label(task))

    if field == "root":
        return (
            labelled(
                lambda task: (lambda parts: parts[0] if len(parts) > 1 else "/")(
                    pathlib.PurePosixPath(task["location"]["path"]).parts
                )
            ),
            reverse,
        )
    if field == "folder":
        return (
            labelled(
                lambda task: str(pathlib.PurePosixPath(task["location"]["path"]).parent)
            ),
            reverse,
        )
    if field == "filename":
        return (
            labelled(lambda task: f"[[{path_stem(task)}|{path_stem(task).name}]]"),
            reverse,
        )
    if field == "path":
        return labelled(lambda task: str(path_stem(task))), reverse
    if field == "heading":
        return labelled(lambda task: task["heading"] or "Sin encabezado"), reverse
    if field == "status.name":
        return labelled(lambda task: task["status"]["name"]), reverse
    if field == "status.type":
        return (
            lambda task: (
                f"{_STATUS_TYPE_ORDER.index(task['status']['type'])}",
                task["status"]["type"],
            )
        ), reverse
    if field in _DATE_FIELDS:
        return (lambda task: _date_group(task, _DATE_FIELDS[field])), reverse
    raise UnsupportedInstruction("unknown group")


def compile_sort(
    directive: str,
) -> tuple[Callable[[dict[str, Any]], Any], bool]:
    """Return a sort key and direction; missing values sort last."""
    match = re.fullmatch(r"sort by (\S+)( reverse)?", " ".join(directive.split()), re.I)
    if not match:
        raise UnsupportedInstruction("unknown sort")
    field, reverse = match.group(1).lower(), bool(match.group(2))
    if field == "priority":
        return lambda task: _PRIORITY_RANK.get(task["priority"], 3), reverse
    if field in {"status", "status.type"}:
        return lambda task: _STATUS_TYPE_ORDER.index(task["status"]["type"]), reverse
    if field in _DATE_FIELDS:
        key = _DATE_FIELDS[field]
        return (
            lambda task: (0, task_date(task, key)) if task_date(task, key) else (1, "")
        ), reverse
    if field in {"description", "path", "filename", "heading", "status.name"}:
        return lambda task: _text_field(task, field)[0].casefold(), reverse
    if field == "recurring":
        return lambda task: not task["recurrence"], reverse
    raise UnsupportedInstruction("unknown sort")


def query_tasks(
    vault: pathlib.Path, query: str, query_source: str | None = None
) -> dict[str, Any]:
    """Evaluate a Tasks query subset. Unsupported filters return no tasks."""
    today = datetime.now().date()
    filters: list[Callable[[dict[str, Any]], bool]] = []
    sorts: list[tuple[Callable[[dict[str, Any]], Any], bool]] = []
    groups: list[tuple[Callable[[dict[str, Any]], tuple[str, str]], bool]] = []
    errors: list[str] = []
    limit: int | None = None
    filter_failed = False

    for raw in query.splitlines():
        directive = raw.strip().removeprefix("> ").strip()
        if (
            not directive
            or directive.startswith("#")
            or _QUERY_LAYOUT.fullmatch(directive)
        ):
            continue
        lower = directive.lower()
        is_filter = not lower.startswith(("group by", "sort by", "limit"))
        try:
            line = expand_placeholders(directive, query_source)
            if lower.startswith("group by"):
                groups.append(compile_group(line, today))
            elif lower.startswith("sort by"):
                sorts.append(compile_sort(line))
            elif limit_match := re.fullmatch(r"limit(?: to)? (\d+)(?: tasks?)?", lower):
                limit = int(limit_match.group(1))
            else:
                is_filter = True
                filters.append(compile_filter(line, today))
        except UnsupportedInstruction as error:
            errors.append(f"Unsupported instruction: {directive} ({error})")
            filter_failed = filter_failed or is_filter

    if filter_failed:
        return {"tasks": [], "errors": errors}
    tasks = [
        task for task in task_index(vault) if all(match(task) for match in filters)
    ]
    for key, reverse in reversed(sorts):
        tasks.sort(key=key, reverse=reverse)
    if limit is not None:
        tasks = tasks[:limit]
    keyed = [(task, [group(task) for group, _ in groups]) for task in tasks]
    for index in range(len(groups) - 1, -1, -1):
        keyed.sort(
            key=lambda item: item[1][index][0].casefold(), reverse=groups[index][1]
        )
    return {
        "tasks": [
            {
                **task,
                "groups": [
                    label
                    for _, raw_label in keys
                    if (label := re.sub(r"%%.*?%%", "", raw_label).strip())
                ],
            }
            for task, keys in keyed
        ],
        "errors": errors,
    }
