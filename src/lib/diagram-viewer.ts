export type View = { x: number; y: number; k: number };

const MIN_SCALE = 0.1;
const MAX_SCALE = 8;

export function clampScale(k: number): number {
  return Math.min(Math.max(k, MIN_SCALE), MAX_SCALE);
}

/** Zoom by `factor` keeping the viewport point (px, py) fixed on the content. */
export function zoomAt(view: View, factor: number, px: number, py: number): View {
  const k = clampScale(view.k * factor);
  const ratio = k / view.k;
  return { k, x: px - (px - view.x) * ratio, y: py - (py - view.y) * ratio };
}

/** Scale and center content of the given size inside the viewport. */
export function fitView(contentW: number, contentH: number, viewportW: number, viewportH: number, padding = 32): View {
  const k = clampScale(Math.min((viewportW - 2 * padding) / contentW, (viewportH - 2 * padding) / contentH));
  return { k, x: (viewportW - contentW * k) / 2, y: (viewportH - contentH * k) / 2 };
}

function svgSize(svg: SVGSVGElement): [number, number] {
  const box = svg.viewBox.baseVal;
  if (box && box.width > 0 && box.height > 0) return [box.width, box.height];
  return [parseFloat(svg.getAttribute('width') ?? '') || 800, parseFloat(svg.getAttribute('height') ?? '') || 600];
}

/** Fullscreen pan/zoom viewer for an already-sanitized SVG string. */
export function openDiagramViewer(svgMarkup: string): void {
  const overlay = document.createElement('div');
  overlay.id = 'diagram-viewer';
  overlay.tabIndex = -1;
  overlay.setAttribute('role', 'dialog');
  overlay.setAttribute('aria-label', 'Diagram viewer');
  const stage = document.createElement('div');
  stage.className = 'dv-stage';
  stage.innerHTML = svgMarkup;
  const svg = stage.querySelector('svg');
  if (!svg) return;
  const [width, height] = svgSize(svg);
  svg.removeAttribute('style');
  svg.setAttribute('width', String(width));
  svg.setAttribute('height', String(height));
  const viewport = document.createElement('div');
  viewport.className = 'dv-viewport';
  viewport.append(stage);

  const toolbar = document.createElement('div');
  toolbar.className = 'dv-toolbar';
  const button = (label: string, title: string, action: () => void) => {
    const element = document.createElement('button');
    element.type = 'button';
    element.textContent = label;
    element.title = title;
    element.addEventListener('click', action);
    return element;
  };
  const percent = document.createElement('span');
  percent.className = 'dv-percent';

  let view: View = { x: 0, y: 0, k: 1 };
  const apply = () => {
    stage.style.transform = `translate(${view.x}px, ${view.y}px) scale(${view.k})`;
    percent.textContent = `${Math.round(view.k * 100)}%`;
  };
  const fit = () => { view = fitView(width, height, viewport.clientWidth, viewport.clientHeight); apply(); };
  const zoomCenter = (factor: number) => { view = zoomAt(view, factor, viewport.clientWidth / 2, viewport.clientHeight / 2); apply(); };
  const close = () => {
    window.removeEventListener('resize', fit);
    overlay.remove();
  };

  toolbar.append(button('−', 'Zoom out (-)', () => zoomCenter(1 / 1.25)), percent, button('+', 'Zoom in (+)', () => zoomCenter(1.25)), button('Fit', 'Fit to window (0)', fit), button('Close', 'Close (Esc)', close));
  overlay.append(viewport, toolbar);

  viewport.addEventListener('wheel', (event) => {
    event.preventDefault();
    const rect = viewport.getBoundingClientRect();
    view = zoomAt(view, Math.exp(-event.deltaY * 0.0015), event.clientX - rect.left, event.clientY - rect.top);
    apply();
  }, { passive: false });
  let drag: { x: number; y: number; origin: View } | null = null;
  viewport.addEventListener('pointerdown', (event) => {
    drag = { x: event.clientX, y: event.clientY, origin: view };
    viewport.setPointerCapture(event.pointerId);
    viewport.classList.add('dragging');
  });
  viewport.addEventListener('pointermove', (event) => {
    if (!drag) return;
    view = { ...drag.origin, x: drag.origin.x + event.clientX - drag.x, y: drag.origin.y + event.clientY - drag.y };
    apply();
  });
  const endDrag = () => { drag = null; viewport.classList.remove('dragging'); };
  viewport.addEventListener('pointerup', endDrag);
  viewport.addEventListener('pointercancel', endDrag);
  viewport.addEventListener('dblclick', fit);
  overlay.addEventListener('keydown', (event) => {
    event.stopPropagation();
    if (event.key === 'Escape') close();
    else if (event.key === '+' || event.key === '=') zoomCenter(1.25);
    else if (event.key === '-') zoomCenter(1 / 1.25);
    else if (event.key === '0') fit();
    else return;
    event.preventDefault();
  });
  window.addEventListener('resize', fit);

  document.body.append(overlay);
  fit();
  overlay.focus();
}
