export class SaveCoordinator {
  private timer: ReturnType<typeof setTimeout> | undefined;
  private writes = new Set<Promise<void>>();
  private pending: (() => Promise<void>) | undefined;
  private lastError: unknown;

  constructor(private readonly delay = 500) {}

  schedule(write: () => Promise<void>): void {
    this.pending = write;
    this.lastError = undefined;
    clearTimeout(this.timer);
    this.timer = setTimeout(() => { void this.save().catch(() => undefined); }, this.delay);
  }

  cancel(): void {
    clearTimeout(this.timer);
    this.timer = undefined;
  }

  discard(): void {
    this.cancel();
    this.pending = undefined;
  }

  async save(): Promise<void> {
    this.cancel();
    const write = this.pending;
    this.pending = undefined;
    if (!write) return;
    const task = Promise.resolve().then(write);
    this.writes.add(task);
    try {
      await task;
      if (!this.pending) this.lastError = undefined;
    } catch (error) {
      this.lastError = error;
      throw error;
    } finally {
      this.writes.delete(task);
    }
  }

  /** Persist the queued change and every request that was already in flight. */
  async flush(): Promise<{ ok: true } | { ok: false; error: unknown }> {
    try {
      if (this.pending) await this.save();
      while (this.writes.size || this.pending) {
        if (this.pending) await this.save();
        if (this.writes.size) await Promise.all([...this.writes]);
      }
      if (this.lastError !== undefined) return { ok: false, error: this.lastError };
      return { ok: true };
    } catch (error) { return { ok: false, error }; }
  }
}
