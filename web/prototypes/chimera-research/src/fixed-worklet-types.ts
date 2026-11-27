import type { AREA_GRID_COLUMNS, BeatCommand, FixedVoiceInput, GLOTTAL_COLUMNS, ScorePreparationSplit, VoiceMode } from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/fixed-voice";

export const PROCESSOR_NAME = "chimera-fixed-voice";
export const SONG_SILENT_LEAD_PROCESSOR = "chimera-song-silent-lead";
export const LIVE_TRACT_BUFFER_COUNT = 4;

export type SongSilentLeadQuanta = 4 | 8;
export type SongSilentLeadOptions = { quanta: SongSilentLeadQuanta; traceInput?: boolean; traceNative?: boolean };
export type SongSilentLeadObservation = {
  quantum: number; frames: number[]; firstValidInputFrame: number; validInputQuanta: number; readyContextFrame: number;
  inputTrace?: { columns: readonly string[]; values: number[]; omittedCallbacks: number };
};

export type ProcessorOptions = {
  module: WebAssembly.Module;
  voice: FixedVoiceInput;
  frames: number;
  observationStride: number;
  tractStride?: number;
  tractGrid?: boolean;
  mode?: Exclude<VoiceMode, "manual">;
  realtime?: {
    leadFrames: number; quantum: number; reportSchedule?: boolean; publishTract?: boolean;
    traceRenderPhases?: boolean | "speech";
    traceWasmCore?: boolean;
    traceFirstOutput?: boolean;
    scorePreparationSplit?: ScorePreparationSplit;
    traceScorePreparationBlocks?: boolean;
    renderPreparation?: {
      calls: number; frames: number; blockFrames: number; distributed?: boolean; firstQuantumOffset?: number;
      startDuringLead?: boolean; deferFinalBlock?: boolean; finalBlockFrames?: number;
    };
  };
};

export const REALTIME_SPEECH_COLUMNS = [
  "context_frame", "quantum_frames", "frames_rendered", "process_ms", "callback_elapsed_ms",
] as const;

export const SCORE_PREPARATION_COLUMNS = [
  "context_frame", "quantum_frames", "prepared_frames",
  "callback_start_ms", "wasm_start_ms", "wasm_end_ms", "silence_ready_ms",
] as const;

export type RealtimeSpeechResult = {
  pcm: Float32Array<ArrayBuffer>;
  timing: Float64Array<ArrayBuffer>;
  timingClock: "performance.now" | "Date.now";
  firstOutputEpochMs?: number;
  startupFirstContextFrame: number;
  startupSecondContextFrame?: number;
  startupContiguousFirstContextFrame: number;
  startupCallbacks: number;
  startupDiscontinuities: number;
  armedContextFrame: number;
  scheduledContextFrame: number;
  leadCallbacks: number;
  firstWasmMemoryGrowthFrame: number | null;
};

export type BeatEvent = BeatCommand & { frame: number; contextFrame: number };

export type BeatProgress = { type: "beat-progress"; framesRendered: number; step: number; playing: boolean };
export type LiveTractMessage = {
  type: "tract-frame";
  frame: number;
  contextFrame: number;
  counts: [number, number];
  values: Float64Array<ArrayBuffer>;
};
export type WorkletCommand = BeatCommand | { type: "return-tract-buffer"; values: Float64Array<ArrayBuffer> };

export type WorkletModuleEvaluation = {
  evaluationStartedAtEpochMs: number;
  registrationStartedAtEpochMs: number;
  registeredAtEpochMs: number;
};

export type WorkletModuleTiming = WorkletModuleEvaluation & { readyPostedAtEpochMs: number };

export type ScoreConstructionTiming = {
  warmUpFrames: number;
  startedAtEpochMs: number;
  finishedAtEpochMs: number;
};

export type ScorePreparationTiming = {
  firstContextFrame: number;
  lastContextFrame: number;
  callbacks: number;
  frames: number;
  discontinuities: number;
  startedAtEpochMs: number;
  finishedAtEpochMs: number;
};

export type WorkletMessage =
  | { type: "ready"; sampleRate: number; moduleTiming?: WorkletModuleTiming; scoreConstruction?: ScoreConstructionTiming }
  | { type: "scheduled"; contextFrame: number }
  | LiveTractMessage
  | BeatProgress
  | {
      type: "complete";
      framesRendered: number;
      callbacks: number;
      shortestQuantum: number;
      longestQuantum: number;
      discontinuities: number;
      firstContextFrame: number;
      stableWasmBuffers: boolean;
      wasmMemoryGrowths?: number;
      scorePreparation?: ScorePreparationTiming;
      renderPreparationTrace?: { contextFrame: number; preparedFrames: number }[];
      scorePreparationTrace?: {
        clock: RealtimeSpeechResult["timingClock"];
        values: Float64Array<ArrayBuffer>;
        omittedCallbacks: number;
      };
      observations: Float64Array<ArrayBuffer>;
      tract?: {
        counts: [number, number]; rows: Float64Array<ArrayBuffer>;
        grid?: { rowWords: number; rows: Float64Array<ArrayBuffer> };
      };
      tractLive?: { capacity: number; sent: number; skipped: number };
      glottal?: Float64Array<ArrayBuffer>;
      radiation?: Float64Array<ArrayBuffer>;
      realtime?: RealtimeSpeechResult;
      beatEvents?: BeatEvent[];
    }
  | { type: "error"; message: string };

export type TractGridSample = { frame: number; rows: number[][] };

export type TractProfile = {
  counts: [number, number];
  rows: number[][];
  acoustics?: { columns: string[]; rows: number[][] };
  grid?: { columns: typeof AREA_GRID_COLUMNS; frames: TractGridSample[] };
};

export type LiveTractSample = {
  grid: TractGridSample;
  contextFrame: number;
  lipMinimum: number;
};

export type GlottalTrace = { columns: typeof GLOTTAL_COLUMNS; values: number[] };
