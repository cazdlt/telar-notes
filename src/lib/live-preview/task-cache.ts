import { api } from '../api';
import type { TaskQueryResult, TaskRecord } from '../types';

// CodeMirror destroys off-screen widgets; keep the last result per query so they reappear instantly.
export const taskQueryCache = new Map<string, TaskQueryResult>();
const taskQueryRequests = new Map<string, Promise<TaskQueryResult>>();

export const taskQueryKey = (query: string, source: string | undefined): string => `${source ?? ''}\n${query}`;

/** Last resolved result of a Tasks query, if any. */
export const cachedTaskQuery = (query: string, source: string | undefined): TaskQueryResult | undefined =>
  taskQueryCache.get(taskQueryKey(query, source));

/** Stable identity of a task row inside a rendered Tasks query. */
export const taskKey = (task: TaskRecord): string => `${task.location.path}:${task.location.line}`;

/** Fetch a Tasks query, sharing an in-flight request unless `fresh` must observe a just-finished write. */
export function loadTaskQuery(query: string, source: string | undefined, fresh = false): Promise<TaskQueryResult> {
  const key = taskQueryKey(query, source);
  const pending = taskQueryRequests.get(key);
  if (pending && !fresh) return pending;
  const request = api.tasks(query, source)
    .then((result) => { if (taskQueryRequests.get(key) === request) taskQueryCache.set(key, result); return result; })
    .finally(() => { if (taskQueryRequests.get(key) === request) taskQueryRequests.delete(key); });
  taskQueryRequests.set(key, request);
  return request;
}

// Last resolved task per `path#id`, so widgets recreated on scroll render without a flash.
export const taskRefCache = new Map<string, TaskRecord | null>();
