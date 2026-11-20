import { beforeEach, describe, expect, it, vi } from 'vitest';

const { sanitizeMock } = vi.hoisted(() => ({
  sanitizeMock: vi.fn((html: string) => html),
}));

vi.mock('dompurify', () => ({
  default: { sanitize: sanitizeMock },
}));

import { renderInlineMarkdown, renderMarkdown, sanitizeSvg } from './markdown-renderer';

beforeEach(() => {
  sanitizeMock.mockClear();
  sanitizeMock.mockImplementation((html: string) => html);
});

describe('renderMarkdown', () => {
  it('renders GFM headings, links, image embeds, and task lists', () => {
    const md = [
      '# Heading',
      '',
      '[Docs](https://example.com) and ![Diagram](diagram.png)',
      '',
      '- [ ] Open task',
      '- [x] Done task',
    ].join('\n');

    const output = renderMarkdown(md);

    expect(output).toContain('<h1>Heading</h1>');
    expect(output).toContain('<a href="https://example.com">Docs</a>');
    expect(output).toContain('<img src="diagram.png" alt="Diagram">');
    expect(output).toContain('<input disabled="" type="checkbox"> Open task');
    expect(output).toContain('<input checked="" disabled="" type="checkbox"> Done task');
  });

  it('preserves single line breaks without inserting <br> (breaks: false)', () => {
    expect(renderMarkdown('line one\nline two')).toBe('<p>line one\nline two</p>\n');
  });

  it('passes rendered HTML through DOMPurify with the HTML profile and allowed attributes', () => {
    sanitizeMock.mockReturnValueOnce('<p>sanitized</p>');

    const output = renderMarkdown('hello <script>alert(1)</script>');

    expect(output).toBe('<p>sanitized</p>');
    expect(sanitizeMock).toHaveBeenCalledWith(
      expect.stringContaining('<script>alert(1)</script>'),
      { USE_PROFILES: { html: true }, ADD_ATTR: ['target', 'rel', 'data-target'] },
    );
  });
});

describe('renderInlineMarkdown', () => {
  it('renders inline formatting without a block <p> wrapper and sanitizes it', () => {
    const output = renderInlineMarkdown('**bold** and [link](https://example.com)');

    expect(output).toBe('<strong>bold</strong> and <a href="https://example.com">link</a>');
    expect(sanitizeMock).toHaveBeenCalledWith(
      '<strong>bold</strong> and <a href="https://example.com">link</a>',
      { USE_PROFILES: { html: true }, ADD_ATTR: ['target', 'rel', 'data-target'] },
    );
  });
});

describe('sanitizeSvg', () => {
  it('delegates SVG sanitization with svg and svgFilters profiles', () => {
    sanitizeMock.mockReturnValueOnce('<svg><g/></svg>');

    expect(sanitizeSvg('<svg><script/></svg>')).toBe('<svg><g/></svg>');
    expect(sanitizeMock).toHaveBeenCalledWith('<svg><script/></svg>', {
      USE_PROFILES: { svg: true, svgFilters: true },
    });
  });
});
