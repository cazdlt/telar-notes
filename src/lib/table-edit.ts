/**
 * Structural edits on a GFM pipe table's Markdown source.
 *
 * Rows are numbered as rendered: 0 is the header, 1.. are body rows (the delimiter row is
 * not counted). Row edits touch only the affected line; column edits rewrite every line in
 * a normalized `| a | b |` form. Edits that would remove the header or the last column
 * return the source unchanged.
 */
export type TableEdit =
  | { kind: 'insert-row'; after: number }
  | { kind: 'delete-row'; row: number }
  | { kind: 'insert-column'; after: number }
  | { kind: 'delete-column'; column: number };

// Blockquote/callout markers and indentation that precede the table on every line.
const PREFIX = /^[ \t]*(?:>[ \t]?)*/;

function splitLine(line: string): { prefix: string; cells: string[] } {
  const prefix = line.match(PREFIX)?.[0] ?? '';
  let body = line.slice(prefix.length).trim();
  if (body.startsWith('|')) body = body.slice(1);
  if (body.endsWith('|') && !body.endsWith('\\|')) body = body.slice(0, -1);
  return { prefix, cells: body.split(/(?<!\\)\|/).map((cell) => cell.trim()) };
}

function joinLine(prefix: string, cells: string[]): string {
  return `${prefix}| ${cells.join(' | ')} |`;
}

/** Number of columns, taken from the header row. */
export function tableColumns(markdown: string): number {
  return splitLine(markdown.split('\n')[0]).cells.length;
}

/** Applies `edit` to the table source and returns the new source. */
export function editTable(markdown: string, edit: TableEdit): string {
  const lines = markdown.split('\n');
  const columns = tableColumns(markdown);
  const prefix = splitLine(lines[0]).prefix;
  if (edit.kind === 'insert-row') {
    const at = Math.min(edit.after === 0 ? 2 : edit.after + 2, lines.length);
    lines.splice(at, 0, joinLine(prefix, Array<string>(columns).fill('')));
    return lines.join('\n');
  }
  if (edit.kind === 'delete-row') {
    if (edit.row < 1 || edit.row + 1 >= lines.length) return markdown;
    lines.splice(edit.row + 1, 1);
    return lines.join('\n');
  }
  if (edit.kind === 'delete-column' && (columns < 2 || edit.column < 0 || edit.column >= columns)) return markdown;
  return lines.map((line, index) => {
    const row = splitLine(line);
    if (edit.kind === 'insert-column') {
      while (row.cells.length <= edit.after) row.cells.push(index === 1 ? '---' : '');
      row.cells.splice(edit.after + 1, 0, index === 1 ? '---' : '');
    } else {
      row.cells.splice(edit.column, 1);
    }
    return joinLine(row.prefix, row.cells);
  }).join('\n');
}
