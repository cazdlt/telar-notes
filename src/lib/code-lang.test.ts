import { CompletionContext } from '@codemirror/autocomplete';
import { markdown } from '@codemirror/lang-markdown';
import { EditorState } from '@codemirror/state';
import { describe, expect, it } from 'vitest';
import {
  codeLanguageCompletionSource,
  codeLanguageOptions,
  fenceInfoChange,
} from './code-lang';
import { ObsidianGFM } from './tasks';

function query(doc: string, pos: number, explicit = true) {
  const state = EditorState.create({ doc, extensions: [markdown({ extensions: ObsidianGFM })] });
  const source = codeLanguageCompletionSource();
  return source(new CompletionContext(state, pos, explicit));
}

describe('codeLanguageOptions', () => {
  it('starts with plain code option and common languages', () => {
    const options = codeLanguageOptions();
    expect(options[0]).toEqual({ id: '', label: 'code' });
    expect(options.some((opt) => opt.id === 'sql')).toBe(true);
    expect(options.some((opt) => opt.id === 'python')).toBe(true);
  });

  it('appends non-common current language so it remains selectable', () => {
    const options = codeLanguageOptions('haskell');
    expect(options[options.length - 1]).toEqual({ id: 'haskell', label: 'haskell' });
  });
});

describe('fenceInfoChange', () => {
  it('replaces or inserts the language info string while preserving prefix', () => {
    expect(fenceInfoChange('```', 10, 'sql')).toEqual({ from: 13, to: 13, insert: 'sql' });
    expect(fenceInfoChange('  > ```python', 20, 'bash')).toEqual({ from: 27, to: 33, insert: 'bash' });
    expect(fenceInfoChange('~~~json', 0, '')).toEqual({ from: 3, to: 7, insert: '' });
  });

  it('returns null for non-fence lines', () => {
    expect(fenceInfoChange('SELECT * FROM users;', 0, 'sql')).toBeNull();
  });
});

describe('codeLanguageCompletionSource', () => {
  it('suggests matching languages after opening backticks', async () => {
    const result = await query('```sq', 5);
    expect(result).not.toBeNull();
    expect(result?.from).toBe(3);
    expect(result?.options.some((opt) => opt.label === 'sql')).toBe(true);
  });

  it('does not trigger on closing fences of an existing code block', async () => {
    const doc = '```sql\nSELECT 1;\n```';
    const result = await query(doc, doc.length);
    expect(result).toBeNull();
  });

  it('does not trigger on normal prose lines', async () => {
    const result = await query('hello world', 5);
    expect(result).toBeNull();
  });
});
