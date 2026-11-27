import type { CreatureMidiInput } from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/creature-midi";
import { AlligatorEngine } from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/alligator";
import { ElephantEngine } from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/elephant";
import { SongbirdEngine } from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/songbird";
import { SealEngine } from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/seal";
import {
  CREATURE_PROCESSOR, CREATURE_TIMING_COLUMNS, creatureColumns, creatureSchedule,
  type AppliedCreatureMidi, type CreatureInput, type CreatureMidiCommand,
  type CreatureWorkletMessage, type CreatureWorkletOptions,
} from "./creature-worklet-types";
import { WorkletStartup } from "./worklet-clock";

declare const sampleRate: number;
declare const currentFrame: number;
declare class AudioWorkletProcessor {
  readonly port: MessagePort;
}
declare function registerProcessor(name: string, ctor: typeof CreatureProcessor): void;

const SOURCE_CLOCK = globalThis.performance ? "performance.now" : "Date.now";
const now = globalThis.performance ? globalThis.performance.now.bind(globalThis.performance) : Date.now;

function createRenderer(module: WebAssembly.Module, voice: CreatureInput) {
  if (voice.kind === "seal") {
    const engine = new SealEngine(module, voice.input);
    const events = voice.events;
    return { engine, events, apply: (index: number) => engine.apply(events[index]),
      applyMidi: (input: CreatureMidiInput) => engine.applyMidi(input) };
  }
  if (voice.kind === "alligator") {
    const engine = new AlligatorEngine(module, voice.input);
    const events = voice.input.events;
    return { engine, events, apply: (index: number) => engine.apply(events[index]),
      applyMidi: (input: CreatureMidiInput) => engine.applyMidi(input) };
  }
  if (voice.kind === "elephant") {
    const engine = new ElephantEngine(module, voice.input);
    const events = voice.input.events;
    return { engine, events, apply: (index: number) => engine.apply(events[index]),
      applyMidi: (input: CreatureMidiInput) => engine.applyMidi(input) };
  }
  const engine = new SongbirdEngine(module, voice.input);
  const events = voice.input.events;
  return { engine, events, apply: (index: number) => engine.apply(events[index]),
    applyMidi: (input: CreatureMidiInput) => engine.applyMidi(input) };
}

class CreatureProcessor extends AudioWorkletProcessor {
  private renderer?: ReturnType<typeof createRenderer>;
  private readonly pcm: Float32Array<ArrayBuffer>;
  private readonly observations: Float64Array<ArrayBuffer>;
  private readonly timing: Float64Array<ArrayBuffer>;
  private readonly renderCalls?: Uint16Array<ArrayBuffer>;
  private readonly startup = new WorkletStartup();
  private rendered = 0;
  private readonly observationWidth: number;
  private observationIndex = 0;
  private timingOffset = 0;
  private nextEvent = 0;
  private readonly outputFrames: number;
  private readonly midi?: { pending: CreatureMidiInput[]; applied: AppliedCreatureMidi[] };

  constructor({ processorOptions: options }: { processorOptions: CreatureWorkletOptions }) {
    super();
    this.options = options;
    const { voice, observationFrames, quantum } = options;
    const { frames, sample_rate_hz } = creatureSchedule(voice);
    this.outputFrames = frames;
    this.observationWidth = creatureColumns(voice).length;
    this.pcm = new Float32Array(frames);
    this.observations = new Float64Array(observationFrames.length * this.observationWidth);
    const blocks = Math.ceil(frames / quantum);
    this.timing = new Float64Array(blocks * CREATURE_TIMING_COLUMNS.length);
    if (options.countRenderCalls) this.renderCalls = new Uint16Array(blocks);
    try {
      if (sampleRate !== sample_rate_hz) throw new Error("動物音声のWorkletとケースのレートが一致しません");
      this.renderer = createRenderer(options.module, voice);
      if (options.captureMidi) {
        if (!this.renderer.applyMidi) throw new Error("この動物ではMIDI入力を使えません");
        const midi = { pending: [] as CreatureMidiInput[], applied: [] as AppliedCreatureMidi[] };
        this.midi = midi;
        this.port.onmessage = ({ data }: MessageEvent<CreatureMidiCommand>) => {
          if (data.type === "midi") midi.pending.push(data.input);
        };
      }
    } catch (error) {
      this.fail(error);
    }
  }
  private readonly options: CreatureWorkletOptions;

  process(_inputs: Float32Array[][], outputs: Float32Array[][]): boolean {
    const renderer = this.renderer;
    if (!renderer) return false;
    const { engine, events, apply } = renderer;
    const channel = outputs[0]?.[0];
    if (!channel?.length) return true;
    const { observationFrames, quantum } = this.options;
    try {
      if (channel.length !== quantum) throw new Error(`動物音声の描画量子は ${channel.length} フレームでした`);
      if (this.rendered === 0 && !this.startup.ready(currentFrame, channel.length)) {
        channel.fill(0);
        return true;
      }
      const began = now();
      const midi = this.midi;
      if (midi && renderer.applyMidi) {
        if (this.rendered === 0) this.port.postMessage({ type: "midi-ready" } satisfies CreatureWorkletMessage);
        for (const input of midi.pending) {
          renderer.applyMidi(input);
          midi.applied.push({ ...input, frame: this.rendered, contextFrame: currentFrame });
        }
        midi.pending.length = 0;
      }
      const end = Math.min(this.outputFrames, this.rendered + channel.length);
      let position = 0;
      let calls = 0;
      while (this.rendered < end) {
        let event = events[this.nextEvent];
        while (event && event.frame === this.rendered) {
          apply(this.nextEvent);
          event = events[++this.nextEvent];
        }
        // 量子内でも、イベントと観測点の前で分ける。Rust側の64フレームの制御時刻は続行する。
        const observationEnd = observationFrames[this.observationIndex] + 1;
        const length = Math.min(end, event?.frame ?? end, observationEnd, this.rendered + engine.maxFrames) - this.rendered;
        engine.render(length);
        calls++;
        for (let i = 0; i < length; i++) {
          const sample = engine.pcm[i];
          channel[position + i] = sample;
          this.pcm[this.rendered + i] = sample;
        }
        position += length;
        this.rendered += length;
        if (this.rendered === observationEnd) {
          const offset = this.observationIndex * this.observationWidth;
          this.observations[offset] = this.rendered - 1;
          this.observations[offset + 1] = this.rendered * engine.factor - 1;
          this.observations.set(engine.observation, offset + 2);
          this.observationIndex++;
        }
      }
      channel.fill(0, position);
      this.timing[this.timingOffset++] = currentFrame;
      this.timing[this.timingOffset++] = quantum;
      this.timing[this.timingOffset++] = now() - began;
      if (this.renderCalls) this.renderCalls[this.timingOffset / CREATURE_TIMING_COLUMNS.length - 1] = calls;
      if (this.rendered !== this.outputFrames) return true;
      const result: CreatureWorkletMessage = {
        type: "complete", sampleRate, factor: engine.factor, pcm: this.pcm,
        observations: this.observations, timing: this.timing,
        renderCalls: this.renderCalls, midiEvents: midi?.applied,
        startupCallbacks: this.startup.callbacks, startupDiscontinuities: this.startup.discontinuities,
        timingClock: SOURCE_CLOCK,
      };
      engine.close();
      this.port.onmessage = null;
      this.renderer = undefined;
      const transfer = [this.pcm.buffer, this.observations.buffer, this.timing.buffer];
      if (this.renderCalls) transfer.push(this.renderCalls.buffer);
      this.port.postMessage(result, transfer);
      return false;
    } catch (error) {
      channel.fill(0);
      this.fail(error);
      return false;
    }
  }

  private fail(error: unknown): void {
    this.port.onmessage = null;
    this.renderer?.engine.close();
    this.renderer = undefined;
    const message: CreatureWorkletMessage = { type: "error", message: String(error) };
    this.port.postMessage(message);
  }
}

registerProcessor(CREATURE_PROCESSOR, CreatureProcessor);
