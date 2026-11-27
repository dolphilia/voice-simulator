import type { CreatureMidiInput } from "./creature-midi";

const SEAL_FIELDS = [
  "gate_target", "gate", "lung_pressure_dyn_cm2",
  "wall_0", "oral_0", "nasal_0", "radiation_0",
  "wall_1", "oral_1", "nasal_1", "radiation_1",
  "decimated", "dc_removed",
] as const;

const SEAL_CALL_FIELDS = [
  ...SEAL_FIELDS, "active_call", "control_clock_seconds", "pitch_hz", "target_pitch_hz",
  "pulse_rate_hz", "pulse_depth", "duty", "pressure_cm_h2o",
  "target_pulse_rate_hz", "target_pulse_depth", "target_duty", "target_pressure_cm_h2o", "pulse_phase", "call_id",
] as const;

const SEAL_GLOTTIS_FIELDS = [
  ...SEAL_CALL_FIELDS, "roughness", "target_roughness",
  "glottis_phase_0", "glottis_f0_hz_0", "glottis_area_cm2_0",
  "glottis_phase_1", "glottis_f0_hz_1", "glottis_area_cm2_1",
] as const;

export const SEAL_CALL_CODES = new Map([["trill", 1], ["zap", 2], ["whistle", 3], ["chug", 4]]);

type BreathControls = { pulse_rate_hz: number; pulse_depth: number; duty: number; pressure_cm_h2o: number };
export type SealBreathEvent = { frame: number; gate?: number; controls?: BreathControls };
export type SealCallEvent = {
  frame: number;
  held_midi?: { note: number | null };
  midi_call?: { id: string; note: number; pressed: boolean };
  pitch_hz?: number;
  roughness?: number;
  play_call?: { id: string; pitch_hz?: number; amplitude?: number };
  stop_call?: boolean;
};
export type SealEvent = { frame: number; breath?: SealBreathEvent; call?: SealCallEvent };

export type SealInput = {
  breath: {
    sample_rate_hz: number;
    frames: number;
    controls: BreathControls;
    events: SealBreathEvent[];
  };
  shape: { pitch_hz: number; brightness: number; roughness: number; mouth: number };
  level: number;
  events?: SealCallEvent[];
  observe_call_id?: boolean;
  observe_glottis?: boolean;
};

export function sealColumns(input: SealInput) {
  if (input.observe_glottis) return SEAL_GLOTTIS_FIELDS;
  return input.observe_call_id || input.events?.length ? SEAL_CALL_FIELDS : SEAL_FIELDS;
}

type SealExports = WebAssembly.Exports & {
  memory: WebAssembly.Memory;
  vocal_seal_layout_version(): number;
  vocal_seal_max_frames(): number;
  vocal_seal_observation_words(): number;
  vocal_seal_new(
    rate: number, level: number, pulseRate: number, pulseDepth: number, duty: number, pressure: number,
    pitch: number, brightness: number, roughness: number, mouth: number,
  ): number;
  vocal_seal_set_gate(handle: number, gate: number): number;
  vocal_seal_set_breath(handle: number, pulseRate: number, depth: number, duty: number, pressure: number): number;
  vocal_seal_set_pitch(handle: number, pitch: number): number;
  vocal_seal_select_midi(handle: number, note: number): number;
  vocal_seal_midi_call(handle: number, id: number, note: number, pressed: number): number;
  vocal_seal_set_roughness(handle: number, roughness: number): number;
  vocal_seal_play_call(handle: number, id: number, pitch: number, amplitude: number): number;
  vocal_seal_stop_call(handle: number): number;
  vocal_seal_render(handle: number, frames: number): number;
  vocal_seal_pcm(handle: number): number;
  vocal_seal_observation(handle: number): number;
  vocal_seal_factor(handle: number): number;
  vocal_seal_free(handle: number): void;
};

export class SealEngine {
  private readonly exports: SealExports;
  private readonly buffer: ArrayBuffer;
  private handle: number;
  readonly maxFrames: number;
  readonly factor: number;
  readonly pcm: Float32Array;
  readonly observation: Float64Array;

  constructor(module: WebAssembly.Module, input: SealInput) {
    const exports = new WebAssembly.Instance(module).exports as SealExports;
    if (exports.vocal_seal_layout_version() !== 3 || exports.vocal_seal_observation_words() !== SEAL_GLOTTIS_FIELDS.length) {
      throw new Error("アザラシのWASM観測形式が一致しません");
    }
    const { pulse_rate_hz, pulse_depth, duty, pressure_cm_h2o } = input.breath.controls;
    const { pitch_hz, brightness, roughness, mouth } = input.shape;
    const handle = exports.vocal_seal_new(input.breath.sample_rate_hz, input.level, pulse_rate_hz, pulse_depth, duty,
      pressure_cm_h2o, pitch_hz, brightness, roughness, mouth);
    if (!handle) throw new Error("アザラシの合成器を初期化できません");
    try {
      this.exports = exports;
      this.handle = handle;
      this.buffer = exports.memory.buffer;
      this.maxFrames = exports.vocal_seal_max_frames();
      this.factor = exports.vocal_seal_factor(handle);
      this.pcm = new Float32Array(this.buffer, exports.vocal_seal_pcm(handle), this.maxFrames);
      this.observation = new Float64Array(this.buffer, exports.vocal_seal_observation(handle), sealColumns(input).length);
    } catch (error) {
      exports.vocal_seal_free(handle);
      throw error;
    }
  }

  apply({ breath, call }: SealEvent): void {
    const { exports, handle } = this;
    if (breath?.controls) {
      const { pulse_rate_hz, pulse_depth, duty, pressure_cm_h2o } = breath.controls;
      if (!exports.vocal_seal_set_breath(handle, pulse_rate_hz, pulse_depth, duty, pressure_cm_h2o)) {
        throw new Error("アザラシの呼気制御を設定できません");
      }
    }
    if (breath?.gate !== undefined && !exports.vocal_seal_set_gate(handle, breath.gate)) {
      throw new Error("アザラシの呼気目標を設定できません");
    }
    if (!call) return;
    const { pitch_hz, roughness, play_call, stop_call, held_midi, midi_call } = call;
    if (held_midi) this.applyMidi(held_midi);
    if (midi_call) this.applyMidi({ call: midi_call.id, note: midi_call.note, pressed: midi_call.pressed });
    if (pitch_hz !== undefined && !exports.vocal_seal_set_pitch(handle, pitch_hz)) {
      throw new Error("アザラシの手動音高を設定できません");
    }
    if (roughness !== undefined && !exports.vocal_seal_set_roughness(handle, roughness)) {
      throw new Error("アザラシの手動の粗さを設定できません");
    }
    if (play_call && !exports.vocal_seal_play_call(handle,
      SEAL_CALL_CODES.get(play_call.id) ?? 0, play_call.pitch_hz ?? NaN, play_call.amplitude ?? 1)) {
      throw new Error("アザラシのコールを開始できません");
    }
    if (stop_call && !exports.vocal_seal_stop_call(handle)) throw new Error("アザラシのコールを停止できません");
  }

  applyMidi(input: CreatureMidiInput): void {
    const { note } = input;
    if (note !== null && (!Number.isInteger(note) || note < 0 || note > 127)) {
      throw new Error("MIDI音番号を確認してください");
    }
    const success = "call" in input
      ? this.exports.vocal_seal_midi_call(this.handle, SEAL_CALL_CODES.get(input.call) ?? 0, input.note,
        Number(input.pressed))
      : this.exports.vocal_seal_select_midi(this.handle, note ?? -1);
    if (!success) {
      throw new Error("アザラシのMIDI入力を適用できません");
    }
  }

  render(frames: number): void {
    if (!this.exports.vocal_seal_render(this.handle, frames)) throw new Error("アザラシの描画に失敗しました");
    if (this.exports.memory.buffer !== this.buffer) throw new Error("アザラシの描画中にWASMメモリが増加しました");
  }

  close(): void {
    this.exports.vocal_seal_free(this.handle);
    this.handle = 0;
  }
}
