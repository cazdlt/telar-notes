import { StateEffect } from '@codemirror/state';
import type { DecorationSet } from '@codemirror/view';

export type LivePreviewOptions = {
  currentPath: string;
  files: () => ReadonlySet<string>;
  reading: () => boolean;
  persistent: () => boolean;
  drawings: () => boolean;
  drawingWidth: () => number;
  openFile: (path: string, anchor?: string, line?: number) => void;
  openDrawing: (path: string) => void;
  missingLink: (target: string) => void;
};

export type BlockRange = { from: number; to: number };
export type FoldKind = 'heading' | 'callout' | 'list';
export type FoldTarget = { kind: FoldKind; from: number };
export type FoldSection = FoldTarget & { first: number; last: number; defaultCollapsed: boolean };

export type LivePreviewState = {
  decorations: DecorationSet;
  atomic: DecorationSet;
  folded: FoldTarget[];
  frontmatterOpen: boolean;
  revealedBlocks: BlockRange[];
};

export type ResolvedLink = { path: string; exists: boolean; anchor?: string };

export type CodeTreeNode = {
  getChildren: (name: string) => ReadonlyArray<{ from: number; to: number }>;
};

export type TextDocument = { sliceString: (from: number, to: number) => string };

export type TreeNode = { name: string; parent: TreeNode | null };

export type LinkedTextPart =
  | { kind: 'text'; value: string }
  | { kind: 'wikilink'; target: string; label: string };

// Shows a rendered block's source until the caret leaves it, even in persistent mode.
export const revealBlock = StateEffect.define<BlockRange>();
