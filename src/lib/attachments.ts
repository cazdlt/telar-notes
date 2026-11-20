export function encodeBase64(bytes: Uint8Array): string {
  // Chunked: a per-byte string concat stalls for seconds on multi-MB screenshots.
  let binary = '';
  for (let offset = 0; offset < bytes.length; offset += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
  }
  return btoa(binary);
}

/**
 * Clipboard screenshots all arrive named "image.png"; timestamp them like Obsidian
 * does so a note can hold more than one.
 */
export function pastedImageName(file: { name: string; type: string }, now = new Date()): string {
  const dot = file.name.lastIndexOf('.');
  const extension = dot > 0 ? file.name.slice(dot) : `.${file.type.split('/')[1] || 'png'}`;
  if (dot > 0 && file.name.slice(0, dot).toLowerCase() !== 'image') return file.name;
  const stamp = [
    now.getFullYear(),
    now.getMonth() + 1,
    now.getDate(),
    now.getHours(),
    now.getMinutes(),
    now.getSeconds(),
  ]
    .map((part, index) => String(part).padStart(index ? 2 : 4, '0'))
    .join('');
  return `Pasted image ${stamp}${extension}`;
}
