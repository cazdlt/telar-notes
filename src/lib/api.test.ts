import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from './api';
import { ApiError } from './types';

function mockJsonResponse(body: unknown, init: { ok?: boolean; status?: number; statusText?: string } = {}) {
  return {
    ok: init.ok ?? true,
    status: init.status ?? 200,
    statusText: init.statusText ?? 'OK',
    json: vi.fn().mockResolvedValue(body),
  } as unknown as Response;
}

describe('api', () => {
  let fetchMock: ReturnType<typeof vi.fn<typeof fetch>>;

  beforeEach(() => {
    fetchMock = vi.fn<typeof fetch>().mockResolvedValue(mockJsonResponse({ ok: true }));
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it('builds raw URLs without calling fetch', () => {
    expect(api.raw('folder/my image.png')).toBe('/api/raw?path=folder%2Fmy%20image.png');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('calls GET endpoints with encoded query parameters and optional revision header', async () => {
    await api.files();
    await api.recentFiles('created', 25);
    await api.note('dir/note 1.md', 'rev-1');
    await api.links('Personal');
    await api.tasks('not done', 'diario/2026-11-19.md');
    await api.search('tag:ai', 'tags');

    expect(fetchMock.mock.calls[0][0]).toBe('/api/files');
    expect(fetchMock.mock.calls[1][0]).toBe('/api/files/recent?sort=created&limit=25');

    const [noteUrl, noteInit] = fetchMock.mock.calls[2];
    expect(noteUrl).toBe('/api/note?path=dir%2Fnote%201.md');
    expect(new Headers(noteInit?.headers).get('If-None-Match')).toBe('rev-1');

    expect(fetchMock.mock.calls[3][0]).toBe('/api/links?vault=Personal');
    expect(fetchMock.mock.calls[4][0]).toBe('/api/tasks?query=not%20done&source=diario%2F2026-11-19.md');
    expect(fetchMock.mock.calls[5][0]).toBe('/api/search?q=tag%3Aai&mode=tags');
  });

  it('sends POST endpoints with JSON content-type and expected payloads', async () => {
    const location = { path: 'todo.md', line: 3, expected: '- [ ] Ship' };
    const patch = { status: 'x', done: '2026-11-19' };

    await api.saveNote('note.md', '# Hello', 'rev-2', true);
    await api.updateTask(location, patch);
    await api.rename('old.md', 'new.md');
    await api.switchVault('Work');

    const expectPost = (callIndex: number, expectedPath: string, expectedBody: unknown) => {
      const [url, init] = fetchMock.mock.calls[callIndex];
      expect(url).toBe(expectedPath);
      expect(init?.method).toBe('POST');
      expect(new Headers(init?.headers).get('Content-Type')).toBe('application/json');
      expect(JSON.parse(String(init?.body))).toEqual(expectedBody);
    };

    expectPost(0, '/api/note', { path: 'note.md', content: '# Hello', base_revision: 'rev-2', force: true });
    expectPost(1, '/api/tasks/update', { location, patch });
    expectPost(2, '/api/rename', { from: 'old.md', to: 'new.md' });
    expectPost(3, '/api/session/vault', { vault: 'Work' });
  });

  it('throws ApiError on 409 revision conflicts and falls back to statusText on invalid error JSON', async () => {
    fetchMock.mockResolvedValueOnce(
      mockJsonResponse({ error: 'Revision conflict' }, { ok: false, status: 409, statusText: 'Conflict' }),
    );

    await expect(api.saveNote('note.md', 'updated', 'stale-rev')).rejects.toMatchObject({
      name: 'Error',
      status: 409,
      message: 'Revision conflict',
    });

    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 502,
      statusText: 'Bad Gateway',
      json: vi.fn().mockRejectedValue(new SyntaxError('Unexpected token')),
    } as unknown as Response);

    const err = await api.files().catch((error: unknown) => error);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(502);
    expect((err as ApiError).message).toBe('Bad Gateway');
  });

  it('sends X-Vault header when window location includes ?vault=', async () => {
    vi.resetModules();
    vi.stubGlobal('location', { search: '?vault=Work' });
    const { api: vaultApi } = await import('./api');

    await vaultApi.files();

    const [, init] = fetchMock.mock.calls[0];
    expect(new Headers(init?.headers).get('X-Vault')).toBe('Work');
  });
});
