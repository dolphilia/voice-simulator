import type { FixedVoiceInput, LiveSongKey, LiveSongMode, ManualTargets, VoiceBody } from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/fixed-voice";
import type { AppliedBodyChange } from "./manual-replay";

export const LIVE_PROCESSOR = "chimera-fixed-live";

export type LiveSettings = {
  quantum: number;
  preRoll: number;
  maximumVoiced: number;
  release: number;
  manual?: boolean;
  midi?: boolean;
};

export type LiveCommand = "stop" | { type: "articulation"; targets: ManualTargets }
  | { type: "body"; body: VoiceBody } | { type: "midi-note"; note: number | null }
  | { type: "song-key"; key: LiveSongKey };
export type AppliedSongKey = LiveSongKey & { frame: number };
export const MANUAL_EVENT_WORDS = 4;
export const MIDI_EVENT_WORDS = 2;

export type FinalizationProbe = "transfer" | "copy";

export type LiveOptions = {
  module: WebAssembly.Module;
  voice: FixedVoiceInput;
  settings: LiveSettings;
  song?: LiveSongMode;
  wasmRenderWarmupCalls?: number;
  wasmDspWarmupFrames?: number;
  finalizationProbe?: FinalizationProbe;
};

export type WrapperWarmup = {
  calls: number;
  contextFrame: number;
  engineInitializationMs: number;
  warmupMs: number;
  discardedRenderFrames?: number;
};

export type LiveResult = {
  type: "complete";
  startFrame: number;
  stopFrame: number;
  stopReason: "manual" | "limit";
  timingClock: "performance.now" | "Date.now";
  startupFirstContextFrame: number;
  startupCallbacks: number;
  startupDiscontinuities: number;
  stableWasmBuffers: boolean;
  workletSampleRate: number;
  internalSampleRate: number;
  controlIntervalOutputFrames: number;
  wasmMemoryGrowths: number;
  firstWasmMemoryGrowthFrame: number | null;
  wrapperWarmup?: WrapperWarmup;
  finalizationProbe?: FinalizationProbe;
  appliedTargets?: Float64Array<ArrayBuffer>;
  appliedNotes?: Float64Array<ArrayBuffer>;
  songKeys?: AppliedSongKey[];
  bodyChanges?: AppliedBodyChange[];
  pcm: Float32Array<ArrayBuffer>;
  observations: Float64Array<ArrayBuffer>;
};

export type LiveMessage =
  | { type: "voicing" }
  | { type: "release" }
  | { type: "error"; message: string }
  | LiveResult;
