import { computeReflectionCoefficients, computeLossCoefficients } from "./tube-model";
import { estimateFormants } from "./formant-estimator";
import { VOWEL_PRESETS, type VowelId } from "./vowel-presets";
import type { LFParams } from "./lf-source";

export type EngineParams = {
  frequency: number;
  gain: number;
  lf: LFParams;
};

const DEFAULT_PARAMS: EngineParams = {
  frequency: 220,
  gain: 0.12,
  lf: { rg: 1.0, rk: 0.3 },
};

export class WaveguideEngine {
  private context: AudioContext | null = null;
  private workletNode: AudioWorkletNode | null = null;
  private analyserNode: AnalyserNode | null = null;
  private masterGain: GainNode | null = null;
  private areas: number[];
  private params: EngineParams = {
    frequency: DEFAULT_PARAMS.frequency,
    gain: DEFAULT_PARAMS.gain,
    lf: { ...DEFAULT_PARAMS.lf },
  };
  private running = false;

  constructor(initialVowel: VowelId = "a") {
    this.areas = [...VOWEL_PRESETS[initialVowel]];
  }

  get analyser(): AnalyserNode | null {
    return this.analyserNode;
  }

  get isRunning(): boolean {
    return this.running;
  }

  async start(): Promise<void> {
    if (this.running) return;

    if (!this.context) {
      this.context = new AudioContext();
    }
    if (this.context.state === "suspended") {
      await this.context.resume();
    }

    await this.context.audioWorklet.addModule("/worklet/waveguide-processor.js");

    this.workletNode = new AudioWorkletNode(this.context, "waveguide-processor");
    this.analyserNode = this.context.createAnalyser();
    this.masterGain = this.context.createGain();

    this.analyserNode.fftSize = 4096;
    this.masterGain.gain.value = 1.0;

    this.workletNode.connect(this.analyserNode);
    this.analyserNode.connect(this.masterGain);
    this.masterGain.connect(this.context.destination);

    // 初期パラメータを送信
    this.send("setFrequency", this.params.frequency);
    this.send("setGain", this.params.gain);
    this.send("setLFParams", this.params.lf);
    this.pushAreas();

    this.running = true;
  }

  stop(): void {
    this.workletNode?.disconnect();
    this.analyserNode?.disconnect();
    this.masterGain?.disconnect();
    this.workletNode = null;
    this.analyserNode = null;
    this.masterGain = null;
    this.running = false;
  }

  setParams(next: Partial<EngineParams>): void {
    if (next.frequency !== undefined) {
      this.params.frequency = next.frequency;
      this.send("setFrequency", next.frequency);
    }
    if (next.gain !== undefined) {
      this.params.gain = next.gain;
      this.send("setGain", next.gain);
    }
    if (next.lf !== undefined) {
      this.params.lf = { ...this.params.lf, ...next.lf };
      this.send("setLFParams", this.params.lf);
    }
  }

  getParams(): EngineParams {
    return { ...this.params, lf: { ...this.params.lf } };
  }

  setAreas(areas: number[]): void {
    this.areas = [...areas];
    this.pushAreas();
  }

  getAreas(): number[] {
    return [...this.areas];
  }

  getFormants(): number[] {
    return estimateFormants(this.areas);
  }

  applyVowelPreset(vowel: VowelId): number[] {
    const areas = [...VOWEL_PRESETS[vowel]];
    this.setAreas(areas);
    return areas;
  }

  private send(type: string, data: unknown): void {
    this.workletNode?.port.postMessage({ type, data });
  }

  private pushAreas(): void {
    const k = computeReflectionCoefficients(this.areas);
    const loss = computeLossCoefficients(this.areas);
    this.send("setReflectionCoeffs", k);
    this.send("setLossCoeffs", loss);
  }
}
