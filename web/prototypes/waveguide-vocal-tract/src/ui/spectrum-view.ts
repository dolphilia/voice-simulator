const BG      = "#111827";
const LINE    = "#34d399";
const FORMANT = "#f59e0b";
const GRID    = "#1f2937";
const TEXT    = "#6b7280";
const MAX_FREQ = 4000;

export class SpectrumView {
  private canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private analyser: AnalyserNode | null = null;
  private buf: Uint8Array<ArrayBuffer> = new Uint8Array(0);
  private formants: number[] = [];
  private rafId = 0;

  constructor(canvas: HTMLCanvasElement) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d")!;
    this.drawIdle();
  }

  setAnalyser(a: AnalyserNode): void {
    this.analyser = a;
    this.buf = new Uint8Array(a.frequencyBinCount) as Uint8Array<ArrayBuffer>;
  }

  setFormants(f: number[]): void { this.formants = f; }

  start(): void { this.rafId = requestAnimationFrame(() => this.loop()); }

  stop(): void {
    cancelAnimationFrame(this.rafId);
    this.analyser = null;
    this.buf = new Uint8Array(0);
    this.drawIdle();
  }

  private loop(): void {
    this.render();
    this.rafId = requestAnimationFrame(() => this.loop());
  }

  private fx(hz: number): number {
    return (hz / MAX_FREQ) * this.canvas.width;
  }

  private drawGrid(): void {
    const { ctx, canvas } = this;
    ctx.strokeStyle = GRID;
    ctx.lineWidth = 1;
    ctx.fillStyle = TEXT;
    ctx.font = "10px monospace";
    ctx.textAlign = "center";
    for (const f of [500, 1000, 1500, 2000, 2500, 3000, 3500, 4000]) {
      const x = this.fx(f);
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, canvas.height); ctx.stroke();
      ctx.fillText(`${f}`, x, canvas.height - 2);
    }
  }

  private drawIdle(): void {
    const { ctx, canvas } = this;
    ctx.fillStyle = BG;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    this.drawGrid();
    ctx.fillStyle = TEXT;
    ctx.font = "13px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("スタートするとスペクトラムが表示されます", canvas.width / 2, canvas.height / 2);
  }

  private render(): void {
    if (!this.analyser) return;
    this.analyser.getByteFrequencyData(this.buf);

    const { ctx, canvas } = this;
    const W = canvas.width, H = canvas.height;
    const nyquist = this.analyser.context.sampleRate / 2;
    const bins = this.buf.length;

    ctx.fillStyle = BG;
    ctx.fillRect(0, 0, W, H);
    this.drawGrid();

    // スペクトラム
    ctx.beginPath();
    for (let i = 0; i < bins; i++) {
      const freq = (i / bins) * nyquist;
      if (freq > MAX_FREQ) break;
      const x = this.fx(freq);
      const y = H - (this.buf[i] / 255) * H * 0.92;
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    }
    ctx.strokeStyle = LINE;
    ctx.lineWidth = 1.5;
    ctx.stroke();

    // フォルマントマーカー
    ctx.textAlign = "center";
    ctx.font = "10px monospace";
    for (let fi = 0; fi < this.formants.length; fi++) {
      const freq = this.formants[fi];
      if (freq <= 0 || freq > MAX_FREQ) continue;
      const x = this.fx(freq);
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H - 14);
      ctx.strokeStyle = FORMANT;
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 3]);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = FORMANT;
      ctx.fillText(`F${fi + 1}`, x, H - 16);
    }
  }
}
