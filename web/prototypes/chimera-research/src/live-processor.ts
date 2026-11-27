import {
  FixedVoiceEngine, observationFields, type LiveSongKey, type ManualTargets, type VoiceBody,
} from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/fixed-voice";
import { LIVE_PROCESSOR, MANUAL_EVENT_WORDS, MIDI_EVENT_WORDS, type AppliedSongKey, type FinalizationProbe, type LiveCommand, type LiveMessage, type LiveOptions, type LiveResult, type LiveSettings, type WrapperWarmup } from "./live-worklet-types";
import { midiFrequency } from "./midi-input";
import { WorkletStartup } from "./worklet-clock";
import type { AppliedBodyChange } from "./manual-replay";

declare const currentFrame: number;
declare const sampleRate: number;
declare class AudioWorkletProcessor {
  readonly port: MessagePort;
}
declare function registerProcessor(name: string, ctor: typeof LiveProcessor): void;

class LiveProcessor extends AudioWorkletProcessor {
  private engine: FixedVoiceEngine | undefined;
  private readonly settings: LiveSettings;
  private readonly internalSampleRate: number;
  private readonly pcm: Float32Array<ArrayBuffer>;
  private readonly observations: Float64Array<ArrayBuffer>;
  private readonly rowWords: number;
  private readonly appliedTargets?: Float64Array<ArrayBuffer>;
  private readonly appliedNotes?: Float64Array<ArrayBuffer>;
  private readonly songKeys?: AppliedSongKey[];
  private readonly pendingKeys: LiveSongKey[] = [];
  private nextTargets?: ManualTargets;
  private nextBody?: VoiceBody;
  private nextNote?: number | null;
  private currentNote: number | null = null;
  private noteOffset = 0;
  private readonly bodyChanges: AppliedBodyChange[] = [];
  private targetOffset = 0;
  private firstMemoryGrowthFrame: number | null = null;
  private readonly timingClock = typeof performance !== "undefined" ? "performance.now" : "Date.now";
  private readonly now = this.timingClock === "performance.now" ? performance.now.bind(performance) : Date.now;
  private readonly wrapperWarmup?: WrapperWarmup;
  private readonly finalizationProbe?: FinalizationProbe;
  private frames = 0;
  private row = 0;
  private firstCallbackMs = 0;
  private readonly startup = new WorkletStartup();
  private armed = false;
  private stopRequested = false;
  private stopFrame: number | undefined;
  private stopReason: "manual" | "limit" = "limit";

  constructor({ processorOptions: options }: { processorOptions: LiveOptions }) {
    super();
    this.settings = options.settings;
    this.finalizationProbe = options.finalizationProbe;
    this.internalSampleRate = options.voice.fixed_airway.sample_rate_hz;
    const capacity = this.settings.preRoll + this.settings.maximumVoiced + this.settings.release;
    const rows = Math.ceil(capacity / this.settings.quantum);
    const mode = options.song ?? (this.settings.manual || this.settings.midi ? "manual" : undefined);
    this.pcm = new Float32Array(capacity);
    this.rowWords = 4 + observationFields(mode).length;
    this.observations = new Float64Array(rows * this.rowWords);
    if (this.settings.manual) this.appliedTargets = new Float64Array(rows * MANUAL_EVENT_WORDS);
    if (this.settings.midi) this.appliedNotes = new Float64Array(rows * MIDI_EVENT_WORDS);
    if (options.song) this.songKeys = [];
    this.port.onmessage = ({ data }: MessageEvent<LiveCommand>) => {
      if (data === "stop") this.stopRequested = true;
      else if (this.appliedTargets && data.type === "articulation") this.nextTargets = data.targets;
      else if (this.appliedTargets && data.type === "body") this.nextBody = data.body;
      else if (this.appliedNotes && data.type === "midi-note") this.nextNote = data.note;
      else if (this.songKeys && data.type === "song-key") this.pendingKeys.push(data.key);
    };
    try {
      if (sampleRate !== options.voice.voice.output_sample_rate_hz) {
        throw new Error("AudioContextの実出力レートがケースと一致しません");
      }
      const calls = options.wasmRenderWarmupCalls;
      const frames = options.wasmDspWarmupFrames;
      const initializationFrame = currentFrame;
      const initializationStart = calls === undefined ? 0 : this.now();
      if (frames !== undefined && calls === undefined) throw new Error("事前描画にはラッパーの準備回数を指定してください");
      let prepareStarted = initializationStart;
      let discardedMs = 0;
      const preparation = frames === undefined || calls === undefined ? undefined : {
        calls, frames,
        mark: (phase: "prepare-start" | "render-start" | "render-end" | "prepare-end") => {
          if (phase === "prepare-start") prepareStarted = this.now();
          else if (phase === "prepare-end") discardedMs = this.now() - prepareStarted;
          else console.timeStamp(`chimera-dsp-${phase}:${currentFrame}`);
        },
      };
      this.engine = new FixedVoiceEngine(options.module, options.voice, mode, false, false, preparation);
      if (calls !== undefined) {
        const began = this.now();
        if (!preparation) this.engine.warmupRenderWrapper(calls);
        this.wrapperWarmup = {
          calls, contextFrame: initializationFrame, engineInitializationMs: began - initializationStart - discardedMs,
          warmupMs: preparation ? discardedMs : this.now() - began,
          ...(preparation && { discardedRenderFrames: preparation.frames }),
        };
      }
    } catch (error) {
      this.engine?.close();
      this.engine = undefined;
      this.post({ type: "error", message: String(error) });
    }
  }

  private post(message: LiveMessage, transfer: Transferable[] = []): void {
    this.port.postMessage(message, transfer);
  }

  private markFinalization(phase: string): void {
    console.timeStamp(`chimera-final-${phase}:${currentFrame}`);
  }

  process(_inputs: Float32Array[][], outputs: Float32Array[][]): boolean {
    const engine = this.engine;
    if (!engine) return false;
    const channel = outputs[0]?.[0];
    if (!channel?.length) return true;
    const began = this.now();
    let probe: FinalizationProbe | undefined;
    try {
      const { quantum, preRoll, maximumVoiced, release } = this.settings;
      if (channel.length !== quantum) {
        throw new Error(`実時間レンダーのブロック長は ${channel.length} でした（ケースの指定は ${quantum}）`);
      }
      // 接続直後にContextが飛んでも、安定した境界まで合成器の時刻を進めない。
      if (!this.armed) {
        this.armed = this.startup.ready(currentFrame, quantum);
        if (!this.armed) {
          channel.fill(0);
          return true;
        }
      }
      if (this.frames === 0) this.firstCallbackMs = began;
      if (this.frames === preRoll) {
        if (!this.settings.midi && !this.songKeys) engine.setGate(1);
        this.post({ type: "voicing" });
      }
      // 同じ描画量子までに届いた目標は最新の組を採用する。
      if (this.appliedTargets && this.nextTargets && this.frames >= preRoll && this.stopFrame === undefined) {
        engine.setManualTargets(this.nextTargets);
        this.appliedTargets[this.targetOffset] = this.frames;
        this.appliedTargets.set(this.nextTargets, this.targetOffset + 1);
        this.targetOffset += MANUAL_EVENT_WORDS;
        this.nextTargets = undefined;
      }
      if (this.stopFrame === undefined && this.frames >= preRoll
          && (this.stopRequested || this.frames === preRoll + maximumVoiced)) {
        this.stopFrame = this.frames;
        this.stopReason = this.stopRequested ? "manual" : "limit";
        if (this.songKeys) engine.stopSong();
        engine.setGate(0);
        this.post({ type: "release" });
      }
      if (this.songKeys && this.frames >= preRoll && this.stopFrame === undefined && this.pendingKeys.length) {
        // 量子の間に届く押下と解放は同じ境界で順番に扱う。
        for (const key of this.pendingKeys) {
          engine.applySongKey(key);
          this.songKeys.push({ frame: this.frames, ...key });
        }
        this.pendingKeys.length = 0;
      }
      if (this.nextBody && this.frames >= preRoll && this.stopFrame === undefined) {
        const cells = engine.switchManualBody(this.nextBody);
        this.bodyChanges.push({ frame: this.frames, body: this.nextBody, cells });
        this.nextBody = undefined;
      }
      if (this.appliedNotes && this.nextNote !== undefined && this.frames >= preRoll && this.stopFrame === undefined) {
        const note = this.nextNote;
        this.nextNote = undefined;
        if (note !== this.currentNote) {
          if (note !== null) engine.setManualPitch(midiFrequency(note));
          engine.setGate(note === null ? 0 : 1);
          this.appliedNotes[this.noteOffset] = this.frames;
          this.appliedNotes[this.noteOffset + 1] = note ?? -1;
          this.noteOffset += MIDI_EVENT_WORDS;
          this.currentNote = note;
        }
      }
      if (this.finalizationProbe && this.stopFrame !== undefined && this.frames + quantum >= this.stopFrame + release) {
        probe = this.finalizationProbe;
        this.markFinalization("render-start");
      }
      engine.renderInto(channel);
      if (probe) this.markFinalization("render-end");
      if (this.firstMemoryGrowthFrame === null && engine.memoryGrowths() > 0) {
        this.firstMemoryGrowthFrame = this.frames;
      }
      this.pcm.set(channel, this.frames);
      this.observations[this.row] = currentFrame;
      this.observations[this.row + 1] = quantum;
      this.observations[this.row + 3] = began - this.firstCallbackMs;
      this.observations.set(engine.readObservation(), this.row + 4);
      this.observations[this.row + 2] = this.now() - began;
      if (probe) this.markFinalization("recorded");
      this.frames += quantum;
      this.row += this.rowWords;
      if (this.stopFrame === undefined || this.frames < this.stopFrame + release) return true;
      const transfer = [this.pcm.buffer, this.observations.buffer];
      if (this.appliedTargets) transfer.push(this.appliedTargets.buffer);
      if (this.appliedNotes) transfer.push(this.appliedNotes.buffer);
      const complete: LiveResult = {
        type: "complete",
        startFrame: preRoll,
        stopFrame: this.stopFrame,
        stopReason: this.stopReason,
        timingClock: this.timingClock,
        startupFirstContextFrame: this.startup.firstContextFrame ?? currentFrame,
        startupCallbacks: this.startup.callbacks,
        startupDiscontinuities: this.startup.discontinuities,
        stableWasmBuffers: engine.buffersAreStable(),
        workletSampleRate: sampleRate,
        internalSampleRate: this.internalSampleRate,
        controlIntervalOutputFrames: engine.controlOutputFrames(),
        wasmMemoryGrowths: engine.memoryGrowths(),
        firstWasmMemoryGrowthFrame: this.firstMemoryGrowthFrame,
        ...(this.wrapperWarmup && { wrapperWarmup: this.wrapperWarmup }),
        ...(probe && { finalizationProbe: probe }),
        ...(this.appliedTargets && { appliedTargets: this.appliedTargets.subarray(0, this.targetOffset) }),
        ...(this.appliedNotes && { appliedNotes: this.appliedNotes.subarray(0, this.noteOffset) }),
        ...(this.songKeys && { songKeys: this.songKeys }),
        ...(this.bodyChanges.length && { bodyChanges: this.bodyChanges }),
        pcm: this.pcm.subarray(0, this.frames),
        observations: this.observations.subarray(0, this.row),
      };
      if (probe) this.markFinalization("post-start");
      this.post(complete, probe === "copy" ? [] : transfer);
      if (probe) {
        this.markFinalization("post-end");
        const detached = this.pcm.byteLength === 0 && this.observations.byteLength === 0;
        const retained = this.pcm.byteLength > 0 && this.observations.byteLength > 0;
        this.markFinalization(detached ? "detached" : retained ? "retained" : "partial");
      }
    } catch (error) {
      channel.fill(0);
      this.post({ type: "error", message: String(error) });
    }
    if (probe) this.markFinalization("free-start");
    engine.close();
    if (probe) this.markFinalization("free-end");
    this.engine = undefined;
    this.port.close();
    if (probe) this.markFinalization("port-closed");
    return false;
  }
}

registerProcessor(LIVE_PROCESSOR, LiveProcessor);
