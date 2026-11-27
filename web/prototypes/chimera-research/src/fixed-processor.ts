import {
  FixedVoiceEngine,
  GLOTTAL_COLUMNS,
  RADIATION_COLUMNS,
  observationFields,
  TRACT_ACOUSTIC_WORDS,
  TRACT_GEOMETRY_WORDS,
  BEAT_OBSERVATION_FIELDS,
  type BeatCommand,
} from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/fixed-voice";
import {
  LIVE_TRACT_BUFFER_COUNT, SCORE_PREPARATION_COLUMNS, type BeatEvent, type ProcessorOptions,
  type ScorePreparationTiming, type WorkletCommand, type WorkletMessage, type WorkletModuleEvaluation,
} from "./fixed-worklet-types";
import { RealtimeSpeechCapture } from "./realtime-speech-capture";

declare const currentFrame: number;
declare const sampleRate: number;
declare class AudioWorkletProcessor {
  readonly port: MessagePort;
}

// 先頭2量子と、32量子描画した後の2量子を比較する。
const tracedQuanta = new Set([1, 2, 33, 34]);
const MAX_SCORE_PREPARATION_TRACE_ROWS = 4096;

export class FixedProcessor extends AudioWorkletProcessor {
  private engine: FixedVoiceEngine | undefined;
  private readonly observations: Float64Array<ArrayBuffer>;
  private readonly frames: number;
  private readonly stride: number;
  private readonly rowWords: number;
  private readonly articulated: boolean;
  private readonly realtime?: RealtimeSpeechCapture;
  private readonly traceRenderPhases?: "song" | "speech";
  private readonly traceWasmCore: boolean;
  private readonly traceScorePreparation: boolean;
  private readonly scorePreparationBlocks?: Float64Array<ArrayBuffer>;
  private preparationTraceRows = 0;
  private scorePreparation?: ScorePreparationTiming;
  private reportSchedule = false;
  private readonly preparationQuantumOffset: number;
  private readonly preparationStartsInLead: boolean;
  private readonly preparationFramesBeforeFinalBlock?: number;
  private readonly renderPreparationTrace?: { contextFrame: number; preparedFrames: number }[];
  private nextPreparationFrame?: number;
  private readonly beat?: { pending: BeatCommand[]; events: BeatEvent[]; playing: boolean };
  private readonly glottal?: Float64Array<ArrayBuffer>;
  private readonly radiation?: Float64Array<ArrayBuffer>;
  private readonly liveTract?: { slots: Float64Array<ArrayBuffer>[]; words: number; sent: number; skipped: number };
  private tract?: {
    counts: [number, number]; rows: Float64Array<ArrayBuffer>;
    stride: number; rowWords: number; offset: number; next: number;
    grid?: { rowWords: number; rows: Float64Array<ArrayBuffer>; offset: number };
  };
  private rendered = 0;
  private nextObservation: number;
  private row = 0;
  private callbacks = 0;
  private shortestQuantum = Infinity;
  private longestQuantum = 0;
  private discontinuities = 0;
  private firstContextFrame = 0;
  private nextContextFrame = 0;

  constructor({ processorOptions: options }: { processorOptions: ProcessorOptions }, evaluation?: WorkletModuleEvaluation) {
    super();
    this.frames = options.frames;
    const traceMode = options.realtime?.traceRenderPhases;
    this.traceRenderPhases = traceMode === true ? "song" : traceMode || undefined;
    this.traceWasmCore = options.realtime?.traceWasmCore ?? false;
    this.traceScorePreparation = options.realtime?.scorePreparationSplit !== undefined
      && Boolean(options.realtime.traceFirstOutput || options.realtime.traceScorePreparationBlocks);
    this.preparationQuantumOffset = options.realtime?.renderPreparation?.firstQuantumOffset ?? 0;
    this.preparationStartsInLead = options.realtime?.renderPreparation?.startDuringLead ?? false;
    const warmup = options.realtime?.renderPreparation;
    if (warmup?.deferFinalBlock) {
      this.preparationFramesBeforeFinalBlock = warmup.frames - (warmup.finalBlockFrames ?? warmup.blockFrames);
      this.renderPreparationTrace = [];
    }
    this.articulated = Boolean(options.mode);
    this.rowWords = 1 + observationFields(options.mode).length;
    this.stride = options.observationStride;
    this.nextObservation = Math.min(this.stride, this.frames);
    this.observations = new Float64Array(Math.ceil(this.frames / this.stride) * this.rowWords);
    try {
      if (sampleRate !== options.voice.voice.output_sample_rate_hz) {
        throw new Error("Workletのサンプルレートがケースと一致しません");
      }
      const preparationMode = this.traceRenderPhases ?? "song";
      const mark = (phase: string) => {
        console.timeStamp(`chimera-${preparationMode}-preparation:${phase}`);
        if (phase === "render-end" && warmup) {
          console.timeStamp(`chimera-${preparationMode}-preparation-result:${warmup.frames}:${warmup.blockFrames}:${warmup.calls}`);
        }
      };
      const sourcePreparation = options.mode && "words" in options.mode ? options.mode.sourcePreparation : undefined;
      const scoreTimingStart = sourcePreparation && options.realtime?.traceFirstOutput ? Date.now() : undefined;
      this.engine = new FixedVoiceEngine(
        options.module, options.voice, options.mode, options.tractStride !== undefined, options.tractGrid,
        warmup && { ...warmup, mark, markWrapper: mark }, options.realtime?.scorePreparationSplit,
      );
      if (options.voice.fixed_voice_probe?.radiation_components) {
        this.radiation = new Float64Array(this.frames * RADIATION_COLUMNS.length);
      }
      const scoreConstruction = scoreTimingStart !== undefined && sourcePreparation
        ? { warmUpFrames: sourcePreparation.warmUpFrames, startedAtEpochMs: scoreTimingStart,
          finishedAtEpochMs: Date.now() } : undefined;
      if (options.realtime) {
        if (options.realtime.traceScorePreparationBlocks && this.engine.hasPendingScorePreparation) {
          const rows = Math.min(MAX_SCORE_PREPARATION_TRACE_ROWS, this.engine.remainingScorePreparationCallbacks);
          this.scorePreparationBlocks = new Float64Array(rows * SCORE_PREPARATION_COLUMNS.length);
        }
        this.realtime = new RealtimeSpeechCapture(this.frames, options.realtime.quantum, options.realtime.leadFrames,
          options.realtime.traceFirstOutput);
        this.reportSchedule = options.realtime.reportSchedule ?? false;
        if (options.mode && "text" in options.mode) {
          const beat = { pending: [] as BeatCommand[], events: [] as BeatEvent[], playing: true };
          this.beat = beat;
        }
      }
      const counts = this.engine.tractCellCounts;
      if (counts && options.tractStride) {
        this.glottal = new Float64Array(this.frames * GLOTTAL_COLUMNS.length);
        const stride = options.tractStride;
        const rowWords = 1 + (TRACT_GEOMETRY_WORDS + TRACT_ACOUSTIC_WORDS) * (counts[0] + counts[1]);
        const rowCount = Math.ceil(this.frames / stride);
        const gridWords = 1 + this.engine.tractGridWords;
        this.tract = {
          counts, stride, rowWords, offset: 0, next: Math.min(stride, this.frames),
          rows: new Float64Array(rowCount * rowWords),
          grid: options.tractGrid ? {
            rowWords: gridWords, rows: new Float64Array(rowCount * gridWords), offset: 0,
          } : undefined,
        };
        if (options.realtime?.publishTract && this.tract.grid) {
          const words = rowWords + gridWords - 2;
          this.liveTract = {
            slots: Array.from({ length: LIVE_TRACT_BUFFER_COUNT }, () => new Float64Array(words)),
            words, sent: 0, skipped: 0,
          };
        }
      }
      if (this.beat || this.liveTract) {
        this.port.onmessage = ({ data }: MessageEvent<WorkletCommand>) => {
          if (data.type !== "return-tract-buffer") {
            this.beat?.pending.push(data);
            return;
          }
          const live = this.liveTract;
          if (live && live.slots.length < LIVE_TRACT_BUFFER_COUNT && data.values.length === live.words) {
            live.slots.push(data.values);
          }
        };
      }
      this.post({ type: "ready", sampleRate, ...(scoreConstruction && { scoreConstruction }),
        ...(evaluation && { moduleTiming: { ...evaluation, readyPostedAtEpochMs: Date.now() } }) });
    } catch (error) {
      this.engine?.close();
      this.engine = undefined;
      this.post({ type: "error", message: String(error) });
    }
  }

  private post(message: WorkletMessage, transfer: Transferable[] = []): void {
    this.port.postMessage(message, transfer);
  }

  process(_inputs: Float32Array[][], outputs: Float32Array[][]): boolean {
    const engine = this.engine;
    if (!engine) return false;
    const channel = outputs[0]?.[0];
    if (!channel?.length) return true;
    const realtime = this.realtime;
    const began = realtime?.now() ?? 0;
    try {
      if (realtime) {
        if (engine.hasPendingScorePreparation) {
          const preparationStarted = this.traceScorePreparation ? Date.now() : 0;
          const times = this.scorePreparationBlocks;
          const row = this.preparationTraceRows * SCORE_PREPARATION_COLUMNS.length;
          const clockIsEpoch = realtime.timingClock === "Date.now";
          const record = times !== undefined && row < times.length;
          const wasmStarted = record ? (clockIsEpoch ? preparationStarted : realtime.now()) : 0;
          // 合成器内の予備描画長と、Contextへ無音を返す量子長は独立している。
          const prepared = engine.advanceScorePreparation();
          const wasmFinished = record ? realtime.now() : 0;
          if (this.traceScorePreparation) {
            const stats = this.scorePreparation ??= { firstContextFrame: currentFrame, lastContextFrame: currentFrame,
              callbacks: 0, frames: 0, discontinuities: 0, startedAtEpochMs: preparationStarted, finishedAtEpochMs: 0 };
            if (stats.callbacks > 0 && currentFrame !== stats.lastContextFrame + channel.length) stats.discontinuities++;
            stats.lastContextFrame = currentFrame;
            stats.callbacks++;
            stats.frames += prepared;
            stats.finishedAtEpochMs = record && clockIsEpoch ? wasmFinished : Date.now();
          }
          // 本番状態ができた次の量子から、通常の予約に必要な連続量子を数える。
          channel.fill(0);
          if (record) {
            const silenceReady = realtime.now();
            times[row] = currentFrame;
            times[row + 1] = channel.length;
            times[row + 2] = prepared;
            times[row + 3] = began;
            times[row + 4] = wasmStarted;
            times[row + 5] = wasmFinished;
            times[row + 6] = silenceReady;
            this.preparationTraceRows++;
          }
          return true;
        }
        const ready = realtime.ready(currentFrame, channel.length, began);
        if (this.reportSchedule && realtime.startFrame !== undefined) {
          this.reportSchedule = false;
          this.post({ type: "scheduled", contextFrame: realtime.startFrame });
        }
        if (!ready) {
          if (engine.hasPendingRenderPreparation && (!this.preparationStartsInLead || realtime.startFrame !== undefined)) {
            this.nextPreparationFrame ??= currentFrame + this.preparationQuantumOffset * channel.length;
            if (currentFrame >= this.nextPreparationFrame) {
              const label = `chimera-${this.traceRenderPhases ?? "song"}-preparation-split:${currentFrame}`;
              console.timeStamp(`${label}:start`);
              const rendered = engine.advanceRenderPreparation();
              console.timeStamp(`${label}:end:${rendered}`);
              this.renderPreparationTrace?.push({ contextFrame: currentFrame, preparedFrames: rendered });
              const start = realtime.startFrame;
              // 最後の予定片を発話直前の待機量子に置く計測条件。
              this.nextPreparationFrame = rendered === this.preparationFramesBeforeFinalBlock && start !== undefined
                ? start - channel.length
                : currentFrame + 2 * channel.length;
            }
          }
          if (this.traceRenderPhases && realtime.startFrame === currentFrame + channel.length) {
            for (let index = 0; index < 8; index++) console.timeStamp(`chimera-${this.traceRenderPhases}-phase:calibration`);
          }
          channel.fill(0);
          return true;
        }
        if (engine.hasPendingRenderPreparation) throw new Error("開始予定フレームまでに事前描画が完了しませんでした");
      }
      if (this.callbacks === 0) {
        this.firstContextFrame = currentFrame;
        if (realtime) this.nextContextFrame = currentFrame;
      }
      if (currentFrame !== this.nextContextFrame) this.discontinuities++;
      this.nextContextFrame = currentFrame + channel.length;
      this.callbacks++;
      this.shortestQuantum = Math.min(this.shortestQuantum, channel.length);
      this.longestQuantum = Math.max(this.longestQuantum, channel.length);

      const firstOutputFrame = this.rendered;
      const beat = this.beat;
      const hasBeatCommands = Boolean(beat?.pending.length);
      if (beat) {
        for (const command of beat.pending) {
          engine.applyBeat(command);
          if (command.type === "playing") beat.playing = command.playing;
          beat.events.push({ ...command, frame: firstOutputFrame, contextFrame: currentFrame });
        }
        beat.pending.length = 0;
      }
      const active = Math.min(channel.length, this.frames - this.rendered);
      let offset = 0;
      const trace = this.traceRenderPhases && tracedQuanta.has(this.callbacks)
        ? (phase: string) => console.timeStamp(`chimera-${this.traceRenderPhases}-phase:${firstOutputFrame}:${offset}:${phase}`)
        : undefined;
      const speechTrace = this.traceRenderPhases === "speech" ? trace : undefined;
      const coreTrace = speechTrace && this.traceWasmCore
        ? (phase: number, internalOffset: number) =>
          console.timeStamp(`chimera-speech-core:${firstOutputFrame}:${offset}:${phase}:${internalOffset}`)
        : undefined;
      trace?.("quantum-start");
      const tract = this.tract;
      while (offset < active) {
        const next = Math.min(this.nextObservation, tract?.next ?? Infinity);
        const length = Math.min(active - offset, next - this.rendered, engine.maxFrames);
        const end = offset + length;
        trace?.("render-start");
        engine.renderInto(length === channel.length ? channel : channel.subarray(offset, end), trace, speechTrace, coreTrace);
        trace?.("render-end");
        if (this.glottal) {
          speechTrace?.("glottal-start");
          engine.copyGlottalTraceTo(this.glottal, this.rendered, length);
          speechTrace?.("glottal-end");
        }
        if (this.radiation) engine.copyRadiationTraceTo(this.radiation, this.rendered);
        this.rendered += length;
        offset = end;
        const frame = realtime ? this.rendered - 1 : currentFrame + offset - 1;
        if (this.rendered === this.nextObservation) {
          trace?.("observation-start");
          this.observations[this.row] = frame;
          this.observations.set(engine.readObservation(), this.row + 1);
          this.row += this.rowWords;
          this.nextObservation = Math.min(this.nextObservation + this.stride, this.frames);
          trace?.("observation-end");
        }
        if (tract && this.rendered === tract.next) {
          speechTrace?.("tract-start");
          tract.rows[tract.offset] = frame;
          const acoustic = engine.readTract();
          tract.rows.set(acoustic, tract.offset + 1);
          if (tract.grid) {
            const grid = tract.grid;
            grid.rows[grid.offset] = frame;
            engine.copyTractGridTo(grid.rows, grid.offset + 1);
            const live = this.liveTract;
            if (live) {
              const values = live.slots.pop();
              if (values) {
                values.set(acoustic);
                for (let i = 1; i < grid.rowWords; i++) {
                  values[acoustic.length + i - 1] = grid.rows[grid.offset + i];
                }
                this.post({ type: "tract-frame", frame, contextFrame: currentFrame + offset - 1, counts: tract.counts, values },
                  [values.buffer]);
                live.sent++;
              } else {
                live.skipped++;
              }
            }
            grid.offset += grid.rowWords;
          }
          tract.offset += tract.rowWords;
          tract.next = Math.min(tract.next + tract.stride, this.frames);
          speechTrace?.("tract-end");
        }
      }
      if (active < channel.length) channel.fill(0, active);
      speechTrace?.("capture-start");
      realtime?.record(channel, firstOutputFrame, active, currentFrame, began, engine.memoryGrowths());
      speechTrace?.("capture-end");
      if (beat && (hasBeatCommands || this.callbacks === 1 || this.callbacks % 6 === 0)) {
        const step = engine.readObservation()[BEAT_STEP_COLUMN];
        this.post({ type: "beat-progress", framesRendered: this.rendered, playing: beat.playing, step });
      }
      trace?.("quantum-end");
      if (this.rendered < this.frames) return true;
      const live = realtime?.result();
      const transfer = [this.observations.buffer];
      const scorePreparationTrace = this.scorePreparationBlocks && this.scorePreparation && live ? {
        clock: live.timingClock,
        values: this.scorePreparationBlocks.subarray(0, this.preparationTraceRows * SCORE_PREPARATION_COLUMNS.length),
        omittedCallbacks: this.scorePreparation.callbacks - this.preparationTraceRows,
      } : undefined;
      if (live) transfer.push(live.pcm.buffer, live.timing.buffer);
      if (scorePreparationTrace) transfer.push(scorePreparationTrace.values.buffer);
      if (tract) transfer.push(tract.rows.buffer);
      if (tract?.grid) transfer.push(tract.grid.rows.buffer);
      if (this.glottal) transfer.push(this.glottal.buffer);
      if (this.radiation) transfer.push(this.radiation.buffer);
      this.post({
        type: "complete",
        framesRendered: this.rendered,
        callbacks: this.callbacks,
        shortestQuantum: this.shortestQuantum,
        longestQuantum: this.longestQuantum,
        discontinuities: this.discontinuities,
        firstContextFrame: this.firstContextFrame,
        stableWasmBuffers: engine.buffersAreStable(),
        ...(this.articulated && { wasmMemoryGrowths: engine.memoryGrowths() }),
        ...(this.scorePreparation && { scorePreparation: this.scorePreparation }),
        ...(scorePreparationTrace && { scorePreparationTrace }),
        ...(this.renderPreparationTrace && { renderPreparationTrace: this.renderPreparationTrace }),
        observations: this.observations,
        ...(tract && { tract: { counts: tract.counts, rows: tract.rows, grid: tract.grid } }),
        ...(this.liveTract && { tractLive: {
          capacity: LIVE_TRACT_BUFFER_COUNT, sent: this.liveTract.sent, skipped: this.liveTract.skipped,
        } }),
        ...(this.glottal && { glottal: this.glottal }),
        ...(this.radiation && { radiation: this.radiation }),
        ...(live && { realtime: live }),
        ...(beat && { beatEvents: beat.events }),
      }, transfer);
    } catch (error) {
      channel.fill(0);
      this.post({ type: "error", message: String(error) });
    }
    engine.close();
    this.port.onmessage = null;
    this.engine = undefined;
    return false;
  }
}

const BEAT_STEP_COLUMN = BEAT_OBSERVATION_FIELDS.indexOf("beat_step");
