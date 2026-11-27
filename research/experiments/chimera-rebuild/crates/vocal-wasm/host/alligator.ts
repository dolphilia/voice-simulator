import type { CreatureMidiInput } from "./creature-midi";

const AIRWAY_FIELDS = [
  "lung_pressure_dyn_cm2", "lung_flow_cm3_s", "trachea_inlet_pressure_dyn_cm2", "trachea_end_pressure_dyn_cm2",
  "pharynx_pressure_dyn_cm2", "glottis_drive_dyn_cm2", "glottis_area_cm2", "glottis_flow_cm3_s",
  "glottis_voicing", "glottis_phase", "glottis_f0_hz", "velum_area_cm2", "velum_flow_cm3_s",
  "wall_cm3_s", "oral_cm3_s", "nasal_cm3_s", "radiation_cm3_s2", "oral_tip_area_cm2",
] as const;

const ALLIGATOR_FIELDS = [
  "gate_target", "gate", "oral_noise", "decimated", "dc_removed",
  ...[0, 1].flatMap((phase) => AIRWAY_FIELDS.map((field) => `${field}_${phase}`)),
] as const;

export const ALLIGATOR_CALL_CODES = new Map([["bellow", 1], ["growl", 2], ["hiss", 3], ["dance", 4]]);
export const ALLIGATOR_PARAMS = ["pitch_hz", "chaos", "pressure_cm_h2o", "mouth", "nostrils", "hiss"] as const;
type AlligatorShape = Record<(typeof ALLIGATOR_PARAMS)[number], number>;

const ALLIGATOR_CALL_FIELDS = [
  ...ALLIGATOR_FIELDS, "call_id", "control_clock_seconds",
  ...ALLIGATOR_PARAMS, ...ALLIGATOR_PARAMS.map((field) => `target_${field}`),
] as const;

const NOISE_FIELDS = [
  "glottal_noise_level_dyn_cm2", "glottal_noise_pressure_dyn_cm2", "oral_noise_level_dyn_cm2",
] as const;

const ALLIGATOR_NOISE_FIELDS = [
  ...ALLIGATOR_CALL_FIELDS, ...[0, 1].flatMap((phase) => NOISE_FIELDS.map((field) => `${field}_${phase}`)),
] as const;

export type AlligatorEvent = {
  frame: number;
  gate?: number;
  held_midi?: { note: number | null };
  midi_call?: { id: string; note: number; pressed: boolean };
  params?: Partial<AlligatorShape>;
  play_call?: { id: string; pitch_hz?: number; amplitude?: number };
  stop_call?: boolean;
};

export type AlligatorInput = {
  sample_rate_hz: number;
  frames: number;
  shape: AlligatorShape;
  level: number;
  events: AlligatorEvent[];
  observe_call?: boolean;
  observe_noise?: boolean;
};

export function alligatorColumns(input: AlligatorInput) {
  if (input.observe_noise) return ALLIGATOR_NOISE_FIELDS;
  return input.observe_call ? ALLIGATOR_CALL_FIELDS : ALLIGATOR_FIELDS;
}

type AlligatorExports = WebAssembly.Exports & {
  memory: WebAssembly.Memory;
  vocal_alligator_layout_version(): number;
  vocal_alligator_max_frames(): number;
  vocal_alligator_observation_words(): number;
  vocal_alligator_new(
    rate: number, level: number, pitch: number, chaos: number, pressure: number,
    mouth: number, nostrils: number, hiss: number,
  ): number;
  vocal_alligator_set_gate(handle: number, gate: number): number;
  vocal_alligator_select_midi(handle: number, note: number): number;
  vocal_alligator_midi_call(handle: number, id: number, note: number, pressed: number): number;
  vocal_alligator_set_params(
    handle: number, pitch: number, chaos: number, pressure: number, mouth: number, nostrils: number, hiss: number,
  ): number;
  vocal_alligator_play_call(handle: number, id: number, pitch: number, amplitude: number): number;
  vocal_alligator_stop_call(handle: number): number;
  vocal_alligator_render(handle: number, frames: number): number;
  vocal_alligator_pcm(handle: number): number;
  vocal_alligator_observation(handle: number): number;
  vocal_alligator_factor(handle: number): number;
  vocal_alligator_free(handle: number): void;
};

export class AlligatorEngine {
  private readonly exports: AlligatorExports;
  private readonly buffer: ArrayBuffer;
  private handle: number;
  readonly maxFrames: number;
  readonly factor: number;
  readonly pcm: Float32Array;
  readonly observation: Float64Array;

  constructor(module: WebAssembly.Module, input: AlligatorInput) {
    const exports = new WebAssembly.Instance(module).exports as AlligatorExports;
    if (exports.vocal_alligator_layout_version() !== 3
      || exports.vocal_alligator_observation_words() !== ALLIGATOR_NOISE_FIELDS.length) {
      throw new Error("アリゲーターのWASM観測形式が一致しません");
    }
    const { pitch_hz, chaos, pressure_cm_h2o, mouth, nostrils, hiss } = input.shape;
    const handle = exports.vocal_alligator_new(input.sample_rate_hz, input.level, pitch_hz, chaos, pressure_cm_h2o,
      mouth, nostrils, hiss);
    if (!handle) throw new Error("アリゲーターの合成器を初期化できません");
    try {
      this.exports = exports;
      this.handle = handle;
      this.buffer = exports.memory.buffer;
      this.maxFrames = exports.vocal_alligator_max_frames();
      this.factor = exports.vocal_alligator_factor(handle);
      this.pcm = new Float32Array(this.buffer, exports.vocal_alligator_pcm(handle), this.maxFrames);
      this.observation = new Float64Array(this.buffer, exports.vocal_alligator_observation(handle), alligatorColumns(input).length);
    } catch (error) {
      exports.vocal_alligator_free(handle);
      throw error;
    }
  }

  apply({ params, gate, play_call, stop_call, held_midi, midi_call }: AlligatorEvent): void {
    const { exports, handle } = this;
    if (held_midi) this.applyMidi(held_midi);
    if (midi_call) this.applyMidi({ call: midi_call.id, note: midi_call.note, pressed: midi_call.pressed });
    if (params) {
      const { pitch_hz, chaos, pressure_cm_h2o, mouth, nostrils, hiss } = params;
      if (!exports.vocal_alligator_set_params(handle, pitch_hz ?? NaN, chaos ?? NaN, pressure_cm_h2o ?? NaN,
        mouth ?? NaN, nostrils ?? NaN, hiss ?? NaN)) {
        throw new Error("アリゲーターの手動目標を設定できません");
      }
    }
    if (gate !== undefined && !exports.vocal_alligator_set_gate(handle, gate)) {
      throw new Error("アリゲーターの呼気目標を設定できません");
    }
    if (play_call && !exports.vocal_alligator_play_call(handle,
      ALLIGATOR_CALL_CODES.get(play_call.id) ?? 0, play_call.pitch_hz ?? NaN, play_call.amplitude ?? 1)) {
      throw new Error("アリゲーターのコールを開始できません");
    }
    if (stop_call && !exports.vocal_alligator_stop_call(handle)) {
      throw new Error("アリゲーターのコールを停止できません");
    }
  }

  applyMidi(input: CreatureMidiInput): void {
    const { note } = input;
    if ((note !== null && (!Number.isInteger(note) || note < 0 || note > 127))
      || ("call" in input && (note === null || typeof input.pressed !== "boolean"))) {
      throw new Error("MIDI音番号を確認してください");
    }
    const success = "call" in input
      ? this.exports.vocal_alligator_midi_call(this.handle, ALLIGATOR_CALL_CODES.get(input.call) ?? 0,
        input.note, Number(input.pressed))
      : this.exports.vocal_alligator_select_midi(this.handle, note ?? -1);
    if (!success) {
      throw new Error("アリゲーターのMIDI入力を適用できません");
    }
  }

  render(frames: number): void {
    if (!this.exports.vocal_alligator_render(this.handle, frames)) {
      throw new Error("アリゲーターの描画に失敗しました");
    }
    if (this.exports.memory.buffer !== this.buffer) throw new Error("アリゲーターの描画中にWASMメモリが増加しました");
  }

  close(): void {
    this.exports.vocal_alligator_free(this.handle);
    this.handle = 0;
  }
}
