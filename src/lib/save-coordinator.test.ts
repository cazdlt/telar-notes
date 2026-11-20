import { describe, expect, it, vi } from 'vitest';
import { SaveCoordinator } from './save-coordinator';

describe('SaveCoordinator', () => {
  it('flushes a pending save immediately', async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    const coordinator = new SaveCoordinator(500);
    coordinator.schedule(save);
    expect(await coordinator.flush()).toEqual({ ok: true });
    expect(save).toHaveBeenCalledOnce();
  });

  it('reports a rejected write', async () => {
    const coordinator = new SaveCoordinator(500);
    coordinator.schedule(async () => { throw new Error('offline'); });
    expect((await coordinator.flush()).ok).toBe(false);
  });

  it('remembers a debounced failure until a later save succeeds', async () => {
    const coordinator = new SaveCoordinator(0);
    coordinator.schedule(async () => { throw new Error('disk full'); });
    await new Promise((resolve) => setTimeout(resolve, 1));
    expect((await coordinator.flush()).ok).toBe(false);
    coordinator.schedule(async () => undefined);
    expect(await coordinator.flush()).toEqual({ ok: true });
  });
});
