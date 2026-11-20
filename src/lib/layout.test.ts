import { describe, expect, it } from 'vitest';
import { clampRightWidth, clampTreeWidth, computeResizedWidth } from './layout';

describe('layout', () => {
  it('clamps left and right panel widths within bounds', () => {
    expect(clampTreeWidth(50)).toBe(160);
    expect(clampTreeWidth(800)).toBe(460);
    expect(clampTreeWidth(260)).toBe(260);

    expect(clampRightWidth(100)).toBe(240);
    expect(clampRightWidth(900)).toBe(640);
    expect(clampRightWidth(350)).toBe(350);
  });

  it('computes resized width from pointer delta', () => {
    expect(computeResizedWidth('left', 238, 40)).toBe(278);
    expect(computeResizedWidth('right', 300, -50)).toBe(350);
    expect(computeResizedWidth('right', 300, 100)).toBe(240);
  });
});
