import { NUM_SECTIONS, MIN_AREA, MAX_AREA } from "../audio/vowel-presets";

type AreasChangeCallback = (areas: number[]) => void;

const CONTROL_POINT_RADIUS = 8;
const WALL_COLOR = "#6b7280";
const LUMEN_COLOR = "#f9fafb";
const CONTROL_POINT_COLOR = "#3b82f6";
const CONTROL_POINT_HOVER_COLOR = "#60a5fa";
const CONTROL_POINT_DRAG_COLOR = "#1d4ed8";
const BORDER_COLOR = "#374151";

export class TractEditor {
  private canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private areas: number[];
  private targetAreas: number[];
  private animating = false;
  private animStartTime = 0;
  private animDuration = 300; // ms
  private animFromAreas: number[] = [];

  private draggingIndex = -1;
  private hoverIndex = -1;
  private onAreasChange: AreasChangeCallback;

  constructor(canvas: HTMLCanvasElement, initialAreas: number[], onChange: AreasChangeCallback) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d")!;
    this.areas = [...initialAreas];
    this.targetAreas = [...initialAreas];
    this.onAreasChange = onChange;

    this.setupEvents();
    this.draw();
  }

  // 制御点の X 座標（インデックス → Canvas X）
  private cpX(index: number): number {
    const padding = 30;
    const w = this.canvas.width - padding * 2;
    return padding + (index / (NUM_SECTIONS - 1)) * w;
  }

  // 断面積 → Canvas Y（中心からのオフセット）
  private areaToHalfHeight(area: number): number {
    const maxHalf = (this.canvas.height / 2) * 0.85;
    return (area / MAX_AREA) * maxHalf;
  }

  private draw(): void {
    const { canvas, ctx } = this;
    const W = canvas.width;
    const H = canvas.height;
    const centerY = H / 2;

    ctx.clearRect(0, 0, W, H);

    // 壁と管腔の形状をパスで描画
    const padding = 30;
    const xs: number[] = [];
    const halfHeights: number[] = [];

    for (let i = 0; i < NUM_SECTIONS; i++) {
      xs.push(this.cpX(i));
      halfHeights.push(this.areaToHalfHeight(this.areas[i]));
    }

    // 上壁（外側）
    const wallThickness = 18;

    // 管腔（白い空洞）
    ctx.beginPath();
    ctx.moveTo(xs[0], centerY - halfHeights[0]);
    for (let i = 1; i < NUM_SECTIONS; i++) {
      const mx = (xs[i - 1] + xs[i]) / 2;
      ctx.quadraticCurveTo(xs[i - 1], centerY - halfHeights[i - 1], mx, centerY - (halfHeights[i - 1] + halfHeights[i]) / 2);
    }
    ctx.lineTo(xs[NUM_SECTIONS - 1], centerY - halfHeights[NUM_SECTIONS - 1]);
    ctx.lineTo(xs[NUM_SECTIONS - 1], centerY + halfHeights[NUM_SECTIONS - 1]);
    for (let i = NUM_SECTIONS - 2; i >= 0; i--) {
      const mx = (xs[i] + xs[i + 1]) / 2;
      ctx.quadraticCurveTo(xs[i + 1], centerY + halfHeights[i + 1], mx, centerY + (halfHeights[i] + halfHeights[i + 1]) / 2);
    }
    ctx.lineTo(xs[0], centerY + halfHeights[0]);
    ctx.closePath();
    ctx.fillStyle = LUMEN_COLOR;
    ctx.fill();
    ctx.strokeStyle = BORDER_COLOR;
    ctx.lineWidth = 1.5;
    ctx.stroke();

    // 上壁（肉）
    ctx.beginPath();
    ctx.moveTo(xs[0], centerY - halfHeights[0]);
    for (let i = 1; i < NUM_SECTIONS; i++) {
      const mx = (xs[i - 1] + xs[i]) / 2;
      ctx.quadraticCurveTo(xs[i - 1], centerY - halfHeights[i - 1], mx, centerY - (halfHeights[i - 1] + halfHeights[i]) / 2);
    }
    ctx.lineTo(xs[NUM_SECTIONS - 1], centerY - halfHeights[NUM_SECTIONS - 1]);
    ctx.lineTo(xs[NUM_SECTIONS - 1], centerY - halfHeights[NUM_SECTIONS - 1] - wallThickness);
    for (let i = NUM_SECTIONS - 2; i >= 0; i--) {
      const mx = (xs[i] + xs[i + 1]) / 2;
      ctx.quadraticCurveTo(xs[i + 1], centerY - halfHeights[i + 1] - wallThickness, mx, centerY - (halfHeights[i] + halfHeights[i + 1]) / 2 - wallThickness);
    }
    ctx.lineTo(xs[0], centerY - halfHeights[0] - wallThickness);
    ctx.closePath();
    ctx.fillStyle = WALL_COLOR;
    ctx.fill();

    // 下壁（肉）
    ctx.beginPath();
    ctx.moveTo(xs[0], centerY + halfHeights[0]);
    for (let i = 1; i < NUM_SECTIONS; i++) {
      const mx = (xs[i - 1] + xs[i]) / 2;
      ctx.quadraticCurveTo(xs[i - 1], centerY + halfHeights[i - 1], mx, centerY + (halfHeights[i - 1] + halfHeights[i]) / 2);
    }
    ctx.lineTo(xs[NUM_SECTIONS - 1], centerY + halfHeights[NUM_SECTIONS - 1]);
    ctx.lineTo(xs[NUM_SECTIONS - 1], centerY + halfHeights[NUM_SECTIONS - 1] + wallThickness);
    for (let i = NUM_SECTIONS - 2; i >= 0; i--) {
      const mx = (xs[i] + xs[i + 1]) / 2;
      ctx.quadraticCurveTo(xs[i + 1], centerY + halfHeights[i + 1] + wallThickness, mx, centerY + (halfHeights[i] + halfHeights[i + 1]) / 2 + wallThickness);
    }
    ctx.lineTo(xs[0], centerY + halfHeights[0] + wallThickness);
    ctx.closePath();
    ctx.fillStyle = WALL_COLOR;
    ctx.fill();

    // グロッタル端・口端のラベル
    ctx.fillStyle = "#9ca3af";
    ctx.font = "11px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("声帯", xs[0], H - 6);
    ctx.fillText("口", xs[NUM_SECTIONS - 1], H - 6);

    // 制御点の描画
    for (let i = 0; i < NUM_SECTIONS; i++) {
      const x = xs[i];
      const y = centerY - halfHeights[i];

      let color = CONTROL_POINT_COLOR;
      if (i === this.draggingIndex) color = CONTROL_POINT_DRAG_COLOR;
      else if (i === this.hoverIndex) color = CONTROL_POINT_HOVER_COLOR;

      ctx.beginPath();
      ctx.arc(x, y, CONTROL_POINT_RADIUS, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }
  }

  // ヒットテスト：制御点のインデックスを返す
  private hitTest(cx: number, cy: number): number {
    const centerY = this.canvas.height / 2;
    for (let i = 0; i < NUM_SECTIONS; i++) {
      const x = this.cpX(i);
      const y = centerY - this.areaToHalfHeight(this.areas[i]);
      const dx = cx - x;
      const dy = cy - y;
      if (Math.sqrt(dx * dx + dy * dy) <= CONTROL_POINT_RADIUS + 4) {
        return i;
      }
    }
    return -1;
  }

  // Canvas 座標 Y → 断面積
  private yToArea(cy: number): number {
    const centerY = this.canvas.height / 2;
    const maxHalf = (this.canvas.height / 2) * 0.85;
    const half = centerY - cy;
    const area = (half / maxHalf) * MAX_AREA;
    return Math.max(MIN_AREA, Math.min(MAX_AREA, area));
  }

  private getCanvasPos(e: MouseEvent | TouchEvent): { x: number; y: number } {
    const rect = this.canvas.getBoundingClientRect();
    const scaleX = this.canvas.width / rect.width;
    const scaleY = this.canvas.height / rect.height;
    if (e instanceof MouseEvent) {
      return {
        x: (e.clientX - rect.left) * scaleX,
        y: (e.clientY - rect.top) * scaleY,
      };
    } else {
      const t = e.touches[0];
      return {
        x: (t.clientX - rect.left) * scaleX,
        y: (t.clientY - rect.top) * scaleY,
      };
    }
  }

  private setupEvents(): void {
    const c = this.canvas;

    const onDown = (e: MouseEvent | TouchEvent) => {
      e.preventDefault();
      const { x, y } = this.getCanvasPos(e);
      this.draggingIndex = this.hitTest(x, y);
    };

    const onMove = (e: MouseEvent | TouchEvent) => {
      e.preventDefault();
      const { x, y } = this.getCanvasPos(e);
      if (this.draggingIndex >= 0) {
        this.areas[this.draggingIndex] = this.yToArea(y);
        this.onAreasChange([...this.areas]);
        this.draw();
      } else {
        const prev = this.hoverIndex;
        this.hoverIndex = this.hitTest(x, y);
        if (prev !== this.hoverIndex) this.draw();
      }
    };

    const onUp = () => {
      this.draggingIndex = -1;
    };

    c.addEventListener("mousedown", onDown);
    c.addEventListener("mousemove", onMove);
    c.addEventListener("mouseup", onUp);
    c.addEventListener("mouseleave", onUp);
    c.addEventListener("touchstart", onDown, { passive: false });
    c.addEventListener("touchmove", onMove, { passive: false });
    c.addEventListener("touchend", onUp);
  }

  // 外部からエリアをセット（アニメーション付き）
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
    this.animateStep();
  }

  private animateStep(): void {
    if (!this.animating) return;
    const elapsed = performance.now() - this.animStartTime;
    const t = Math.min(1, elapsed / this.animDuration);
    // ease-out cubic
    const ease = 1 - Math.pow(1 - t, 3);

    for (let i = 0; i < NUM_SECTIONS; i++) {
      this.areas[i] =
        this.animFromAreas[i] +
        (this.targetAreas[i] - this.animFromAreas[i]) * ease;
    }
    this.onAreasChange([...this.areas]);
    this.draw();

    if (t < 1) {
      requestAnimationFrame(() => this.animateStep());
    } else {
      this.animating = false;
      this.areas = [...this.targetAreas];
      this.onAreasChange([...this.areas]);
      this.draw();
    }
  }

  getAreas(): number[] {
    return [...this.areas];
  }
}
