import { VOWEL_PROFILES, type VowelId } from "./vowels";

export type VoiceParams = {
  frequency: number;
  gain: number;
  vowel: VowelId;
  tractScale: number;
};

const DEFAULT_PARAMS: VoiceParams = {
  frequency: 220,
  gain: 0.12,
  vowel: "a",
  tractScale: 1,
};

export class VoiceEngine {
  private context: AudioContext | null = null;
  private oscillator: OscillatorNode | null = null;
  private sourceGainNode: GainNode | null = null;
  private masterGainNode: GainNode | null = null;
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
    this.updateNodes();

    this.oscillator.start();
  }

  stop(): void {
    this.oscillator?.stop();
    this.oscillator?.disconnect();
    this.sourceGainNode?.disconnect();
    this.masterGainNode?.disconnect();
    this.filterNodes.forEach((node) => node.disconnect());
    this.filterGainNodes.forEach((node) => node.disconnect());
    this.oscillator = null;
    this.sourceGainNode = null;
    this.masterGainNode = null;
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

  private updateNodes(): void {
    if (this.oscillator) {
      this.oscillator.frequency.value = this.params.frequency;
    }

    if (this.masterGainNode) {
      this.masterGainNode.gain.value = this.params.gain;
    }

    const profile = VOWEL_PROFILES[this.params.vowel];

    this.filterNodes.forEach((filter, index) => {
      const formant = profile.formants[index];
      const scaledFrequency = formant.frequency / this.params.tractScale;
      const q = Math.max(0.1, scaledFrequency / Math.max(1, formant.bandwidth));

      filter.frequency.value = scaledFrequency;
      filter.Q.value = q;
    });

    this.filterGainNodes.forEach((gainNode, index) => {
      const formant = profile.formants[index];
      gainNode.gain.value = formant.gain;
    });
  }
}
