const BG_COLOR = "#111827";
const SPECTRUM_COLOR = "#34d399";
const FORMANT_COLOR = "#f59e0b";
const GRID_COLOR = "#1f2937";
const TEXT_COLOR = "#6b7280";

export class SpectrumView {
  private canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private analyser: AnalyserNode | null = null;
  private dataBuffer: Uint8Array<ArrayBuffer> = new Uint8Array(0);
  private rafId = 0;
  private formants: number[] = [];
  private maxFreq = 4000;

  constructor(canvas: HTMLCanvasElement) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d")!;
    this.drawIdle();
  }

  setAnalyser(analyser: AnalyserNode): void {
    this.analyser = analyser;
    this.dataBuffer = new Uint8Array(analyser.frequencyBinCount) as Uint8Array<ArrayBuffer>;
  }

  setFormants(formants: number[]): void {
    this.formants = formants;
  }

  start(): void {
    this.rafId = requestAnimationFrame(() => this.loop());
  }

  stop(): void {
    cancelAnimationFrame(this.rafId);
    this.analyser = null;
    this.dataBuffer = new Uint8Array(0);
    this.drawIdle();
  }

  private loop(): void {
    this.drawSpectrum();
    this.rafId = requestAnimationFrame(() => this.loop());
  }

  private freqToX(freq: number): number {
    return (freq / this.maxFreq) * this.canvas.width;
  }

  private drawGrid(): void {
    const { ctx, canvas } = this;
    ctx.strokeStyle = GRID_COLOR;
    ctx.lineWidth = 1;
    ctx.fillStyle = TEXT_COLOR;
    ctx.font = "10px monospace";
    ctx.textAlign = "center";

    const freqMarks = [500, 1000, 1500, 2000, 2500, 3000, 3500, 4000];
    for (const f of freqMarks) {
      const x = this.freqToX(f);
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, canvas.height);
      ctx.stroke();
      ctx.fillText(`${f}`, x, canvas.height - 2);
    }
  }

  private drawIdle(): void {
    const { ctx, canvas } = this;
    ctx.fillStyle = BG_COLOR;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    this.drawGrid();
    ctx.fillStyle = TEXT_COLOR;
    ctx.font = "13px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("スタートするとスペクトラムが表示されます", canvas.width / 2, canvas.height / 2);
  }

  private drawSpectrum(): void {
    if (!this.analyser) return;
    this.analyser.getByteFrequencyData(this.dataBuffer);

    const { ctx, canvas } = this;
    const W = canvas.width;
    const H = canvas.height;
    const sampleRate = this.analyser.context.sampleRate;
    const nyquist = sampleRate / 2;
    const binCount = this.dataBuffer.length;

    ctx.fillStyle = BG_COLOR;
    ctx.fillRect(0, 0, W, H);
    this.drawGrid();

    // スペクトラム描画
    ctx.beginPath();
    ctx.moveTo(0, H);
    for (let i = 0; i < binCount; i++) {
      const freq = (i / binCount) * nyquist;
      if (freq > this.maxFreq) break;
      const x = this.freqToX(freq);
      const amplitude = this.dataBuffer[i] / 255;
      const y = H - amplitude * H * 0.9;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.strokeStyle = SPECTRUM_COLOR;
    ctx.lineWidth = 1.5;
    ctx.stroke();

    // フォルマントマーカー
    ctx.textAlign = "center";
    for (let fi = 0; fi < this.formants.length; fi++) {
      const freq = this.formants[fi];
      if (freq <= 0 || freq > this.maxFreq) continue;
      const x = this.freqToX(freq);
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, H - 14);
      ctx.strokeStyle = FORMANT_COLOR;
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 3]);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = FORMANT_COLOR;
      ctx.font = "10px monospace";
      ctx.fillText(`F${fi + 1}`, x, H - 16);
    }
  }
}
