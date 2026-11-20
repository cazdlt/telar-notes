# Task references

Show a task that lives in another note without copying its text. Typical use: the daily plan.

## Use

1. Type `[[^^` in any note and pick an open task. A block ID is added to the task if it has none, and the reference is inserted.
2. Or write it by hand: the task line ends with ` ^id`, and the other note has `- ![[Source note#^id]]` in a plain bullet (never in a `- [ ]` line).

```markdown
- [ ] Review the experiment results 📅 2026-10-10 ^review-experiment-results
- ![[Project#^review-experiment-results]] before the meeting
```

## How it looks

The reference renders inline as the source task: a checkbox, its headline and a `↗ Note` chip. Changing the checkbox updates the task in its source note. On a closed daily note, a task finished on a later day shows a `done MM-DD` badge. Only the chip opens the source note. Option-click shows the Markdown. If the task was removed or moved, it shows `Missing task`.

In Obsidian the same line is a normal block embed.

Developer details live in `docs/task-references.md` in the Telar Notes repository.
