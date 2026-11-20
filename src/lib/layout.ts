// Below this width the explorer and right panel float over the editor (see styles/responsive.css).
export const FLOATING_PANELS_QUERY = '(max-width: 1100px)';

export const TREE_WIDTH_DEFAULT = 238;
export const TREE_WIDTH_MIN = 160;
export const TREE_WIDTH_MAX = 460;

export const RIGHT_WIDTH_DEFAULT = 300;
export const RIGHT_WIDTH_MIN = 240;
export const RIGHT_WIDTH_MAX = 640;

export function clampTreeWidth(width: number): number {
  return Math.min(TREE_WIDTH_MAX, Math.max(TREE_WIDTH_MIN, width));
}

export function clampRightWidth(width: number): number {
  return Math.min(RIGHT_WIDTH_MAX, Math.max(RIGHT_WIDTH_MIN, width));
}

export function computeResizedWidth(side: 'left' | 'right', startWidth: number, deltaX: number): number {
  return side === 'left' ? clampTreeWidth(startWidth + deltaX) : clampRightWidth(startWidth - deltaX);
}
