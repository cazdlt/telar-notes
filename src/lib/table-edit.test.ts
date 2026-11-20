import { describe, expect, it } from 'vitest';
import { editTable, tableColumns } from './table-edit';

const table = ['| a | b |', '| :-- | --: |', '| 1 | 2 |', '| 3 | 4 |'].join('\n');

describe('editTable', () => {
  it('inserts an empty row after the header or a body row without touching other lines', () => {
    expect(editTable(table, { kind: 'insert-row', after: 0 }).split('\n')).toEqual(['| a | b |', '| :-- | --: |', '|  |  |', '| 1 | 2 |', '| 3 | 4 |']);
    expect(editTable(table, { kind: 'insert-row', after: 2 }).split('\n').at(-1)).toBe('|  |  |');
  });

  it('deletes a body row but never the header', () => {
    expect(editTable(table, { kind: 'delete-row', row: 1 })).toBe(['| a | b |', '| :-- | --: |', '| 3 | 4 |'].join('\n'));
    expect(editTable(table, { kind: 'delete-row', row: 0 })).toBe(table);
  });

  it('inserts a column and keeps the existing alignment', () => {
    expect(editTable(table, { kind: 'insert-column', after: 0 })).toBe(
      ['| a |  | b |', '| :-- | --- | --: |', '| 1 |  | 2 |', '| 3 |  | 4 |'].join('\n'),
    );
  });

  it('deletes a column but never the last one', () => {
    expect(editTable(table, { kind: 'delete-column', column: 1 })).toBe(['| a |', '| :-- |', '| 1 |', '| 3 |'].join('\n'));
    const single = ['| a |', '| --- |', '| 1 |'].join('\n');
    expect(editTable(single, { kind: 'delete-column', column: 0 })).toBe(single);
  });

  it('keeps escaped pipes and quote prefixes', () => {
    const quoted = ['> | a \\| b | c |', '> | --- | --- |'].join('\n');
    expect(tableColumns(quoted)).toBe(2);
    expect(editTable(quoted, { kind: 'delete-column', column: 1 })).toBe(['> | a \\| b |', '> | --- |'].join('\n'));
    expect(editTable(quoted, { kind: 'insert-row', after: 0 }).split('\n').at(-1)).toBe('> |  |  |');
  });
});
