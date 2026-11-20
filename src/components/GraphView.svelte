<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { stepLayout, type Graph, type GraphNode } from '../lib/graph';

  let {
    graph,
    current,
    groupColors,
    hiddenGroups,
    onOpen,
    onToggleGroup,
  }: {
    graph: Graph;
    current: string | null;
    groupColors: Map<string, string>;
    hiddenGroups?: Set<string>;
    onOpen: (path: string) => void;
    onToggleGroup?: (group: string) => void;
  } = $props();

  let canvas: HTMLCanvasElement;
  let width = 0;
  let height = 0;
  let view = { x: 0, y: 0, k: 0.45 };
  let alpha = 1;
  let frame = 0;
  let hovered = -1;
  let autoFit = true;
  let drag: { mode: 'pan' | 'node'; node: number; startX: number; startY: number; moved: boolean } | null = null;
  let theme = { edge: '', node: '', text: '', accent: '', font: '' };
  let observer: ResizeObserver;

  const HUB_LABELS = 12;
  const hubs = $derived(new Set(graph.nodes.map((node, i) => [node.degree, i]).sort((a, b) => b[0] - a[0]).slice(0, HUB_LABELS).map(([, i]) => i)));

  const radius = (node: GraphNode): number => (2 + Math.sqrt(node.degree)) * Math.min(Math.max(view.k, 0.5), 2);
  const toScreen = (node: GraphNode): [number, number] => [width / 2 + view.x + node.x * view.k, height / 2 + view.y + node.y * view.k];
  const toWorld = (sx: number, sy: number): [number, number] => [(sx - width / 2 - view.x) / view.k, (sy - height / 2 - view.y) / view.k];

  function nodeAt(sx: number, sy: number): number {
    const [wx, wy] = toWorld(sx, sy);
    let best = -1;
    let bestDist = Infinity;
    graph.nodes.forEach((node, i) => {
      const d = Math.hypot(node.x - wx, node.y - wy);
      if (d < bestDist && d * view.k <= radius(node) + 4) { best = i; bestDist = d; }
    });
    return best;
  }

  function draw(): void {
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const dpr = window.devicePixelRatio || 1;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    const focus = hovered >= 0 ? graph.neighbors[hovered] : null;
    const active = (i: number): boolean => !focus || i === hovered || focus.has(i);

    ctx.lineWidth = 1;
    for (const { source, target } of graph.edges) {
      const lit = focus && (source === hovered || target === hovered);
      ctx.strokeStyle = lit ? theme.accent : theme.edge;
      ctx.globalAlpha = lit ? 0.9 : focus ? 0.04 : 0.12;
      const [x1, y1] = toScreen(graph.nodes[source]);
      const [x2, y2] = toScreen(graph.nodes[target]);
      ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
    }

    ctx.font = theme.font;
    ctx.textAlign = 'center';
    const labels: { i: number; x: number; y: number; priority: number }[] = [];
    graph.nodes.forEach((node, i) => {
      const [x, y] = toScreen(node);
      const r = radius(node);
      const isCurrent = node.id === current;
      ctx.globalAlpha = active(i) ? 1 : 0.12;
      ctx.fillStyle = groupColors.get(node.group) ?? theme.node;
      ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
      if (isCurrent || i === hovered) { ctx.strokeStyle = theme.text; ctx.lineWidth = 2; ctx.stroke(); ctx.lineWidth = 1; }
      if (view.k > 1.3 || i === hovered || isCurrent || (focus ? focus.has(i) : hubs.has(i))) {
        labels.push({ i, x, y: y + r + 12, priority: i === hovered ? Infinity : isCurrent ? 1e9 : node.degree });
      }
    });
    // Place labels by priority and skip any that would overlap one already drawn.
    ctx.globalAlpha = 1;
    ctx.fillStyle = theme.text;
    const placed: [number, number, number, number][] = [];
    for (const { i, x, y } of labels.sort((a, b) => b.priority - a.priority)) {
      const w = ctx.measureText(graph.nodes[i].label).width / 2 + 3;
      if (placed.some(([x0, y0, x1, y1]) => x - w < x1 && x + w > x0 && y - 11 < y1 && y + 3 > y0)) continue;
      placed.push([x - w, y - 11, x + w, y + 3]);
      ctx.fillText(graph.nodes[i].label, x, y);
    }
  }

  function loop(): void {
    if (alpha > 0.005) {
      stepLayout(graph, alpha);
      alpha *= 0.985;
      if (autoFit) fit();
    }
    draw();
    frame = requestAnimationFrame(loop);
  }

  function fit(): void {
    if (!graph.nodes.length || !width) return;
    let [minX, minY, maxX, maxY] = [Infinity, Infinity, -Infinity, -Infinity];
    for (const { x, y } of graph.nodes) { minX = Math.min(minX, x); minY = Math.min(minY, y); maxX = Math.max(maxX, x); maxY = Math.max(maxY, y); }
    view.k = Math.min((width - 80) / Math.max(maxX - minX, 1), (height - 80) / Math.max(maxY - minY, 1), 2);
    view.x = -((minX + maxX) / 2) * view.k;
    view.y = -((minY + maxY) / 2) * view.k;
  }

  function resize(): void {
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    width = rect.width;
    height = rect.height;
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
  }

  function pointerDown(event: PointerEvent): void {
    const node = nodeAt(event.offsetX, event.offsetY);
    if (node < 0) autoFit = false;
    drag = { mode: node >= 0 ? 'node' : 'pan', node, startX: event.offsetX, startY: event.offsetY, moved: false };
    if (node >= 0) graph.nodes[node].pinned = true;
    canvas.setPointerCapture(event.pointerId);
  }

  function pointerMove(event: PointerEvent): void {
    if (!drag) {
      hovered = nodeAt(event.offsetX, event.offsetY);
      canvas.style.cursor = hovered >= 0 ? 'pointer' : 'grab';
      return;
    }
    if (Math.hypot(event.offsetX - drag.startX, event.offsetY - drag.startY) > 3) drag.moved = true;
    if (drag.mode === 'pan') {
      view.x += event.movementX;
      view.y += event.movementY;
    } else {
      const [wx, wy] = toWorld(event.offsetX, event.offsetY);
      graph.nodes[drag.node].x = wx;
      graph.nodes[drag.node].y = wy;
      alpha = Math.max(alpha, 0.3);
    }
  }

  function pointerUp(): void {
    if (drag?.mode === 'node') {
      graph.nodes[drag.node].pinned = false;
      if (!drag.moved) onOpen(graph.nodes[drag.node].id);
    }
    drag = null;
  }

  function wheel(event: WheelEvent): void {
    event.preventDefault();
    autoFit = false;
    const [wx, wy] = toWorld(event.offsetX, event.offsetY);
    view.k = Math.min(Math.max(view.k * Math.exp(-event.deltaY * 0.0015), 0.1), 6);
    view.x = event.offsetX - width / 2 - wx * view.k;
    view.y = event.offsetY - height / 2 - wy * view.k;
  }

  onMount(() => {
    const style = getComputedStyle(canvas);
    theme = { edge: style.getPropertyValue('--text-dim').trim() || '#555', node: style.getPropertyValue('--text-sec').trim() || '#aaa', text: style.getPropertyValue('--text-pri').trim() || '#eee', accent: style.getPropertyValue('--accent').trim() || '#c74', font: `11px ${style.fontFamily}` };
    observer = new ResizeObserver(resize);
    observer.observe(canvas);
    resize();
    frame = requestAnimationFrame(loop);
  });

  onDestroy(() => {
    cancelAnimationFrame(frame);
    observer?.disconnect();
  });
</script>

<div class="graph-view">
  <canvas class="graph-canvas" bind:this={canvas} onpointerdown={pointerDown} onpointermove={pointerMove} onpointerup={pointerUp} onpointerleave={() => { if (!drag) hovered = -1; }} onwheel={wheel}></canvas>
  {#if onToggleGroup}
    <ul class="graph-legend">
      {#each groupColors as [group, color]}
        <li><button type="button" class:off={hiddenGroups?.has(group)} onclick={() => onToggleGroup(group)} title="Show or hide this folder"><span style={`background:${color}`}></span>{group || '(root)'}</button></li>
      {/each}
    </ul>
  {/if}
</div>
