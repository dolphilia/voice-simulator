import type { CreatureMidiInput } from "./creature-midi";

const MANUAL_FIELDS = ["pitch_hz", "pressure_cm_h2o", "trunk", "chaos"] as const;
const VALVE_PARAMS = ["mode", "lip_pitch_hz"] as const;
export const ELEPHANT_PARAMS = [...MANUAL_FIELDS, ...VALVE_PARAMS] as const;
export const ELEPHANT_CALL_CODES = new Map<string, number>([["rumble", 1], ["trumpet", 2], ["squeak", 3]]);
type ElephantShape = Record<(typeof MANUAL_FIELDS)[number], number>
  & Partial<Record<(typeof VALVE_PARAMS)[number], number>>;

export const ELEPHANT_FIELDS = [
  "gate", ...MANUAL_FIELDS,
  "lung_pressure_dyn_cm2", "lung_flow_cm3_s", "trachea_end_pressure_dyn_cm2", "pharynx_pressure_dyn_cm2",
  "glottis_drive_dyn_cm2", "glottis_area_cm2", "glottis_flow_cm3_s", "glottis_phase", "glottis_f0_hz",
  "oral_tip_area_cm2", "velum_area_cm2", "velum_flow_cm3_s", "nasal_base_pressure_dyn_cm2",
  "trunk_inlet_pressure_dyn_cm2", "trunk_tip_pressure_dyn_cm2", "trunk_valve_area_cm2", "trunk_valve_flow_cm3_s",
  "wall_cm3_s", "oral_cm3_s", "nasal_cm3_s", "radiation_cm3_s2", "decimated", "dc_removed", "target_trunk",
] as const;

const CALL_FIELDS = [
  ...ELEPHANT_FIELDS, "call_id", "control_clock_seconds", "gate_goal", "target_pitch_hz", "target_pressure_cm_h2o",
  "target_chaos",
] as const;

const VALVE_FIELDS = [
  ...CALL_FIELDS, ...VALVE_PARAMS, "target_mode", "target_lip_pitch_hz", "glottis_abduction_cm2",
  "glottis_amplitude_cm2", "glottal_noise_gain", "reed_drive_dyn_cm2", "reed_opening_cm2",
  "reed_height_cm", "reed_speed_cm_s",
] as const;

export function elephantColumns(input: ElephantInput) {
  if (input.observe_valve) return VALVE_FIELDS;
  return input.observe_call ? CALL_FIELDS : ELEPHANT_FIELDS;
}

export type ElephantEvent = {
  frame: number;
  gate?: number;
  held_midi?: { note: number | null };
  midi_call?: { id: string; note: number; pressed: boolean };
  params?: Partial<ElephantShape>;
  play_call?: { id: string; pitch_hz?: number; amplitude?: number };
  stop_call?: boolean;
};

export type ElephantInput = {
  sample_rate_hz: number;
  frames: number;
  shape: ElephantShape;
  level: number;
  events: ElephantEvent[];
  observe_call?: boolean;
  observe_valve?: boolean;
};

type ElephantExports = WebAssembly.Exports & {
  memory: WebAssembly.Memory;
  vocal_elephant_layout_version(): number;
  vocal_elephant_max_frames(): number;
  vocal_elephant_observation_words(): number;
  vocal_elephant_new(rate: number, level: number, pitch: number, pressure: number, trunk: number, chaos: number,
                     mode: number, lipPitch: number): number;
  vocal_elephant_set_gate(handle: number, gate: number): number;
  vocal_elephant_select_midi(handle: number, note: number): number;
  vocal_elephant_midi_call(handle: number, id: number, note: number, pressed: number): number;
  vocal_elephant_set_params(handle: number, pitch: number, pressure: number, trunk: number, chaos: number,
                            mode: number, lipPitch: number): number;
  vocal_elephant_play_call(handle: number, callId: number, pitch: number, amplitude: number): number;
  vocal_elephant_stop_call(handle: number): number;
  vocal_elephant_render(handle: number, frames: number): number;
  vocal_elephant_pcm(handle: number): number;
  vocal_elephant_observation(handle: number): number;
  vocal_elephant_free(handle: number): void;
};

export class ElephantEngine {
  private readonly exports: ElephantExports;
  private readonly buffer: ArrayBuffer;
  private handle: number;
  readonly factor = 1;
  readonly maxFrames: number;
  readonly pcm: Float32Array;
  readonly observation: Float64Array;

  constructor(module: WebAssembly.Module, input: ElephantInput) {
    const exports = new WebAssembly.Instance(module).exports as ElephantExports;
    if (exports.vocal_elephant_layout_version() !== 3
      || exports.vocal_elephant_observation_words() !== VALVE_FIELDS.length) {
      throw new Error("ゾウのWASM観測形式が一致しません");
    }
    const { pitch_hz, pressure_cm_h2o, trunk, chaos, mode = 0, lip_pitch_hz = 470 } = input.shape;
    const handle = exports.vocal_elephant_new(
      input.sample_rate_hz, input.level, pitch_hz, pressure_cm_h2o, trunk, chaos, mode, lip_pitch_hz,
    );
    if (!handle) throw new Error("ゾウの合成器を初期化できません");
    try {
      this.exports = exports;
      this.handle = handle;
      this.buffer = exports.memory.buffer;
      this.maxFrames = exports.vocal_elephant_max_frames();
      this.pcm = new Float32Array(this.buffer, exports.vocal_elephant_pcm(handle), this.maxFrames);
      this.observation = new Float64Array(this.buffer, exports.vocal_elephant_observation(handle), elephantColumns(input).length);
    } catch (error) {
      exports.vocal_elephant_free(handle);
      throw error;
    }
  }

  apply({ params, gate, play_call, stop_call, held_midi, midi_call }: ElephantEvent) {
    const { exports, handle } = this;
    if (held_midi) this.applyMidi(held_midi);
    if (midi_call) this.applyMidi({ call: midi_call.id, note: midi_call.note, pressed: midi_call.pressed });
    if (params) {
      const { pitch_hz, pressure_cm_h2o, trunk, chaos, mode, lip_pitch_hz } = params;
      if (!exports.vocal_elephant_set_params(handle, pitch_hz ?? NaN, pressure_cm_h2o ?? NaN, trunk ?? NaN,
        chaos ?? NaN, mode ?? NaN, lip_pitch_hz ?? NaN)) {
        throw new Error("ゾウの手動目標を設定できません");
      }
    }
    if (gate !== undefined && !exports.vocal_elephant_set_gate(handle, gate)) {
      throw new Error("ゾウの呼気目標を設定できません");
    }
    if (play_call) {
      const callId = ELEPHANT_CALL_CODES.get(play_call.id);
      if (callId === undefined
        || !exports.vocal_elephant_play_call(handle, callId, play_call.pitch_hz ?? NaN, play_call.amplitude ?? 1)) {
        throw new Error("ゾウのコールを開始できません");
      }
    }
    if (stop_call && !exports.vocal_elephant_stop_call(handle)) {
      throw new Error("ゾウのコールを停止できません");
    }
  }

  applyMidi(input: CreatureMidiInput) {
    const { note } = input;
    if ((note !== null && (!Number.isInteger(note) || note < 0 || note > 127))
      || ("call" in input && (note === null || typeof input.pressed !== "boolean"))) {
      throw new Error("MIDI音番号と押下状態を確認してください");
    }
    const success = "call" in input
      ? this.exports.vocal_elephant_midi_call(this.handle, ELEPHANT_CALL_CODES.get(input.call) ?? 0, input.note,
        Number(input.pressed))
      : this.exports.vocal_elephant_select_midi(this.handle, note ?? -1);
    if (!success) {
      throw new Error("ゾウのMIDI入力を適用できません");
    }
  }

  render(frames: number) {
    if (!this.exports.vocal_elephant_render(this.handle, frames)) throw new Error("ゾウの描画に失敗しました");
    if (this.exports.memory.buffer !== this.buffer) throw new Error("ゾウの描画中にWASMメモリが増加しました");
  }

  close() {
    this.exports.vocal_elephant_free(this.handle);
    this.handle = 0;
  }
}
