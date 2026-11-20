import { describe, expect, it } from 'vitest';
import { encodeBase64, pastedImageName } from './attachments';

describe('attachments', () => {
  it('encodes multi-chunk Uint8Array to base64', () => {
    const bytes = new Uint8Array(0x8000 + 5);
    bytes.fill(65); // 'A'
    const encoded = encodeBase64(bytes);
    expect(encoded.length).toBeGreaterThan(0);
    expect(atob(encoded).length).toBe(bytes.length);
  });

  it('timestamps generic clipboard image names and preserves custom filenames', () => {
    const now = new Date(2026, 0, 5, 9, 4, 3);
    expect(pastedImageName({ name: 'image.png', type: 'image/png' }, now)).toBe('Pasted image 20260105090403.png');
    expect(pastedImageName({ name: 'blob', type: 'image/webp' }, now)).toBe('Pasted image 20260105090403.webp');
    expect(pastedImageName({ name: 'diagram.png', type: 'image/png' }, now)).toBe('diagram.png');
  });
});
