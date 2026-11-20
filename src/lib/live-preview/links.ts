import { sanitizeUrl } from '@braintree/sanitize-url';
import { renderInlineMarkdown } from '../markdown-renderer';
import { resolveNotePath, resolveVaultPath } from '../paths';
import type { LinkedTextPart, LivePreviewOptions, ResolvedLink } from './types';

function splitTarget(target: string): { path: string; anchor?: string } {
  const hash = target.indexOf('#');
  if (hash < 0) return { path: target.trim() };
  return { path: target.slice(0, hash).trim(), anchor: target.slice(hash + 1).trim() || undefined };
}

export function resolveInternalLink(target: string, options: LivePreviewOptions, noteLink: boolean): ResolvedLink {
  const { path, anchor } = splitTarget(target);
  if (!path) return { path: options.currentPath, exists: options.files().has(options.currentPath), anchor };
  const resolved = noteLink
    ? resolveNotePath(path, options.currentPath, options.files())
    : resolveVaultPath(path, options.currentPath, options.files());
  return { ...resolved, anchor };
}

export function wikiParts(raw: string): { target: string; label: string } {
  const separator = raw.indexOf('|');
  if (separator < 0) return { target: raw.trim(), label: raw.trim() };
  return {
    target: raw.slice(0, separator).replace(/\\$/, '').trim(),
    label: raw.slice(separator + 1).trim(),
  };
}

export function linkedTextParts(raw: string): LinkedTextPart[] {
  const parts: LinkedTextPart[] = [];
  const pattern = /\[\[([^\]]+)\]\]/g;
  let position = 0;
  for (const match of raw.matchAll(pattern)) {
    const start = match.index ?? 0;
    if (start > position) parts.push({ kind: 'text', value: raw.slice(position, start) });
    const link = wikiParts(match[1]);
    parts.push({ kind: 'wikilink', ...link });
    position = start + match[0].length;
  }
  if (position < raw.length) parts.push({ kind: 'text', value: raw.slice(position) });
  return parts.length ? parts : [{ kind: 'text', value: raw }];
}

export function internalLinkButton(
  label: string,
  target: string,
  options: LivePreviewOptions,
  noteLink: boolean,
  table = false,
  sourcePath = options.currentPath,
): HTMLButtonElement {
  const resolved = resolveInternalLink(target, { ...options, currentPath: sourcePath }, noteLink);
  const button = document.createElement('button');
  button.type = 'button';
  button.className = `${table ? 'cm-tbl-wikilink ' : ''}cm-wikilink${resolved.exists ? '' : ' cm-wikilink-missing'}`;
  button.textContent = label;
  button.addEventListener('mousedown', (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (resolved.exists) options.openFile(resolved.path, resolved.anchor);
    else options.missingLink(target);
  });
  button.addEventListener('click', (event) => event.stopPropagation());
  return button;
}

export function appendLinkedText(
  container: HTMLElement,
  value: string,
  options: LivePreviewOptions,
  sourcePath: string,
  onPlainText?: () => void,
): void {
  for (const part of linkedTextParts(value)) {
    if (part.kind === 'wikilink') {
      container.append(internalLinkButton(part.label, part.target, options, true, false, sourcePath));
    } else if (onPlainText) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'cm-tasks-open';
      button.textContent = part.value;
      button.onclick = onPlainText;
      container.append(button);
    } else {
      container.append(part.value);
    }
  }
}

export function renderTaskDescription(
  container: HTMLElement,
  value: string,
  options: LivePreviewOptions,
  sourcePath: string,
  openSource: () => void,
): void {
  container.innerHTML = renderInlineMarkdown(value);
  container.tabIndex = 0;
  container.setAttribute('aria-label', `${value}. Open source task`);
  container.onclick = (event) => {
    if (!(event.target as Element).closest('a, button')) openSource();
  };
  container.onkeydown = (event) => {
    if (event.target === container && (event.key === 'Enter' || event.key === ' ')) {
      event.preventDefault();
      openSource();
    }
  };
  enhanceRenderedMarkdown(container, options, { sourcePath, stopExternalPropagation: true });
}

export function enhanceRenderedMarkdown(
  wrapper: HTMLElement,
  options: LivePreviewOptions,
  context: { sourcePath?: string; table?: boolean; stopExternalPropagation?: boolean } = {},
): void {
  const sourcePath = context.sourcePath ?? options.currentPath;
  const table = context.table ?? false;
  wrapper.querySelectorAll<HTMLAnchorElement>('a').forEach((anchor) => {
    const href = anchor.getAttribute('href') || '';
    if (/^(?:https?:|mailto:)/i.test(href)) {
      anchor.href = sanitizeUrl(href);
      anchor.target = '_blank';
      anchor.rel = 'noopener noreferrer';
      if (context.stopExternalPropagation) anchor.onclick = (event) => event.stopPropagation();
      return;
    }
    anchor.replaceWith(internalLinkButton(anchor.textContent || href, href, options, false, table, sourcePath));
  });

  const walker = document.createTreeWalker(wrapper, NodeFilter.SHOW_TEXT);
  const textNodes: Text[] = [];
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const parent = node.parentElement;
    if (parent && !parent.closest('a, button, code, pre')) textNodes.push(node as Text);
  }
  const inlinePattern = /\[\[([^\]]+)\]\]|(^|\s)(#[A-Za-z0-9_/-]+)/g;
  for (const node of textNodes) {
    const source = node.data;
    const matches = [...source.matchAll(inlinePattern)];
    if (!matches.length) continue;
    const fragment = document.createDocumentFragment();
    let position = 0;
    for (const match of matches) {
      const start = match.index ?? 0;
      fragment.append(source.slice(position, start));
      if (match[1]) {
        const wiki = wikiParts(match[1]);
        fragment.append(internalLinkButton(wiki.label, wiki.target, options, true, table, sourcePath));
      } else {
        fragment.append(match[2] || '');
        const tag = document.createElement('span');
        tag.className = table ? 'cm-tbl-tag' : 'cm-task-tag';
        tag.textContent = match[3];
        fragment.append(tag);
      }
      position = start + match[0].length;
    }
    fragment.append(source.slice(position));
    node.replaceWith(fragment);
  }
}
