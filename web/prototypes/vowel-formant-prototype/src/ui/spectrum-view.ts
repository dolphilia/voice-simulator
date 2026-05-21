import { VOWEL_PROFILE_SETS, type VowelId, type VowelSetId } from "../audio/vowels";

const BG_COLOR = "#102323";
const SPECTRUM_COLOR = "#2f9e8f";
const ACTIVE_FORMANT_COLOR = "#c87a2a";
const REFERENCE_FORMANT_COLOR = "rgba(52, 83, 83, 0.45)";
const GRID_COLOR = "rgba(19, 32, 32, 0.18)";
const TEXT_COLOR = "#345353";
const MAX_FREQ = 4000;

export type SpectrumTarget = {
  vowel: VowelId;
  vowelSet: VowelSetId;
  tractScale: number;
};

export class SpectrumView {
  private canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private analyser: AnalyserNode | null = null;
  private dataBuffer: Uint8Array<ArrayBuffer> = new Uint8Array(0);
  private rafId = 0;
  private target: SpectrumTarget = {
    vowel: "a",
    vowelSet: "reference",
    tractScale: 1,
  };

  constructor(canvas: HTMLCanvasElement) {
    this.canvas = canvas;
    const context = canvas.getContext("2d");
    if (!context) {
      throw new Error("Canvas 2D context is not available");
    }
    this.ctx = context;
    this.drawIdle();
  }

  setAnalyser(analyser: AnalyserNode): void {
    this.analyser = analyser;
    this.dataBuffer = new Uint8Array(analyser.frequencyBinCount) as Uint8Array<ArrayBuffer>;
  }

  setTarget(target: SpectrumTarget): void {
    this.target = { ...target };
    if (!this.analyser) {
      this.drawIdle();
    }
  }

  start(): void {
    cancelAnimationFrame(this.rafId);
    this.rafId = requestAnimationFrame(() => this.loop());
  }

  stop(): void {
    cancelAnimationFrame(this.rafId);
    this.rafId = 0;
    this.analyser = null;
    this.dataBuffer = new Uint8Array(0);
    this.drawIdle();
  }

  private loop(): void {
    this.drawSpectrum();
    this.rafId = requestAnimationFrame(() => this.loop());
  }

  private freqToX(freq: number): number {
    return (freq / MAX_FREQ) * this.canvas.width;
  }

  private drawGrid(): void {
    const { ctx, canvas } = this;
    ctx.strokeStyle = GRID_COLOR;
    ctx.lineWidth = 1;
    ctx.fillStyle = TEXT_COLOR;
    ctx.font = "10px monospace";
    ctx.textAlign = "center";

    for (const freq of [500, 1000, 1500, 2000, 2500, 3000, 3500, 4000]) {
      const x = this.freqToX(freq);
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, canvas.height);
      ctx.stroke();
      ctx.fillText(String(freq), x, canvas.height - 4);
    }
  }

  private drawIdle(): void {
    const { ctx, canvas } = this;
    ctx.fillStyle = "#f6f1e8";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    this.drawGrid();
    this.drawFormantMarkers();
    ctx.fillStyle = TEXT_COLOR;
    ctx.font = "13px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("Start 後に 0-4 kHz のスペクトルを表示", canvas.width / 2, canvas.height / 2);
  }

  private drawSpectrum(): void {
    if (!this.analyser) {
      return;
    }

    this.analyser.getByteFrequencyData(this.dataBuffer);

    const { ctx, canvas } = this;
    const width = canvas.width;
    const height = canvas.height;
    const nyquist = this.analyser.context.sampleRate / 2;
    const binCount = this.dataBuffer.length;

    ctx.fillStyle = BG_COLOR;
    ctx.fillRect(0, 0, width, height);
    this.drawGrid();

    ctx.beginPath();
    for (let index = 0; index < binCount; index += 1) {
      const freq = (index / binCount) * nyquist;
      if (freq > MAX_FREQ) {
        break;
      }
      const x = this.freqToX(freq);
      const amplitude = this.dataBuffer[index] / 255;
      const y = height - amplitude * height * 0.9;
      if (index === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    }
    ctx.strokeStyle = SPECTRUM_COLOR;
    ctx.lineWidth = 1.8;
    ctx.stroke();

    this.drawFormantMarkers();
  }

  private drawFormantMarkers(): void {
    const { ctx, canvas } = this;
    const inactiveSets = (Object.keys(VOWEL_PROFILE_SETS) as VowelSetId[]).filter(
      (setId) => setId !== this.target.vowelSet,
    );

    ctx.font = "10px monospace";
    ctx.textAlign = "center";

    for (const setId of inactiveSets) {
      const profile = VOWEL_PROFILE_SETS[setId][this.target.vowel];
      for (const formant of profile.formants) {
        this.drawMarker(formant.frequency / this.target.tractScale, REFERENCE_FORMANT_COLOR, "", 0.5);
      }
    }

    const activeProfile = VOWEL_PROFILE_SETS[this.target.vowelSet][this.target.vowel];
    activeProfile.formants.forEach((formant, index) => {
      this.drawMarker(
        formant.frequency / this.target.tractScale,
        ACTIVE_FORMANT_COLOR,
        `F${index + 1}`,
        1.3,
      );
    });
    ctx.setLineDash([]);
  }

  private drawMarker(freq: number, color: string, label: string, lineWidth: number): void {
    if (freq <= 0 || freq > MAX_FREQ) {
      return;
    }

    const { ctx, canvas } = this;
    const x = this.freqToX(freq);
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, canvas.height - 16);
    ctx.strokeStyle = color;
    ctx.lineWidth = lineWidth;
    ctx.setLineDash(label ? [4, 3] : [2, 6]);
    ctx.stroke();
    ctx.setLineDash([]);

    if (label) {
      ctx.fillStyle = color;
      ctx.fillText(label, x, canvas.height - 18);
    }
  }
}
