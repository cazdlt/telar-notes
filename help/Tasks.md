# Tasks

Tasks are ordinary Markdown checkboxes, compatible with the Obsidian Tasks plugin:

```markdown
- [ ] Write the report 📅 2026-10-12 ⏫
```

Click the checkbox to advance the status. The next status (done, in progress or cancelled) and the automatic created, done and cancelled dates are set in **Settings > Plugins > Tasks**.

## Statuses

Todo `[ ]`, in progress `[/]`, done `[x]`, cancelled `[-]`, plus the extra statuses of common themes (`[>]` delegated, `[?]` question, `[!]` important, `[*]` star and more). Each shows its own glyph.

## Dates and priority

📅 due, ⏳ scheduled, 🛫 start, ➕ created, ✅ done, ❌ cancelled, and priority markers. They are plain text at the end of the line, so they stay editable and portable.

## Queries

A `tasks` code block lists matching tasks from the whole vault, with live checkboxes:

````markdown
```tasks
not done
due before tomorrow
```
````

Toggling a task in the result updates the note that holds it.
