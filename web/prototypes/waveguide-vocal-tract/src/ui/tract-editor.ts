import { NUM_SECTIONS, MIN_AREA, MAX_AREA } from "../audio/vowel-presets";

type AreasChangeCallback = (areas: number[]) => void;
export type EditorMode = "manual" | "magnet";

// 44 セクションでは制御点が密集するため小さめの半径に
const CP_RADIUS = 5;
const WALL_COLOR = "#6b7280";
const LUMEN_COLOR = "#f0f4f8";
const CP_COLOR = "#3b82f6";
const CP_HOVER_COLOR = "#60a5fa";
const CP_DRAG_COLOR  = "#1d4ed8";
const BORDER_COLOR   = "#374151";
const MAGNET_COLOR   = "rgba(251,191,36,0.18)";
const MAGNET_RING    = "rgba(251,191,36,0.55)";

function clamp(v: number): number {
  return Math.max(MIN_AREA, Math.min(MAX_AREA, v));
}

export class TractEditor {
  private canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private areas: number[];
  private targetAreas: number[];
  private animating = false;
  private animStartTime = 0;
  private readonly animDuration = 300;
  private animFromAreas: number[] = [];
  private draggingIndex = -1;
  private hoverIndex = -1;
  private onAreasChange: AreasChangeCallback;

  // マグネット
  private mode: EditorMode = "manual";
  private magnetRadius = 100;  // canvas px
  private magnetStrength = 1.0;
  private isDraggingMagnet = false;
  private prevDragY = -1;
  private magnetCursorX = -1;
  private magnetCursorY = -1;

  constructor(
    canvas: HTMLCanvasElement,
    initialAreas: number[],
    onChange: AreasChangeCallback
  ) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d")!;
    this.areas = [...initialAreas];
    this.targetAreas = [...initialAreas];
    this.onAreasChange = onChange;
    this.setupEvents();
    this.draw();
  }

  setMode(mode: EditorMode): void {
    this.mode = mode;
    this.draggingIndex = -1;
    this.isDraggingMagnet = false;
    this.magnetCursorX = -1;
    this.magnetCursorY = -1;
    this.canvas.style.cursor = mode === "magnet" ? "none" : "crosshair";
    this.draw();
  }

  setMagnetRadius(px: number): void {
    this.magnetRadius = px;
    this.draw();
  }

  setMagnetStrength(v: number): void {
    this.magnetStrength = v;
  }

  private cpX(i: number): number {
    const pad = 20;
    return pad + (i / (NUM_SECTIONS - 1)) * (this.canvas.width - pad * 2);
  }

  private areaToHalf(area: number): number {
    return (area / MAX_AREA) * (this.canvas.height / 2) * 0.82;
  }

  private yToArea(cy: number): number {
    const half = this.canvas.height / 2 - cy;
    return Math.max(MIN_AREA, Math.min(MAX_AREA, (half / ((this.canvas.height / 2) * 0.82)) * MAX_AREA));
  }

  private hitTest(cx: number, cy: number): number {
    const cy0 = this.canvas.height / 2;
    for (let i = 0; i < NUM_SECTIONS; i++) {
      const dx = cx - this.cpX(i);
      const dy = cy - (cy0 - this.areaToHalf(this.areas[i]));
      if (dx * dx + dy * dy <= (CP_RADIUS + 5) ** 2) return i;
    }
    return -1;
  }

  private getPos(e: MouseEvent | TouchEvent): { x: number; y: number } {
    const rect = this.canvas.getBoundingClientRect();
    const sx = this.canvas.width / rect.width;
    const sy = this.canvas.height / rect.height;
    if (e instanceof MouseEvent) {
      return { x: (e.clientX - rect.left) * sx, y: (e.clientY - rect.top) * sy };
    }
    const t = e.touches[0];
    return { x: (t.clientX - rect.left) * sx, y: (t.clientY - rect.top) * sy };
  }

  private applyMagnet(cx: number, deltaY: number): void {
    const maxHalf = (this.canvas.height / 2) * 0.82;
    // deltaY > 0（下ドラッグ）→ 断面積減少
    const deltaArea = -(deltaY / maxHalf) * MAX_AREA * this.magnetStrength;
    for (let i = 0; i < NUM_SECTIONS; i++) {
      const dist = Math.abs(this.cpX(i) - cx);
      if (dist >= this.magnetRadius) continue;
      const t = dist / this.magnetRadius;
      const weight = 0.5 * (1 + Math.cos(Math.PI * t)); // コサインベル
      this.areas[i] = clamp(this.areas[i] + deltaArea * weight);
    }
  }

  private setupEvents(): void {
    const c = this.canvas;

    const down = (e: MouseEvent | TouchEvent) => {
      e.preventDefault();
      const { x, y } = this.getPos(e);
      if (this.mode === "magnet") {
        this.isDraggingMagnet = true;
        this.prevDragY = y;
        this.magnetCursorX = x;
        this.magnetCursorY = y;
      } else {
        this.draggingIndex = this.hitTest(x, y);
      }
    };

    const move = (e: MouseEvent | TouchEvent) => {
      e.preventDefault();
      const { x, y } = this.getPos(e);
      if (this.mode === "magnet") {
        this.magnetCursorX = x;
        this.magnetCursorY = y;
        if (this.isDraggingMagnet) {
          const deltaY = y - this.prevDragY;
          this.prevDragY = y;
          this.applyMagnet(x, deltaY);
          this.onAreasChange([...this.areas]);
        }
        this.draw();
      } else {
        if (this.draggingIndex >= 0) {
          this.areas[this.draggingIndex] = this.yToArea(y);
          this.onAreasChange([...this.areas]);
          this.draw();
        } else {
          const prev = this.hoverIndex;
          this.hoverIndex = this.hitTest(x, y);
          if (prev !== this.hoverIndex) this.draw();
        }
      }
    };

    const up = () => {
      this.draggingIndex = -1;
      this.isDraggingMagnet = false;
      this.prevDragY = -1;
    };

    const leave = () => {
      up();
      if (this.mode === "magnet") {
        this.magnetCursorX = -1;
        this.magnetCursorY = -1;
        this.draw();
      }
    };

    c.addEventListener("mousedown", down);
    c.addEventListener("mousemove", move);
    c.addEventListener("mouseup", up);
    c.addEventListener("mouseleave", leave);
    c.addEventListener("touchstart", down, { passive: false });
    c.addEventListener("touchmove", move, { passive: false });
    c.addEventListener("touchend", up);
  }

  private draw(): void {
    const { canvas, ctx } = this;
    const W = canvas.width;
    const H = canvas.height;
    const cy = H / 2;
    const WALL = 16;

    ctx.clearRect(0, 0, W, H);

    const xs = Array.from({ length: NUM_SECTIONS }, (_, i) => this.cpX(i));
    const hs = this.areas.map(a => this.areaToHalf(a));

    // ── 管腔（白い空洞）─────────────────────────────────────
    ctx.beginPath();
    ctx.moveTo(xs[0], cy - hs[0]);
    for (let i = 1; i < NUM_SECTIONS; i++) {
      ctx.lineTo(xs[i], cy - hs[i]);
    }
    ctx.lineTo(xs[NUM_SECTIONS - 1], cy + hs[NUM_SECTIONS - 1]);
    for (let i = NUM_SECTIONS - 2; i >= 0; i--) {
      ctx.lineTo(xs[i], cy + hs[i]);
    }
    ctx.closePath();
    ctx.fillStyle = LUMEN_COLOR;
    ctx.fill();
    ctx.strokeStyle = BORDER_COLOR;
    ctx.lineWidth = 1;
    ctx.stroke();

    // ── 上壁（肉）──────────────────────────────────────────
    ctx.beginPath();
    ctx.moveTo(xs[0], cy - hs[0]);
    for (let i = 1; i < NUM_SECTIONS; i++) ctx.lineTo(xs[i], cy - hs[i]);
    ctx.lineTo(xs[NUM_SECTIONS - 1], cy - hs[NUM_SECTIONS - 1] - WALL);
    for (let i = NUM_SECTIONS - 2; i >= 0; i--) ctx.lineTo(xs[i], cy - hs[i] - WALL);
    ctx.closePath();
    ctx.fillStyle = WALL_COLOR;
    ctx.fill();

    // ── 下壁（肉）──────────────────────────────────────────
    ctx.beginPath();
    ctx.moveTo(xs[0], cy + hs[0]);
    for (let i = 1; i < NUM_SECTIONS; i++) ctx.lineTo(xs[i], cy + hs[i]);
    ctx.lineTo(xs[NUM_SECTIONS - 1], cy + hs[NUM_SECTIONS - 1] + WALL);
    for (let i = NUM_SECTIONS - 2; i >= 0; i--) ctx.lineTo(xs[i], cy + hs[i] + WALL);
    ctx.closePath();
    ctx.fillStyle = WALL_COLOR;
    ctx.fill();

    // ── ラベル ──────────────────────────────────────────────
    ctx.fillStyle = "#9ca3af";
    ctx.font = "11px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("声帯", xs[0], H - 4);
    ctx.fillText("口", xs[NUM_SECTIONS - 1], H - 4);

    if (this.mode === "manual") {
      // ── 制御点（上壁上）────────────────────────────────────
      for (let i = 0; i < NUM_SECTIONS; i++) {
        const x = xs[i];
        const y = cy - hs[i];
        let col = CP_COLOR;
        if (i === this.draggingIndex) col = CP_DRAG_COLOR;
        else if (i === this.hoverIndex) col = CP_HOVER_COLOR;
        ctx.beginPath();
        ctx.arc(x, y, CP_RADIUS, 0, Math.PI * 2);
        ctx.fillStyle = col;
        ctx.fill();
        ctx.strokeStyle = "#fff";
        ctx.lineWidth = 1;
        ctx.stroke();
      }
    } else {
      // ── マグネットカーソルオーバーレイ ────────────────────
      if (this.magnetCursorX >= 0) {
        const mx = this.magnetCursorX;
        const my = this.magnetCursorY;
        const r = this.magnetRadius;

        // 影響範囲の円（塗り）
        ctx.beginPath();
        ctx.ellipse(mx, cy, r, H * 0.46, 0, 0, Math.PI * 2);
        ctx.fillStyle = MAGNET_COLOR;
        ctx.fill();

        // 影響範囲の円（縁）
        ctx.beginPath();
        ctx.ellipse(mx, cy, r, H * 0.46, 0, 0, Math.PI * 2);
        ctx.strokeStyle = MAGNET_RING;
        ctx.lineWidth = 1.5;
        ctx.setLineDash([4, 3]);
        ctx.stroke();
        ctx.setLineDash([]);

        // カーソル中心十字
        ctx.strokeStyle = "rgba(251,191,36,0.9)";
        ctx.lineWidth = 1.5;
        const cs = 6;
        ctx.beginPath();
        ctx.moveTo(mx - cs, my); ctx.lineTo(mx + cs, my);
        ctx.moveTo(mx, my - cs); ctx.lineTo(mx, my + cs);
        ctx.stroke();
      }
    }
  }

  setAreas(newAreas: number[], animate = true): void {
    if (!animate) {
      this.areas = [...newAreas];
      this.targetAreas = [...newAreas];
      this.draw();
      return;
    }
    this.animFromAreas = [...this.areas];
    this.targetAreas = [...newAreas];
    this.animStartTime = performance.now();
    this.animating = true;
    this.tick();
  }

  private tick(): void {
    if (!this.animating) return;
    const t = Math.min(1, (performance.now() - this.animStartTime) / this.animDuration);
    const e = 1 - Math.pow(1 - t, 3); // ease-out cubic
    for (let i = 0; i < NUM_SECTIONS; i++) {
      this.areas[i] = this.animFromAreas[i] + (this.targetAreas[i] - this.animFromAreas[i]) * e;
    }
    this.onAreasChange([...this.areas]);
    this.draw();
    if (t < 1) {
      requestAnimationFrame(() => this.tick());
    } else {
      this.animating = false;
      this.areas = [...this.targetAreas];
    }
  }

  getAreas(): number[] { return [...this.areas]; }
}
