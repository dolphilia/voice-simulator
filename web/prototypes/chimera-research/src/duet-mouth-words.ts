import type { Word } from "./duet-words";

const fadeSeconds = 0.45;
const trailLimit = 8;
type Entry = { word: Word; left: number | null };

// 退場する語の時間式と配置は固定上流の src/ui/mouthWords.ts を参照
// （Jameson Hodge、MIT。研究ワークスペースの LICENSE-CHIMERA）。
export class DuetMouthTrail {
  readonly entries: Entry[] = [];

  update(word: Word | null, seconds: number, reset = false) {
    const entries = this.entries;
    if (reset) entries.length = 0;
    const current = entries.at(-1);
    if (current && word?.key === current.word.key) {
      current.left = null;
    } else {
      if (current?.left === null) current.left = seconds;
      if (word) entries.push({ word, left: null });
    }
    while (entries.length > trailLimit || (entries[0]?.left != null && seconds - entries[0].left > fadeSeconds)) {
      entries.shift();
    }
  }
}

export type DuetMouthView = { x: number; y: number; width: number; height: number; pxPerCm: number };
type Clock = { epoch: number; time: number };
type Label = {
  key: number; text: string; age: number; x: number; y: number; size: number; alpha: number; left: number | null;
};

export function createDuetMouthOverlay(layer: HTMLDivElement, viewAtMouth: () => DuetMouthView, facing: 1 | -1) {
  const trail = new DuetMouthTrail();
  const measure = document.createElement("canvas").getContext("2d");
  const labels = new Map<Entry, HTMLSpanElement>();
  const guide = document.createElement("i");
  guide.className = "duet-mouth-guide";
  guide.hidden = true;
  layer.append(guide);
  let frame = 0;
  let latest: Clock | undefined;
  let word: Word | null = null;
  let snapshot: { view: DuetMouthView; below: boolean; ahead: number; labels: Label[]; seconds: number } | undefined;

  function draw(seconds: number) {
    const view = viewAtMouth();
    const { x: lx, y: ly, width, height, pxPerCm } = view;
    const gap = 1.2 * pxPerCm;
    const start = lx + facing * gap;
    const ahead = (facing > 0 ? width - start : start) - 14;
    const below = ahead < 60;
    const room = below ? width - 16 : ahead;
    const base = Math.max(26, Math.min(64, pxPerCm * 1.7));
    const bottom = Math.min(height - 14, ly + pxPerCm * 18);
    const active = new Set(trail.entries);
    for (const [entry, label] of labels) {
      if (active.has(entry)) continue;
      label.remove();
      labels.delete(entry);
    }
    const drawn: Label[] = [];
    for (const entry of trail.entries) {
      const { word: current, left } = entry;
      const age = left === null ? 0 : seconds - left;
      const progress = Math.min(1, age / fadeSeconds);
      const text = current.text.toUpperCase();
      if (measure) measure.font = `600 ${base}px system-ui`;
      const widthAtBase = (measure?.measureText(text).width ?? base * text.length) * 1.08;
      const shrink = 1 - 0.55 * progress;
      const widthForLayout = Math.min(widthAtBase, room) * shrink;
      const size = base * Math.min(1, room / Math.max(1, widthAtBase)) * shrink;
      const alpha = left === null ? 1 : 0.75 * (1 - progress) ** 1.5;
      const half = widthForLayout / 2;
      const x = below ? Math.min(width - 8 - half, Math.max(8 + half, lx)) : start + facing * age * 240;
      const y = below ? bottom + age * 120 : ly + size * 0.36 - age * 200;
      let label = labels.get(entry);
      if (!label) {
        label = document.createElement("span");
        label.className = "duet-mouth-word";
        label.textContent = text;
        labels.set(entry, label);
        layer.append(label);
      }
      label.dataset.wordKey = String(current.key);
      label.dataset.departing = String(left !== null);
      const horizontal = below ? "-50%" : facing > 0 ? "0%" : "-100%";
      label.style.left = `${x}px`;
      label.style.top = `${y}px`;
      label.style.transform = `translate(${horizontal}, -0.8em)`;
      label.style.fontSize = `${size}px`;
      label.style.opacity = String(alpha);
      drawn.push({ key: current.key, text, age, x, y, size, alpha, left });
    }
    guide.hidden = below || !word || gap <= 8;
    if (!guide.hidden) {
      guide.style.left = `${Math.min(lx, start) + 4}px`;
      guide.style.top = `${ly}px`;
      guide.style.width = `${gap - 8}px`;
    }
    snapshot = { view, below, ahead, labels: drawn, seconds };
  }

  function animate() {
    const seconds = performance.now() / 1000;
    trail.update(word, seconds);
    draw(seconds);
    frame = trail.entries.some(({ left }) => left !== null) ? requestAnimationFrame(animate) : 0;
  }

  return {
    update(next: Word | null, clock: Clock) {
      const seconds = performance.now() / 1000;
      const reset = latest?.epoch !== clock.epoch || clock.time < latest.time;
      latest = clock;
      word = next;
      trail.update(word, seconds, reset);
      draw(seconds);
      if (!frame && trail.entries.some(({ left }) => left !== null)) frame = requestAnimationFrame(animate);
    },
    resize() {
      if (latest) draw(performance.now() / 1000);
    },
    read() {
      return snapshot;
    },
    dispose() {
      cancelAnimationFrame(frame);
      layer.replaceChildren();
    },
  };
}
