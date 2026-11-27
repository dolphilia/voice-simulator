import type { CreatureMidiInput } from "./creature-midi";

// 鳴禽のC ABIをAudioWorkletから使うための固定バッファの読み書き。

export const SONGBIRD_FIELDS = [
  "gate", "sac_pressure_dyn_cm2", "left_opening", "right_opening",
  "left_port_area_cm2", "right_port_area_cm2", "left_port_flow_cm3_s", "right_port_flow_cm3_s",
] as const;

const CONTROL_FIELDS = [
  "pitch_hz", "interval_semitones", "voices", "drive", "tension", "pressure_kpa", "purity", "oec_cm3", "gape",
] as const;

export const SONGBIRD_CALL_FIELDS = [
  ...SONGBIRD_FIELDS, "control_clock_seconds", "call_id", "gate_target",
  ...CONTROL_FIELDS, ...CONTROL_FIELDS.map((key) => `target_${key}`),
] as const;

export const SONGBIRD_CALL_CODES: ReadonlyMap<string, number> = new Map([
  ["flute", 1], ["trill", 2], ["chirps", 3], ["buzz", 4],
]);

type SongbirdControls = Record<(typeof CONTROL_FIELDS)[number], number>;

export type SongbirdEvent = {
  frame: number;
  gate?: number;
  held_midi?: { note: number | null };
  midi_call?: { id: string; note: number; pressed: boolean };
  controls?: SongbirdControls;
  play_call?: { id: string; pitch_hz?: number; amplitude?: number };
  stop_call?: boolean;
};

export type SongbirdInput = {
  sample_rate_hz: number;
  frames: number;
  level: number;
  controls: SongbirdControls;
  events: SongbirdEvent[];
  observe_call_id?: boolean;
};

type SongbirdExports = WebAssembly.Exports & {
  memory: WebAssembly.Memory;
  vocal_songbird_layout_version(): number;
  vocal_songbird_max_frames(): number;
  vocal_songbird_observation_words(): number;
  vocal_songbird_new(
    rate: number, level: number, pitch: number, interval: number, voices: number, drive: number,
    tension: number, pressure: number, purity: number, oec: number, gape: number,
  ): number;
  vocal_songbird_set_gate(handle: number, goal: number): number;
  vocal_songbird_select_midi(handle: number, note: number): number;
  vocal_songbird_midi_call(handle: number, id: number, note: number, pressed: number): number;
  vocal_songbird_set_controls(
    handle: number, pitch: number, interval: number, voices: number, drive: number,
    tension: number, pressure: number, purity: number, oec: number, gape: number,
  ): number;
  vocal_songbird_play_call(handle: number, id: number, pitch: number, amplitude: number): number;
  vocal_songbird_stop_call(handle: number): number;
  vocal_songbird_render(handle: number, frames: number): number;
  vocal_songbird_pcm(handle: number): number;
  vocal_songbird_observation(handle: number): number;
  vocal_songbird_factor(handle: number): number;
  vocal_songbird_free(handle: number): void;
};

export class SongbirdEngine {
  private readonly exports: SongbirdExports;
  private readonly buffer: ArrayBuffer;
  private handle: number;
  readonly maxFrames: number;
  readonly factor: number;
  readonly pcm: Float32Array;
  readonly observation: Float64Array;

  constructor(module: WebAssembly.Module, input: SongbirdInput) {
    const exports = new WebAssembly.Instance(module).exports as SongbirdExports;
    if (exports.vocal_songbird_layout_version() !== 2
        || exports.vocal_songbird_observation_words() !== SONGBIRD_CALL_FIELDS.length) {
      throw new Error("鳴禽のWASM観測形式が一致しません");
    }
    const { pitch_hz, interval_semitones, voices, drive, tension, pressure_kpa, purity, oec_cm3, gape } = input.controls;
    const handle = exports.vocal_songbird_new(input.sample_rate_hz, input.level, pitch_hz, interval_semitones,
      voices, drive, tension, pressure_kpa, purity, oec_cm3, gape);
    if (!handle) throw new Error("鳴禽の合成器を初期化できません");
    try {
      this.exports = exports;
      this.handle = handle;
      this.buffer = exports.memory.buffer;
      this.maxFrames = exports.vocal_songbird_max_frames();
      this.factor = exports.vocal_songbird_factor(handle);
      this.pcm = new Float32Array(this.buffer, exports.vocal_songbird_pcm(handle), this.maxFrames);
      const width = input.observe_call_id ? SONGBIRD_CALL_FIELDS.length : SONGBIRD_FIELDS.length;
      this.observation = new Float64Array(this.buffer, exports.vocal_songbird_observation(handle), width);
    } catch (error) {
      exports.vocal_songbird_free(handle);
      throw error;
    }
  }

  apply(event: SongbirdEvent): void {
    const { gate, controls, play_call, stop_call, held_midi, midi_call } = event;
    if (held_midi) this.applyMidi(held_midi);
    if (midi_call) this.applyMidi({ call: midi_call.id, note: midi_call.note, pressed: midi_call.pressed });
    if (gate !== undefined && !this.exports.vocal_songbird_set_gate(this.handle, gate)) {
      throw new Error("鳴禽の呼気目標を設定できません");
    }
    if (controls) {
      const { pitch_hz, interval_semitones, voices, drive, tension, pressure_kpa, purity, oec_cm3, gape } = controls;
      if (!this.exports.vocal_songbird_set_controls(this.handle, pitch_hz, interval_semitones,
        voices, drive, tension, pressure_kpa, purity, oec_cm3, gape)) {
        throw new Error("鳴禽の演奏パラメータを設定できません");
      }
    }
    if (play_call && !this.exports.vocal_songbird_play_call(this.handle,
      SONGBIRD_CALL_CODES.get(play_call.id) ?? 0, play_call.pitch_hz ?? NaN, play_call.amplitude ?? 1)) {
      throw new Error("鳴禽のコールを開始できません");
    }
    if (stop_call && !this.exports.vocal_songbird_stop_call(this.handle)) throw new Error("鳴禽のコールを停止できません");
  }

  applyMidi(input: CreatureMidiInput): void {
    const { note } = input;
    if (note !== null && (!Number.isInteger(note) || note < 0 || note > 127)) {
      throw new Error("MIDI音番号を確認してください");
    }
    const success = "call" in input
      ? this.exports.vocal_songbird_midi_call(this.handle, SONGBIRD_CALL_CODES.get(input.call) ?? 0, input.note,
        Number(input.pressed))
      : this.exports.vocal_songbird_select_midi(this.handle, note ?? -1);
    if (!success) {
      throw new Error("鳴禽のMIDI入力を適用できません");
    }
  }

  render(frames: number): void {
    if (!this.exports.vocal_songbird_render(this.handle, frames)) throw new Error("鳴禽のレンダーに失敗しました");
    if (this.exports.memory.buffer !== this.buffer) throw new Error("鳴禽のレンダー中にWASMメモリが増加しました");
  }

  close(): void {
    this.exports.vocal_songbird_free(this.handle);
    this.handle = 0;
  }
}
