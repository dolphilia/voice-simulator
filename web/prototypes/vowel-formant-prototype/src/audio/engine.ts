import { VOWEL_PROFILE_SETS, type VowelId, type VowelSetId } from "./vowels";

export type VoiceParams = {
  frequency: number;
  gain: number;
  vowel: VowelId;
  tractScale: number;
  vowelSet: VowelSetId;
  brightness: number;
  breathiness: number;
};

const DEFAULT_PARAMS: VoiceParams = {
  frequency: 220,
  gain: 0.12,
  vowel: "a",
  tractScale: 1,
  vowelSet: "reference",
  brightness: 0,
  breathiness: 0,
};

const VOWEL_TRANSITION_SECONDS = 0.167;
const DEFAULT_NOISE_BUFFER_SECONDS = 2;

export class VoiceEngine {
  private context: AudioContext | null = null;
  private oscillator: OscillatorNode | null = null;
  private sourceGainNode: GainNode | null = null;
  private masterGainNode: GainNode | null = null;
  private breathNoiseSource: AudioBufferSourceNode | null = null;
  private breathFilterNode: BiquadFilterNode | null = null;
  private breathGainNode: GainNode | null = null;
  private filterNodes: BiquadFilterNode[] = [];
  private filterGainNodes: GainNode[] = [];
  private params: VoiceParams = { ...DEFAULT_PARAMS };

  async start(): Promise<void> {
    if (!this.context) {
      this.context = new AudioContext();
    }

    if (this.context.state === "suspended") {
      await this.context.resume();
    }

    if (this.oscillator || !this.context) {
      return;
    }

    this.oscillator = this.context.createOscillator();
    this.sourceGainNode = this.context.createGain();
    this.masterGainNode = this.context.createGain();

    this.oscillator.type = "sawtooth";
    this.sourceGainNode.gain.value = 0.3;
    this.masterGainNode.gain.value = this.params.gain;

    this.oscillator.connect(this.sourceGainNode);
    this.configureFilters();
    this.configureBreathNoise();
    this.updateNodes();

    this.oscillator.start();
    this.breathNoiseSource?.start();
  }

  stop(): void {
    this.oscillator?.stop();
    this.oscillator?.disconnect();
    this.sourceGainNode?.disconnect();
    this.masterGainNode?.disconnect();
    this.breathNoiseSource?.stop();
    this.breathNoiseSource?.disconnect();
    this.breathFilterNode?.disconnect();
    this.breathGainNode?.disconnect();
    this.filterNodes.forEach((node) => node.disconnect());
    this.filterGainNodes.forEach((node) => node.disconnect());
    this.oscillator = null;
    this.sourceGainNode = null;
    this.masterGainNode = null;
    this.breathNoiseSource = null;
    this.breathFilterNode = null;
    this.breathGainNode = null;
    this.filterNodes = [];
    this.filterGainNodes = [];
  }

  setParams(nextParams: Partial<VoiceParams>): VoiceParams {
    this.params = { ...this.params, ...nextParams };

    this.updateNodes();

    return this.params;
  }

  getParams(): VoiceParams {
    return { ...this.params };
  }

  triggerConsonant(kind: "shi" | "su"): void {
    if (!this.context || !this.masterGainNode) {
      return;
    }

    const source = this.context.createBufferSource();
    const filter = this.context.createBiquadFilter();
    const gain = this.context.createGain();
    const now = this.context.currentTime;
    const duration = kind === "shi" ? 0.13 : 0.15;

    source.buffer = this.createNoiseBuffer(0.25);
    filter.type = "bandpass";
    filter.frequency.value = kind === "shi" ? 6100 : 6000;
    filter.Q.value = kind === "shi" ? 1.4 : 1.0;

    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(kind === "shi" ? 0.08 : 0.07, now + 0.015);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + duration);

    source.connect(filter);
    filter.connect(gain);
    gain.connect(this.masterGainNode);
    source.start(now);
    source.stop(now + duration + 0.02);
  }

  private configureFilters(): void {
    if (!this.context || !this.sourceGainNode || !this.masterGainNode) {
      return;
    }

    this.filterNodes = [];
    this.filterGainNodes = [];

    for (let index = 0; index < 3; index += 1) {
      const filter = this.context.createBiquadFilter();
      const gain = this.context.createGain();

      filter.type = "bandpass";

      this.sourceGainNode.connect(filter);
      filter.connect(gain);
      gain.connect(this.masterGainNode);

      this.filterNodes.push(filter);
      this.filterGainNodes.push(gain);
    }

    this.masterGainNode.connect(this.context.destination);
  }

  private configureBreathNoise(): void {
    if (!this.context || !this.masterGainNode) {
      return;
    }

    this.breathNoiseSource = this.context.createBufferSource();
    this.breathFilterNode = this.context.createBiquadFilter();
    this.breathGainNode = this.context.createGain();

    this.breathNoiseSource.buffer = this.createNoiseBuffer(DEFAULT_NOISE_BUFFER_SECONDS);
    this.breathNoiseSource.loop = true;
    this.breathFilterNode.type = "highpass";
    this.breathFilterNode.frequency.value = 3400;
    this.breathFilterNode.Q.value = 0.5;
    this.breathGainNode.gain.value = 0;

    this.breathNoiseSource.connect(this.breathFilterNode);
    this.breathFilterNode.connect(this.breathGainNode);
    this.breathGainNode.connect(this.masterGainNode);
  }

  private updateNodes(): void {
    const now = this.context?.currentTime ?? 0;

    if (this.oscillator) {
      this.setAudioParam(this.oscillator.frequency, this.params.frequency, now, 0.03);
    }

    if (this.masterGainNode) {
      this.setAudioParam(this.masterGainNode.gain, this.params.gain, now, 0.03);
    }

    if (this.breathGainNode) {
      this.setAudioParam(this.breathGainNode.gain, this.params.breathiness * 0.045, now, 0.05);
    }

    const profile = VOWEL_PROFILE_SETS[this.params.vowelSet][this.params.vowel];

    this.filterNodes.forEach((filter, index) => {
      const formant = profile.formants[index];
      const scaledFrequency = formant.frequency / this.params.tractScale;
      const q = Math.max(0.1, scaledFrequency / Math.max(1, formant.bandwidth));

      this.setAudioParam(filter.frequency, scaledFrequency, now, VOWEL_TRANSITION_SECONDS);
      this.setAudioParam(filter.Q, q, now, VOWEL_TRANSITION_SECONDS);
    });

    this.filterGainNodes.forEach((gainNode, index) => {
      const formant = profile.formants[index];
      const brightnessGain = 1 + this.params.brightness * index * 0.45;
      const breathCompensation = Math.max(0.55, 1 - this.params.breathiness * 0.2);
      this.setAudioParam(
        gainNode.gain,
        formant.gain * brightnessGain * breathCompensation,
        now,
        VOWEL_TRANSITION_SECONDS,
      );
    });
  }

  private setAudioParam(param: AudioParam, value: number, startTime: number, rampSeconds: number): void {
    param.cancelScheduledValues(startTime);
    param.setValueAtTime(param.value, startTime);
    param.linearRampToValueAtTime(value, startTime + rampSeconds);
  }

  private createNoiseBuffer(seconds: number): AudioBuffer | null {
    if (!this.context) {
      return null;
    }

    const length = Math.max(1, Math.floor(this.context.sampleRate * seconds));
    const buffer = this.context.createBuffer(1, length, this.context.sampleRate);
    const data = buffer.getChannelData(0);

    for (let index = 0; index < length; index += 1) {
      data[index] = Math.random() * 2 - 1;
    }

    return buffer;
  }
}
