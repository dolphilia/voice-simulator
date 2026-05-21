import { SIBILANT_PROFILES, type SibilantId } from "./phonemes";
import { VOWEL_PROFILE_SETS, type Formant, type VowelId, type VowelSetId } from "./vowels";

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
const SOURCE_GAIN = 0.3;
const MUTED_SOURCE_GAIN = 0.018;

export class VoiceEngine {
  private context: AudioContext | null = null;
  private oscillator: OscillatorNode | null = null;
  private sourceGainNode: GainNode | null = null;
  private masterGainNode: GainNode | null = null;
  private breathNoiseSource: AudioBufferSourceNode | null = null;
  private breathFilterNode: BiquadFilterNode | null = null;
  private breathGainNode: GainNode | null = null;
  private analyserNode: AnalyserNode | null = null;
  private filterNodes: BiquadFilterNode[] = [];
  private filterGainNodes: GainNode[] = [];
  private params: VoiceParams = { ...DEFAULT_PARAMS };

  get analyser(): AnalyserNode | null {
    return this.analyserNode;
  }

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
    this.analyserNode = this.context.createAnalyser();

    this.oscillator.type = "sawtooth";
    this.sourceGainNode.gain.value = SOURCE_GAIN;
    this.masterGainNode.gain.value = this.params.gain;
    this.analyserNode.fftSize = 4096;
    this.analyserNode.smoothingTimeConstant = 0.82;

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
    this.analyserNode?.disconnect();
    this.breathNoiseSource?.stop();
    this.breathNoiseSource?.disconnect();
    this.breathFilterNode?.disconnect();
    this.breathGainNode?.disconnect();
    this.filterNodes.forEach((node) => node.disconnect());
    this.filterGainNodes.forEach((node) => node.disconnect());
    this.oscillator = null;
    this.sourceGainNode = null;
    this.masterGainNode = null;
    this.analyserNode = null;
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

  triggerConsonant(kind: SibilantId): void {
    if (!this.context || !this.analyserNode) {
      return;
    }

    const profile = SIBILANT_PROFILES[kind];
    this.triggerNoise(profile, this.context.currentTime);
  }

  triggerSyllable(consonant: SibilantId, vowel: VowelId): VoiceParams {
    this.params = { ...this.params, vowel };

    if (!this.context || !this.sourceGainNode || !this.analyserNode) {
      return this.params;
    }

    const profile = SIBILANT_PROFILES[consonant];
    const now = this.context.currentTime;
    const vowelStart = now + Math.max(0, profile.durationSeconds - profile.overlapSeconds);
    const releaseEnd = now + profile.durationSeconds + 0.08;

    this.sourceGainNode.gain.cancelScheduledValues(now);
    this.sourceGainNode.gain.setValueAtTime(this.sourceGainNode.gain.value, now);
    this.sourceGainNode.gain.linearRampToValueAtTime(MUTED_SOURCE_GAIN, now + 0.012);
    this.sourceGainNode.gain.setValueAtTime(MUTED_SOURCE_GAIN, vowelStart);
    this.sourceGainNode.gain.linearRampToValueAtTime(SOURCE_GAIN, releaseEnd);

    this.triggerNoise(profile, now);
    this.scheduleVowelProfile(vowelStart, VOWEL_TRANSITION_SECONDS);

    return this.params;
  }

  private triggerNoise(profile: (typeof SIBILANT_PROFILES)[SibilantId], startTime: number): void {
    if (!this.context || !this.analyserNode) {
      return;
    }

    const source = this.context.createBufferSource();
    const filter = this.context.createBiquadFilter();
    const gain = this.context.createGain();

    source.buffer = this.createNoiseBuffer(0.25);
    filter.type = "bandpass";
    filter.frequency.value = profile.centerFrequency;
    filter.Q.value = profile.q;

    gain.gain.setValueAtTime(0.0001, startTime);
    gain.gain.exponentialRampToValueAtTime(profile.peakGain, startTime + profile.attackSeconds);
    gain.gain.exponentialRampToValueAtTime(0.0001, startTime + profile.durationSeconds);

    source.connect(filter);
    filter.connect(gain);
    gain.connect(this.analyserNode);
    source.start(startTime);
    source.stop(startTime + profile.durationSeconds + 0.02);
  }

  private configureFilters(): void {
    if (!this.context || !this.sourceGainNode || !this.masterGainNode || !this.analyserNode) {
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
      gain.connect(this.analyserNode);

      this.filterNodes.push(filter);
      this.filterGainNodes.push(gain);
    }

    this.analyserNode.connect(this.masterGainNode);
    this.masterGainNode.connect(this.context.destination);
  }

  private configureBreathNoise(): void {
    if (!this.context || !this.analyserNode) {
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
    this.breathGainNode.connect(this.analyserNode);
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

    this.scheduleFormants(profile.formants, now, VOWEL_TRANSITION_SECONDS);
  }

  private scheduleVowelProfile(startTime: number, rampSeconds: number): void {
    const profile = VOWEL_PROFILE_SETS[this.params.vowelSet][this.params.vowel];
    this.scheduleFormants(profile.formants, startTime, rampSeconds);
  }

  private scheduleFormants(
    formants: readonly [Formant, Formant, Formant],
    startTime: number,
    rampSeconds: number,
  ): void {
    this.filterNodes.forEach((filter, index) => {
      const formant = formants[index];
      const scaledFrequency = formant.frequency / this.params.tractScale;
      const q = Math.max(0.1, scaledFrequency / Math.max(1, formant.bandwidth));

      this.setAudioParam(filter.frequency, scaledFrequency, startTime, rampSeconds);
      this.setAudioParam(filter.Q, q, startTime, rampSeconds);
    });

    this.filterGainNodes.forEach((gainNode, index) => {
      const formant = formants[index];
      const brightnessGain = 1 + this.params.brightness * index * 0.45;
      const breathCompensation = Math.max(0.55, 1 - this.params.breathiness * 0.2);
      this.setAudioParam(
        gainNode.gain,
        formant.gain * brightnessGain * breathCompensation,
        startTime,
        rampSeconds,
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
