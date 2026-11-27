import { REALTIME_SPEECH_COLUMNS, type RealtimeSpeechResult } from "./fixed-worklet-types";
import { WorkletStartup } from "./worklet-clock";

export class RealtimeSpeechCapture {
  private readonly startup = new WorkletStartup();
  readonly timingClock = typeof performance === "undefined" ? "Date.now" : "performance.now";
  readonly now = this.timingClock === "performance.now" ? performance.now.bind(performance) : Date.now;
  private readonly pcm: Float32Array<ArrayBuffer>;
  private readonly timing: Float64Array<ArrayBuffer>;
  private armedContextFrame?: number;
  private scheduledContextFrame?: number;
  private leadCallbacks = 0;
  private firstCallbackMs = 0;
  private firstOutputEpochMs?: number;
  private startupSecondContextFrame?: number;
  private firstWasmMemoryGrowthFrame: number | null = null;
  private row = 0;

  constructor(frames: number, private readonly quantum: number, private readonly leadFrames: number,
    private readonly traceFirstOutput = false) {
    this.pcm = new Float32Array(frames);
    this.timing = new Float64Array(Math.ceil(frames / quantum) * REALTIME_SPEECH_COLUMNS.length);
  }

  get startFrame(): number | undefined {
    return this.scheduledContextFrame;
  }

  ready(frame: number, quantum: number, began: number): boolean {
    if (quantum !== this.quantum) throw new Error(`実時間の描画量子が ${quantum} フレームでした`);
    if (this.scheduledContextFrame === undefined) {
      if (this.traceFirstOutput && this.startup.callbacks === 1) this.startupSecondContextFrame = frame;
      if (!this.startup.ready(frame, quantum)) return false;
      this.armedContextFrame = frame;
      this.scheduledContextFrame = frame + this.leadFrames;
    }
    if (frame < this.scheduledContextFrame) {
      this.leadCallbacks++;
      return false;
    }
    if (this.row === 0) {
      if (frame !== this.scheduledContextFrame) {
        throw new Error(`実時間発話の予定フレーム ${this.scheduledContextFrame} を通過しました（実測 ${frame}）`);
      }
      if (this.traceFirstOutput) this.firstOutputEpochMs = this.timingClock === "Date.now" ? began : Date.now();
    }
    return true;
  }

  record(channel: Float32Array, firstOutputFrame: number, frames: number,
    contextFrame: number, began: number, growths: number) {
    if (this.row === 0) this.firstCallbackMs = began;
    if (growths > 0) this.firstWasmMemoryGrowthFrame ??= firstOutputFrame;
    this.pcm.set(frames === channel.length ? channel : channel.subarray(0, frames), firstOutputFrame);
    this.timing[this.row] = contextFrame;
    this.timing[this.row + 1] = channel.length;
    this.timing[this.row + 2] = firstOutputFrame + frames;
    this.timing[this.row + 3] = this.now() - began;
    this.timing[this.row + 4] = began - this.firstCallbackMs;
    this.row += REALTIME_SPEECH_COLUMNS.length;
  }

  result(): RealtimeSpeechResult {
    if (this.startup.firstContextFrame === undefined || this.startup.contiguousFirstContextFrame === undefined
        || this.armedContextFrame === undefined
        || this.scheduledContextFrame === undefined) {
      throw new Error("実時間発話の開始時刻が記録されていません");
    }
    return {
      pcm: this.pcm, timing: this.timing, timingClock: this.timingClock,
      ...(this.firstOutputEpochMs !== undefined && { firstOutputEpochMs: this.firstOutputEpochMs }),
      startupFirstContextFrame: this.startup.firstContextFrame,
      ...(this.startupSecondContextFrame !== undefined && { startupSecondContextFrame: this.startupSecondContextFrame }),
      startupContiguousFirstContextFrame: this.startup.contiguousFirstContextFrame,
      startupCallbacks: this.startup.callbacks,
      startupDiscontinuities: this.startup.discontinuities,
      armedContextFrame: this.armedContextFrame,
      scheduledContextFrame: this.scheduledContextFrame,
      leadCallbacks: this.leadCallbacks,
      firstWasmMemoryGrowthFrame: this.firstWasmMemoryGrowthFrame,
    };
  }
}
