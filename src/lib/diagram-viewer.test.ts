import { describe, expect, it } from 'vitest';
import { clampScale, fitView, zoomAt } from './diagram-viewer';

describe('diagram viewer math', () => {
  it('clamps the scale', () => {
    expect(clampScale(0.01)).toBe(0.1);
    expect(clampScale(50)).toBe(8);
    expect(clampScale(2)).toBe(2);
  });

  it('keeps the cursor point fixed while zooming', () => {
    const view = { x: 10, y: 20, k: 1 };
    const next = zoomAt(view, 2, 100, 100);
    expect(next.k).toBe(2);
    expect((100 - next.x) / next.k).toBeCloseTo((100 - view.x) / view.k);
    expect((100 - next.y) / next.k).toBeCloseTo((100 - view.y) / view.k);
  });

  it('does not move when already at the scale limit', () => {
    const view = { x: 5, y: 5, k: 8 };
    expect(zoomAt(view, 2, 50, 50)).toEqual(view);
  });

  it('fits and centers the content', () => {
    const view = fitView(1000, 500, 600, 400, 50);
    expect(view.k).toBeCloseTo(0.5);
    expect(view.x).toBeCloseTo(50);
    expect(view.y).toBeCloseTo(75);
  });
});
