import type { CreatureMidiInput } from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/creature-midi";
import { alligatorColumns, type AlligatorInput } from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/alligator";
import { elephantColumns, type ElephantInput } from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/elephant";
import { SONGBIRD_CALL_FIELDS, SONGBIRD_FIELDS, type SongbirdInput } from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/songbird";
import { sealColumns, type SealEvent, type SealInput } from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/seal";

export const CREATURE_PROCESSOR = "chimera-creature";
export const CREATURE_TIMING_COLUMNS = ["context_frame", "quantum_frames", "process_ms"] as const;

export type CreatureInput = { kind: "songbird"; input: SongbirdInput }
  | { kind: "seal"; input: SealInput; events: SealEvent[] }
  | { kind: "alligator"; input: AlligatorInput }
  | { kind: "elephant"; input: ElephantInput };

export function creatureSchedule(voice: CreatureInput) {
  return voice.kind === "seal" ? voice.input.breath : voice.input;
}

export function creatureColumns(voice: CreatureInput) {
  if (voice.kind === "alligator") return ["output_frame", "internal_sample", ...alligatorColumns(voice.input)];
  if (voice.kind === "elephant") return ["output_frame", "internal_sample", ...elephantColumns(voice.input)];
  const fields = voice.kind === "seal" ? sealColumns(voice.input)
    : voice.input.observe_call_id ? SONGBIRD_CALL_FIELDS : SONGBIRD_FIELDS;
  return ["output_frame", "internal_sample", ...fields];
}

export type CreatureWorkletOptions = {
  module: WebAssembly.Module;
  voice: CreatureInput;
  observationFrames: number[];
  quantum: number;
  countRenderCalls?: boolean;
  captureMidi?: boolean;
};

export type AppliedCreatureMidi = CreatureMidiInput & { frame: number; contextFrame: number };
export type CreatureMidiCommand = { type: "midi"; input: CreatureMidiInput };

export type CreatureWorkletMessage =
  | { type: "midi-ready" }
  | { type: "error"; message: string }
  | {
      type: "complete";
      sampleRate: number;
      factor: number;
      pcm: Float32Array<ArrayBuffer>;
      observations: Float64Array<ArrayBuffer>;
      timing: Float64Array<ArrayBuffer>;
      renderCalls?: Uint16Array<ArrayBuffer>;
      midiEvents?: AppliedCreatureMidi[];
      startupCallbacks: number;
      startupDiscontinuities: number;
      timingClock: "performance.now" | "Date.now";
    };
