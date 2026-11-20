import { describe, expect, it } from 'vitest';
import { titleFromContent, uniqueNotePath } from './untitled';

describe('titleFromContent', () => {
  it('prefers the first H1 over earlier lines', () => {
    expect(titleFromContent('intro\n\n# Hello\nbody')).toBe('Hello');
  });
  it('falls back to the first non-empty line and strips markers', () => {
    expect(titleFromContent('\n\n- [ ] Buy milk')).toBe('Buy milk');
    expect(titleFromContent('> quoted')).toBe('quoted');
    expect(titleFromContent('## Sub')).toBe('Sub');
  });
  it('skips front matter', () => {
    expect(titleFromContent('---\ntags: a\n---\n# Real')).toBe('Real');
  });
  it('removes illegal characters and caps the length', () => {
    expect(titleFromContent('# a/b:c*d?"e<f>g|h[i]#j^k')).toBe('abcdefghijk');
    expect(titleFromContent('x'.repeat(150))).toHaveLength(100);
  });
  it('is empty for blank content', () => {
    expect(titleFromContent('  \n\n')).toBe('');
    expect(titleFromContent('---\na: b\n---\n')).toBe('');
  });
});

describe('uniqueNotePath', () => {
  it('suffixes on collision', () => {
    const existing = new Set(['d/Untitled.md', 'd/Untitled 1.md']);
    expect(uniqueNotePath('d', 'Untitled', existing)).toBe('d/Untitled 2.md');
    expect(uniqueNotePath('', 'Untitled', new Set())).toBe('Untitled.md');
  });
});
