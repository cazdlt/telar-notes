import { SearchQuery } from '@codemirror/search';
import { describe, expect, it } from 'vitest';
import { matchingTasks, tasksInDisplayOrder } from './task-query-find';
import type { TaskRecord } from './types';

const task = (line: number, description: string, groups?: string[]): TaskRecord => ({
  location: { path: 'a.md', line } as TaskRecord['location'],
  status: { symbol: ' ', name: 'Todo', type: 'TODO' },
  description, heading: '', parent: null, indent: 0, dates: {}, priority: null, tags: [],
  recurrence: null, delete_when_done: false, block_id: null, groups,
});
const lines = (tasks: TaskRecord[]) => tasks.map((item) => item.location.line);

describe('tasksInDisplayOrder', () => {
  it('lists ungrouped tasks first, then groups in first-seen order, recursively', () => {
    const tasks = [task(1, '', ['B']), task(2, ''), task(3, '', ['A', 'y']), task(4, '', ['B']), task(5, '', ['A']), task(6, '', ['A', 'x'])];
    expect(lines(tasksInDisplayOrder(tasks))).toEqual([2, 1, 4, 5, 3, 6]);
  });
});

describe('matchingTasks', () => {
  const tasks = [task(1, 'Revisar [[Alice Smith|Alice]]'), task(2, '**Deploy** api'), task(3, 'otra cosa')];

  it('matches the visible text, not link targets or markup', () => {
    expect(lines(matchingTasks(tasks, new SearchQuery({ search: 'alice' })))).toEqual([1]);
    expect(lines(matchingTasks(tasks, new SearchQuery({ search: 'smith' })))).toEqual([]);
    expect(lines(matchingTasks(tasks, new SearchQuery({ search: 'deploy api' })))).toEqual([2]);
  });

  it('honors the panel options and ignores an empty query', () => {
    expect(lines(matchingTasks(tasks, new SearchQuery({ search: 'alice', caseSensitive: true })))).toEqual([]);
    expect(lines(matchingTasks(tasks, new SearchQuery({ search: '^otra', regexp: true })))).toEqual([3]);
    expect(matchingTasks(tasks, new SearchQuery({ search: '' }))).toEqual([]);
  });
});
