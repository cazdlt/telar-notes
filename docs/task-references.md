# Linked task references

A note can reference a task that lives in another note, instead of restating it. The
main use is the daily plan (`### Para hoy`): a plan item that comes from an initiative
task is written as a reference, so the task text exists in one place only.

## Syntax

The task line gets an Obsidian block ID as its last token:

```markdown
- [ ] Review release notes for the search module 📅 2026-10-10 ^review-release-notes-search
```

Any other note references it with a block embed:

```markdown
- ![[Roadmap#^review-release-notes-search]]
- ![[Roadmap#^review-release-notes-search]] — before the sync with Alice
```

- The link target is the note's basename. Use the vault-relative path without `.md` only
  when another note shares the basename.
- Write the reference in a plain bullet (`- `), never in a checkbox line (`- [ ] `),
  which would create a second task.
- Short context can follow the embed on the same line; do not restate the task.

## Block IDs

- The ID is the last token of the line, preceded by a space: ` ^id`. The Tasks plugin
  and Telar Notes both keep it last when they add dates (✅, ❌, 📅…) or change the status.
- IDs are unique within their file.
- If a task already has an ID, reuse it; never add a second one.
- Convention for new IDs: lowercase ASCII (accents stripped), hyphen-separated, built from
  the first four words of the description, skipping Spanish/English stopwords (`de`, `la`,
  `el`, `para`, `con`, `the`, `of`, …) and dropping links and URLs. If the slug is already
  taken in the file, append `-2`, `-3`, ….
- Recurring tasks: the next occurrence is created without the ID; the reference keeps
  pointing at the occurrence that had it.

Agents can add the ID by editing the task line directly, or with the API, which creates it
only when missing and returns it:

```
POST /api/tasks/block-id  {"location": {"path": "...", "line": N, "expected": "<current line>"}}
→ {"ok": true, "id": "review-release-notes-search", "revision": "..."}
```

## How it renders

Telar Notes (live preview):

- The reference renders inline as the source task: a status checkbox, the task description, and a `↗ Note` chip.
- Changing the checkbox updates the task in its source note; the daily note is not modified.
- On a closed daily note (`YYYY-MM-DD.md`), a task finished or cancelled on a later day shows
  a `done MM-DD` / `cancelled MM-DD` badge.
- Only the chip opens the source note. Alt/Option-click shows the embed's markdown.
- Typing `[[^^` opens a picker of open tasks; choosing one adds the ID if needed and inserts
  the embed.
- If the ID or note no longer exists (for example, the task was moved to another note), it
  renders as `Missing task: Note#^id`.

Obsidian renders the same embed as a block embed of the task line.

## Guidance for the daily plan

- A plan item that comes from an existing task: write `- ![[Note#^id]]`, adding the ID
  first if the task has none.
- A plan item with no task behind it (meetings, one-off reminders): plain text as before.
- Do not create a task just to reference it, and do not copy the task's description or
  log into the plan.
- The task text is not duplicated, so text search finds it only in its source note.
  Telar Notes's backlinks and graph ignore embeds; Obsidian's graph counts the embed as a
  link to the source note.
