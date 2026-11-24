# Editing

Notes are plain Markdown files. The editor renders them as you type (live preview): the line under the cursor shows its Markdown, every other line shows the result. Turn on **Persistent Live Preview** in settings to keep everything rendered while you type.

Changes save automatically 500 ms after you stop typing. If the file changed on disk in the meantime, you are asked what to do instead of losing either version.

## Edit rendered elements

Links, tables, embeds, task queries, diagrams and task references are widgets. Hold **Option** and click one to reveal and edit its Markdown. While Option is held, editable elements get a dashed outline. A plain click keeps its normal meaning (for example, following a link).

## Embeds and images

- Paste or drop an image to save it in your attachment folder and embed it.
- `![[Note]]` embeds a note, `![[Note#Heading]]` a section, `![[Note#^id]]` one block.
- Tables, Mermaid fences (` ```mermaid `) and tasks queries render in place.
- Fenced code blocks support syntax highlighting: type a language after ```` ``` ```` with autocomplete, or pick one from the block header selector.

## Autocomplete

- Type `#` anywhere outside headings, frontmatter, and code blocks to autocomplete tags from the vault and current note.
- Type `[[^^` to search open tasks and insert a block reference.
- On task lines, type keywords like `due martes`, `start sunday`, `high`, or `every week` to insert Obsidian Tasks metadata (see [[Tasks]]).

## Reading mode

Switch to reading mode for a clean, non-editable view of the note.
