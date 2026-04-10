import { TubeModel, computeReflectionCoefficients } from "./tube-model";
import { VOWEL_PRESETS, type VowelId } from "./vowel-presets";

export type EngineParams = {
  frequency: number;
  gain: number;
};

const DEFAULT_PARAMS: EngineParams = {
  frequency: 220,
  gain: 0.12,
};

export class TubeVoiceEngine {
  private context: AudioContext | null = null;
  private workletNode: AudioWorkletNode | null = null;
  private analyserNode: AnalyserNode | null = null;
  private masterGain: GainNode | null = null;
  private model: TubeModel;
  private params: EngineParams = { ...DEFAULT_PARAMS };
  private running = false;

  constructor(initialVowel: VowelId = "a") {
    this.model = new TubeModel(VOWEL_PRESETS[initialVowel]);
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

    // AudioWorklet モジュールを登録（public/ に配置した JS を参照）
    await this.context.audioWorklet.addModule("/worklet/tube-processor.js");

    this.workletNode = new AudioWorkletNode(this.context, "tube-processor");
    this.analyserNode = this.context.createAnalyser();
    this.masterGain = this.context.createGain();

    this.analyserNode.fftSize = 2048;
    this.masterGain.gain.value = 1.0;

    this.workletNode.connect(this.analyserNode);
    this.analyserNode.connect(this.masterGain);
    this.masterGain.connect(this.context.destination);

    // 初期パラメータを送信
    this.sendToWorklet("setFrequency", this.params.frequency);
    this.sendToWorklet("setGain", this.params.gain);
    this.pushCoeffsToWorklet();

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
    this.params = { ...this.params, ...next };
    if (next.frequency !== undefined) {
      this.sendToWorklet("setFrequency", next.frequency);
    }
    if (next.gain !== undefined) {
      this.sendToWorklet("setGain", next.gain);
    }
  }

  getParams(): EngineParams {
    return { ...this.params };
  }

  setAreas(areas: number[]): void {
    this.model.setAreas(areas);
    this.pushCoeffsToWorklet();
  }

  getAreas(): number[] {
    return this.model.getAreas();
  }

  getFormants(): number[] {
    return this.model.getFormants(this.context?.sampleRate ?? 44100);
  }

  applyVowelPreset(vowel: VowelId): number[] {
    const areas = [...VOWEL_PRESETS[vowel]];
    this.setAreas(areas);
    return areas;
  }

  private sendToWorklet(type: string, data: unknown): void {
    this.workletNode?.port.postMessage({ type, data });
  }

  private pushCoeffsToWorklet(): void {
    const areas = this.model.getAreas();
    const k = computeReflectionCoefficients(areas);
    this.sendToWorklet("setReflectionCoeffs", k);
  }
}
