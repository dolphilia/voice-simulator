// 固定発声を無輸入のWASMで動かす。準備と観測の書式は配置バージョン1。
export const TRACT_GEOMETRY_WORDS = 3;
export const TRACT_ACOUSTIC_WORDS = 2;
export const AREA_GRID_COLUMNS = [
  "region", "inner_x_cm", "inner_y_cm", "outer_x_cm", "outer_y_cm", "mid_x_cm", "mid_y_cm",
  "ray_cm", "gap_cm", "area_cm2", "s_cm",
] as const;
export const GLOTTAL_COLUMNS = ["glottal_area_cm2", "glottal_flow_cm3_s"] as const;
export const RADIATION_COLUMNS = [
  "wall_radiation_flow_cm3_s", "lip_flow_cm3_s", "nose_flow_cm3_s",
  "radiation_flow_cm3_s", "radiation_derivative_cm3_s2",
] as const;

export type VoiceBodyName = "male" | "female" | "child";
export type VoiceBody = VoiceBodyName | { female: number; child: number };

export function bodyAxes(body: VoiceBody): [number, number] {
  if (typeof body === "object") return [body.female, body.child];
  switch (body) {
    case "male": return [0, 0];
    case "female": return [1, 0];
    case "child": return [0, 1];
  }
}

export type FixedVoiceInput = {
  body: VoiceBody;
  posture: {
    jaw_cm: number;
    tongue_body_cm: [number, number];
    tongue_tip_cm: [number, number];
    tip_curl: number;
    tongue_root_cm: number;
    lip_aperture_cm: number;
    lip_protrusion_cm: number;
    lip_spread: number;
    labiodental: number;
    velum_cm2: number;
    larynx_cm: number;
    epilarynx?: number;
    ventricular?: number;
    lateral?: number;
    dorsum: number;
  };
  fixed_airway: {
    sample_rate_hz: number;
    impulse_volume_cm3: number;
    sample_count: number;
  };
  fixed_voice_probe?: { radiation_components?: boolean; internal_trace?: boolean };
  voice: {
    pressure_cm_h2o: number;
    gate: number;
    f0_hz: number;
    breathiness: number;
    tension: number;
    output_gain: number;
    output_sample_rate_hz: number;
  };
};

export const OBSERVATION_FIELDS = [
  "frames_rendered",
  "gate",
  "glottal_area_cm2",
  "glottal_flow_cm3_s",
  "glottal_phase",
  "glottal_voicing",
  "glottal_f0_hz",
  "radiation_derivative_cm3_s2",
] as const;

export const SPEECH_OBSERVATION_FIELDS = [...OBSERVATION_FIELDS, "lip_aperture_cm", "lip_minimum_cm2"] as const;

export const SONG_OBSERVATION_FIELDS = [...SPEECH_OBSERVATION_FIELDS, "smoothed_f0_hz", "abduction_cm2"] as const;
export const MANUAL_OBSERVATION_FIELDS = [
  ...SONG_OBSERVATION_FIELDS, "tongue_body_x_cm", "tongue_body_y_cm", "oral_minimum_cm2",
] as const;

export const ENGLISH_OBSERVATION_FIELDS = [
  ...MANUAL_OBSERVATION_FIELDS, "nose_flow_cm3_s", "velum_port_area_cm2",
] as const;

export const BEAT_OBSERVATION_FIELDS = [...ENGLISH_OBSERVATION_FIELDS, "beat_step", "beat_next_step"] as const;
const FRICATION_FIELDS = [
  "noise_minimum_cm2", "teeth_noise_source", "teeth_noise_level", "teeth_noise_forward_pressure",
] as const;
const IPA_FRICATION_OBSERVATION_FIELDS = [...SPEECH_OBSERVATION_FIELDS, ...FRICATION_FIELDS] as const;

export type ManualTargets = [tongueBodyX: number, tongueBodyY: number, lipAperture: number];

export type ScoreTurbulence = {
  scale: number;
  glottis_gain_multiplier?: number;
  constriction_gain_multiplier?: number;
  teeth_lowpass_floor_hz?: number;
};

export type VoiceScore = {
  words: Float64Array<ArrayBuffer>;
  noiseScale: number | null;
  turbulence?: ScoreTurbulence;
  basePitchHz?: number;
  sourcePreparation?: {
    warmUpFrames: number;
    pitchDriftCents: number;
    periodJitter: number;
    amplitudeShimmer: number;
  };
  observeNasal?: boolean;
  observeTongue?: boolean;
  observeIpa?: "speech" | "frication";
};

export type BeatPattern = {
  pattern: string;
  bpm: number;
  swing: number;
  initialPitchHz: number;
  noiseScale: number;
};

export type BeatCommand =
  | { type: "tempo"; bpm?: number; swing?: number }
  | { type: "playing"; playing: boolean }
  | { type: "bass_key"; note: number; pressed: boolean }
  | { type: "toggle_hum"; step: number };

type EncodedBeatPattern = Omit<BeatPattern, "pattern"> & { text: Uint8Array<ArrayBuffer> };

export type LiveSongKey = { type: "note-on"; note: number; velocity: number } | { type: "note-off"; note: number };
export type LiveSongMode = { syllableBytes: Uint8Array<ArrayBuffer>; vibratoCents: number };
export type VoiceMode = VoiceScore | EncodedBeatPattern | LiveSongMode | "manual";

export function observationFields(mode?: VoiceMode): readonly string[] {
  if (mode === "manual") return MANUAL_OBSERVATION_FIELDS;
  if (!mode) return OBSERVATION_FIELDS;
  if ("text" in mode) return BEAT_OBSERVATION_FIELDS;
  if ("syllableBytes" in mode) return SONG_OBSERVATION_FIELDS;
  if (mode.observeNasal) return ENGLISH_OBSERVATION_FIELDS;
  if (mode.observeTongue) return MANUAL_OBSERVATION_FIELDS;
  if (mode.observeIpa === "frication") return IPA_FRICATION_OBSERVATION_FIELDS;
  if (mode.observeIpa) return SPEECH_OBSERVATION_FIELDS;
  return mode.basePitchHz === undefined ? SPEECH_OBSERVATION_FIELDS : SONG_OBSERVATION_FIELDS;
}

type Exports = {
  memory: WebAssembly.Memory;
  vocal_layout_version(): number;
  vocal_max_frames(): number;
  vocal_control_output_frames(): number;
  vocal_new(internalRate: number, outputRate: number): number;
  vocal_free(handle: number): void;
  vocal_config(handle: number): number;
  vocal_start(handle: number): number;
  vocal_start_manual(handle: number): number;
  vocal_set_manual_targets(handle: number, tongueX: number, tongueY: number, lipAperture: number): number;
  vocal_set_manual_pitch(handle: number, f0Hz: number): number;
  vocal_switch_manual_body(handle: number, female: number, child: number): number;
  vocal_score_buffer(handle: number, words: number): number;
  vocal_start_score_with_body(handle: number, noiseScale: number, basePitchHz: number,
    female: number, child: number): number;
  vocal_start_score_with_turbulence(handle: number, noiseScale: number, basePitchHz: number,
    female: number, child: number, glottisGain: number, constrictionGain: number, teethLowpassFloorHz: number): number;
  vocal_start_score_prepared(handle: number, noiseScale: number, basePitchHz: number,
    female: number, child: number, glottisGain: number, constrictionGain: number, teethLowpassFloorHz: number,
    warmUpFrames: number, pitchDriftCents: number, periodJitter: number, amplitudeShimmer: number): number;
  vocal_start_score_preparation: Exports["vocal_start_score_prepared"];
  vocal_advance_score_preparation(handle: number, frames: number): number;
  vocal_beat_text(handle: number, bytes: number): number;
  vocal_start_beat(handle: number, bpm: number, swing: number, initialPitchHz: number, noiseScale: number): number;
  vocal_set_beat_tempo(handle: number, bpm: number, swing: number): number;
  vocal_set_beat_playing(handle: number, playing: number): number;
  vocal_beat_bass_key(handle: number, note: number, pressed: number): number;
  vocal_toggle_beat_hum(handle: number, step: number): number;
  vocal_start_live_song(handle: number, vibratoCents: number, female: number, child: number): number;
  vocal_live_song_key(handle: number, note: number, velocity: number): number;
  vocal_stop_live_song(handle: number): number;
  vocal_pcm(handle: number): number;
  vocal_observation(handle: number): number;
  vocal_tract_init(handle: number): number;
  vocal_tract_snapshot(handle: number): number;
  vocal_tract_grid_words(): number;
  vocal_tract_grid_init(handle: number): number;
  vocal_tract_grid_snapshot(handle: number): number;
  vocal_fixed_area_grid(handle: number): number;
  vocal_glottal_trace_init(handle: number): number;
  vocal_radiation_trace_init?(handle: number): number;
  vocal_render(handle: number, frames: number): number;
  vocal_render_traced?(handle: number, frames: number): number;
  vocal_set_gate(handle: number, goal: number): number;
};

export type ScorePreparationSplit = { blockFrames: number; initialBlocks?: readonly number[] };

export class FixedVoiceEngine {
  readonly maxFrames: number;
  readonly tractCellCounts?: [number, number];
  private readonly wasm: Exports;
  private handle: number;
  private pendingPreparation?: {
    handle: number; calls: number; frames: number; blockFrames: number; finalBlockFrames?: number; rendered: number;
  };
  private scorePreparationRemaining = 0;
  private scorePreparationBlockIndex = 0;
  private pcm: Float32Array;
  private last: Float64Array;
  private tract?: Float64Array;
  private tractOffset = 0;
  private tractWords = 0;
  readonly tractGridWords: number;
  private tractGridOffset = 0;
  private tractGrid?: Float64Array;
  private glottalTrace?: Float64Array;
  private glottalOffset = 0;
  private radiationTrace?: Float64Array;
  private radiationOffset = 0;
  private radiationFrames = 0;

  private readonly observationWords: number;
  private readonly fricationRow?: Float64Array;
  private memoryGrowthCount = 0;
  private markCorePhase?: (phase: number, internalOffset: number) => void;

  constructor(
    module: WebAssembly.Module, input: FixedVoiceInput, mode?: VoiceMode, observeSpeech = false, observeGrid = false,
    preparation?: { calls: number; frames: number; blockFrames?: number; finalBlockFrames?: number; distributed?: boolean;
      markWrapper?: (phase: "zero-start" | "zero-end") => void;
      mark: (phase: "prepare-start" | "render-start" | "render-end" | "prepare-end") => void },
    private readonly scorePreparationSplit?: ScorePreparationSplit,
  ) {
    const fields = observationFields(mode);
    if (fields === IPA_FRICATION_OBSERVATION_FIELDS) {
      this.fricationRow = new Float64Array(fields.length);
    }
    this.observationWords = this.fricationRow ? BEAT_OBSERVATION_FIELDS.length + FRICATION_FIELDS.length : fields.length;
    this.wasm = new WebAssembly.Instance(module, {
      chimera_probe: { mark_phase: (phase: number, internalOffset: number) => this.markCorePhase?.(phase, internalOffset) },
    }).exports as unknown as Exports;
    if (this.wasm.vocal_layout_version() !== 1) {
      throw new Error("固定発声WASMのレイアウトに対応していません");
    }
    const { posture: p, voice: v, fixed_airway: a } = input;
    if (input.body !== "male" && (!mode || mode === "manual" || "text" in mode)) {
      throw new Error("体型の指定には調音スコアを使う発声を選んでください");
    }
    if (![a.sample_rate_hz, v.output_sample_rate_hz].every(
      (rate) => Number.isInteger(rate) && rate > 0 && rate <= 0xffffffff,
    ) || a.impulse_volume_cm3 !== 0) {
      throw new Error("固定発声には整数のサンプルレートとゼロのインパルスを指定してください");
    }
    if (p.tongue_body_cm.length !== 2 || p.tongue_tip_cm.length !== 2) {
      throw new Error("舌体と舌先の座標にはそれぞれ2値を指定してください");
    }
    this.handle = 0;
    this.maxFrames = this.wasm.vocal_max_frames();
    if (scorePreparationSplit) {
      const validLength = (frames: number) => Number.isSafeInteger(frames) && frames > 0 && frames <= this.maxFrames;
      if (preparation || !mode || mode === "manual" || !("words" in mode) || !mode.sourcePreparation
        || !validLength(scorePreparationSplit.blockFrames) || scorePreparationSplit.initialBlocks?.some((n) => !validLength(n))) {
        throw new Error("分割する予備描画には音源設定付きのスコアと有効な分割長を指定してください");
      }
    }
    this.tractGridWords = observeGrid ? this.wasm.vocal_tract_grid_words() : 0;
    try {
      const settings = [
        p.jaw_cm, ...p.tongue_body_cm, ...p.tongue_tip_cm, p.tip_curl, p.tongue_root_cm,
        p.lip_aperture_cm, p.lip_protrusion_cm, p.lip_spread, p.labiodental, p.velum_cm2,
        p.larynx_cm, p.epilarynx ?? 0, p.ventricular ?? 0, p.lateral ?? 0, p.dorsum,
        v.pressure_cm_h2o, v.gate, v.f0_hz, v.breathiness, v.tension, v.output_gain,
      ];
      const startHandle = (handle: number) => {
        new Float64Array(this.wasm.memory.buffer, this.wasm.vocal_config(handle), settings.length).set(settings);
        let started: number;
        if (mode === "manual") {
          started = this.wasm.vocal_start_manual(handle);
        } else if (mode && "text" in mode) {
          const { text } = mode;
          const offset = this.wasm.vocal_beat_text(handle, text.length);
          if (!offset) throw new Error("ビートの記譜領域を確保できません");
          new Uint8Array(this.wasm.memory.buffer, offset, text.length).set(text);
          started = this.wasm.vocal_start_beat(handle, mode.bpm, mode.swing, mode.initialPitchHz, mode.noiseScale);
          if (!started) throw new Error("ビートパターンまたは音源設定を読み取れません");
        } else if (mode && "syllableBytes" in mode) {
          const bytes = mode.syllableBytes;
          const offset = this.wasm.vocal_beat_text(handle, bytes.length);
          if (!offset) throw new Error("鍵盤歌唱の音節を準備できません");
          new Uint8Array(this.wasm.memory.buffer, offset, bytes.length).set(bytes);
          started = this.wasm.vocal_start_live_song(handle, mode.vibratoCents, ...bodyAxes(input.body));
        } else if (mode) {
          const offset = this.wasm.vocal_score_buffer(handle, mode.words.length);
          if (!offset) throw new Error("調音スコア領域を確保できません");
          new Float64Array(this.wasm.memory.buffer, offset, mode.words.length).set(mode.words);
          const { turbulence, sourcePreparation } = mode;
          const body = bodyAxes(input.body);
          const pitch = mode.basePitchHz ?? NaN;
          if (sourcePreparation) {
            const { warmUpFrames, pitchDriftCents, periodJitter, amplitudeShimmer } = sourcePreparation;
            if (!Number.isSafeInteger(warmUpFrames) || warmUpFrames < 0 || warmUpFrames > 0xffffffff) {
              throw new Error("予約前の描画フレーム数は0以上の整数で指定してください");
            }
            const start = scorePreparationSplit ? this.wasm.vocal_start_score_preparation
              : this.wasm.vocal_start_score_prepared;
            started = start(handle, turbulence?.scale ?? mode.noiseScale ?? NaN,
              pitch, ...body, turbulence?.glottis_gain_multiplier ?? 1,
              turbulence?.constriction_gain_multiplier ?? 1, turbulence?.teeth_lowpass_floor_hz ?? 0,
              warmUpFrames, pitchDriftCents, periodJitter, amplitudeShimmer);
            if (scorePreparationSplit) this.scorePreparationRemaining = warmUpFrames;
          } else if (turbulence) {
            started = this.wasm.vocal_start_score_with_turbulence(handle, turbulence.scale, pitch, ...body,
              turbulence.glottis_gain_multiplier ?? 1, turbulence.constriction_gain_multiplier ?? 1,
              turbulence.teeth_lowpass_floor_hz ?? 0);
          } else {
            started = this.wasm.vocal_start_score_with_body(handle, mode.noiseScale ?? NaN, pitch, ...body);
          }
        } else {
          started = this.wasm.vocal_start(handle);
        }
        if (!started) throw new Error("発声WASMを指定された設定で初期化できません");
      };
      if (preparation) {
        const { calls, frames, blockFrames = this.maxFrames, finalBlockFrames, mark, markWrapper } = preparation;
        const scoreOrFixed = !mode || (mode !== "manual" && "words" in mode);
        if (!scoreOrFixed || observeGrid
          || !Number.isSafeInteger(frames) || frames < 0 || frames > this.maxFrames
          || (preparation.distributed && frames === 0)
          || !Number.isSafeInteger(blockFrames) || blockFrames < 1 || blockFrames > this.maxFrames
          || (finalBlockFrames !== undefined && (!preparation.distributed || !Number.isSafeInteger(finalBlockFrames)
            || finalBlockFrames < 1 || finalBlockFrames >= frames || (frames - finalBlockFrames) % blockFrames !== 0))) {
          throw new Error("事前描画には固定発声か調音スコアと、範囲内のフレーム数を指定してください");
        }
        if (preparation.distributed) {
          const handle = this.wasm.vocal_new(a.sample_rate_hz, v.output_sample_rate_hz);
          this.pendingPreparation = { handle, calls, frames, blockFrames, finalBlockFrames, rendered: 0 };
          startHandle(handle);
        } else {
          mark("prepare-start");
          this.handle = this.wasm.vocal_new(a.sample_rate_hz, v.output_sample_rate_hz);
          startHandle(this.handle);
          markWrapper?.("zero-start");
          this.warmupRenderWrapper(calls);
          markWrapper?.("zero-end");
          mark("render-start");
          for (let offset = 0; offset < frames; offset += blockFrames) {
            this.renderPreparationBlock(this.handle, Math.min(blockFrames, frames - offset));
          }
          mark("render-end");
          // 同じWASMインスタンスを使い、進んだ状態と出力は本番より先に破棄する。
          this.close();
          mark("prepare-end");
        }
      }
      this.handle = this.wasm.vocal_new(a.sample_rate_hz, v.output_sample_rate_hz);
      startHandle(this.handle);
      if (input.fixed_voice_probe?.radiation_components) {
        this.radiationOffset = this.wasm.vocal_radiation_trace_init?.(this.handle) ?? 0;
        if (!this.radiationOffset) throw new Error("WASMの放射観測領域を確保できません");
      }
      if (observeGrid) {
        this.tractGridOffset = this.wasm.vocal_tract_grid_init(this.handle);
        if (!this.tractGridOffset) throw new Error("声道測定線の観測領域を確保できません");
      }
      if (observeSpeech) {
        this.glottalOffset = this.wasm.vocal_glottal_trace_init(this.handle);
        if (!this.glottalOffset) throw new Error("声門の観測領域を確保できません");
        const offset = this.wasm.vocal_tract_init(this.handle);
        if (!offset) throw new Error("声道断面の観測領域を確保できません");
        const [pharynx, oral] = new Float64Array(this.wasm.memory.buffer, offset, 2);
        this.tractCellCounts = [pharynx, oral];
        this.tractWords = (TRACT_GEOMETRY_WORDS + TRACT_ACOUSTIC_WORDS) * (pharynx + oral);
        this.tractOffset = offset + 2 * Float64Array.BYTES_PER_ELEMENT;
        this.tract = new Float64Array(this.wasm.memory.buffer, this.tractOffset, this.tractWords);
        this.glottalTrace = new Float64Array(
          this.wasm.memory.buffer, this.glottalOffset, this.maxFrames * GLOTTAL_COLUMNS.length,
        );
      }
      // 準備時に線形メモリが伸びる場合があるため、出力のビューは準備後に作る。
      const memory = this.wasm.memory.buffer;
      if (this.radiationOffset) {
        this.radiationTrace = new Float64Array(memory, this.radiationOffset, this.maxFrames * RADIATION_COLUMNS.length);
      }
      if (this.tractGridOffset) {
        this.tractGrid = new Float64Array(memory, this.tractGridOffset, this.tractGridWords);
      }
      this.pcm = new Float32Array(memory, this.wasm.vocal_pcm(this.handle), this.maxFrames);
      this.last = new Float64Array(
        memory, this.wasm.vocal_observation(this.handle), this.observationWords,
      );
    } catch (error) {
      this.close();
      throw error;
    }
  }

  get hasPendingScorePreparation(): boolean {
    return this.scorePreparationRemaining > 0;
  }

  get remainingScorePreparationCallbacks(): number {
    const split = this.scorePreparationSplit;
    if (!split) return 0;
    let remaining = this.scorePreparationRemaining;
    let callbacks = 0;
    const initial = split.initialBlocks;
    if (initial) {
      for (let i = this.scorePreparationBlockIndex; i < initial.length && remaining > 0; i++) {
        remaining = Math.max(0, remaining - initial[i]);
        callbacks++;
      }
    }
    return callbacks + Math.ceil(remaining / split.blockFrames);
  }

  advanceScorePreparation(): number {
    const split = this.scorePreparationSplit;
    if (!this.handle || !this.hasPendingScorePreparation || !split) {
      throw new Error("進める分割予備描画がありません");
    }
    const requested = split.initialBlocks?.[this.scorePreparationBlockIndex] ?? split.blockFrames;
    const frames = Math.min(this.scorePreparationRemaining, requested);
    if (!this.wasm.vocal_advance_score_preparation(this.handle, frames)) {
      throw new Error("発声WASMの分割予備描画に失敗しました");
    }
    this.scorePreparationRemaining -= frames;
    this.scorePreparationBlockIndex++;
    return frames;
  }

  warmupRenderWrapper(calls: number): void {
    this.warmupRenderHandle(this.handle, calls);
  }

  private warmupRenderHandle(handle: number, calls: number): void {
    if (!handle || !Number.isSafeInteger(calls) || calls < 0 || calls > 1000) {
      throw new Error("WASMラッパーを準備する呼び出し回数が範囲外です");
    }
    const render = this.wasm.vocal_render;
    for (let index = 0; index < calls; index++) {
      // 0フレームはABIの入口で終了するので、発声を進めずに同じ関数を呼べる。
      if (render(handle, 0) !== 0) {
        throw new Error("準備中にWASMが0フレームの処理を受理しました");
      }
    }
  }

  get hasPendingRenderPreparation(): boolean {
    return this.pendingPreparation !== undefined;
  }

  advanceRenderPreparation(): number {
    const pending = this.pendingPreparation;
    if (!pending) throw new Error("分割する事前描画がありません");
    if (pending.rendered === 0) this.warmupRenderHandle(pending.handle, pending.calls);
    const remaining = pending.frames - pending.rendered;
    const length = remaining === pending.finalBlockFrames ? remaining : Math.min(remaining, pending.blockFrames);
    this.renderPreparationBlock(pending.handle, length);
    pending.rendered += length;
    if (pending.rendered === pending.frames) {
      this.wasm.vocal_free(pending.handle);
      this.pendingPreparation = undefined;
      // 準備中にメモリが伸びた場合も、本番用ハンドルの観測位置を引き継ぐ。
      if (this.wasm.memory.buffer !== this.pcm.buffer) this.refreshRenderViews();
    }
    return pending.rendered;
  }

  private renderPreparationBlock(handle: number, frames: number): void {
    if (!this.wasm.vocal_render(handle, frames)) throw new Error("WASMの事前描画に失敗しました");
  }

  renderInto(output: Float32Array, mark?: (phase: "wasm-start" | "wasm-end") => void,
    markCopy?: (phase: "pcm-copy-start" | "pcm-copy-end") => void,
    markCore?: (phase: number, internalOffset: number) => void): void {
    if (!this.handle || output.length === 0 || output.length > this.maxFrames) {
      throw new Error("固定発声WASMのハンドルまたはフレーム数が無効です");
    }
    if (this.radiationTrace) this.radiationFrames = 0;
    mark?.("wasm-start");
    let rendered: number;
    if (markCore) {
      const render = this.wasm.vocal_render_traced;
      if (!render) throw new Error("WASMの内部計時には診断用ビルドが必要です");
      this.markCorePhase = markCore;
      try {
        rendered = render(this.handle, output.length);
      } finally {
        this.markCorePhase = undefined;
      }
    } else {
      rendered = this.wasm.vocal_render(this.handle, output.length);
    }
    mark?.("wasm-end");
    if (!rendered) {
      throw new Error("固定発声WASMのレンダーに失敗しました");
    }
    if (this.wasm.memory.buffer !== this.pcm.buffer) {
      if (this.observationWords === OBSERVATION_FIELDS.length) {
        throw new Error("レンダー中にWASMの線形メモリが変更されました");
      }
      this.refreshRenderViews();
      this.memoryGrowthCount++;
    }
    if (this.radiationTrace) this.radiationFrames = output.length;
    markCopy?.("pcm-copy-start");
    for (let i = 0; i < output.length; i++) {
      output[i] = this.pcm[i];
    }
    markCopy?.("pcm-copy-end");
  }

  private refreshRenderViews(): void {
    const memory = this.wasm.memory.buffer;
    this.pcm = new Float32Array(memory, this.wasm.vocal_pcm(this.handle), this.maxFrames);
    this.last = new Float64Array(memory, this.wasm.vocal_observation(this.handle), this.observationWords);
    if (this.tract) this.tract = new Float64Array(memory, this.tractOffset, this.tractWords);
    if (this.tractGrid) this.tractGrid = new Float64Array(memory, this.tractGridOffset, this.tractGridWords);
    if (this.glottalTrace) {
      this.glottalTrace = new Float64Array(memory, this.glottalOffset, this.maxFrames * GLOTTAL_COLUMNS.length);
    }
    if (this.radiationTrace) {
      this.radiationTrace = new Float64Array(memory, this.radiationOffset, this.maxFrames * RADIATION_COLUMNS.length);
    }
  }

  setGate(goal: number): void {
    if (!this.handle || !this.wasm.vocal_set_gate(this.handle, goal)) {
      throw new Error("固定発声WASMの呼気目標を更新できません");
    }
  }

  setManualPitch(f0Hz: number): void {
    if (!this.handle || !this.wasm.vocal_set_manual_pitch(this.handle, f0Hz)) {
      throw new Error("手動発声の基準F0を更新できません");
    }
  }

  applySongKey(key: LiveSongKey): void {
    const velocity = key.type === "note-on" ? key.velocity : 0;
    if (!this.handle || !this.wasm.vocal_live_song_key(this.handle, key.note, velocity)) {
      throw new Error("鍵盤歌唱の入力を音源へ渡せません");
    }
  }

  stopSong(): void {
    if (!this.handle || !this.wasm.vocal_stop_live_song(this.handle)) {
      throw new Error("鍵盤歌唱を停止できません");
    }
  }

  applyBeat(command: BeatCommand): void {
    if (!this.handle) throw new Error("ビートボックスの音源は解放済みです");
    let applied: number;
    switch (command.type) {
      case "tempo":
        applied = this.wasm.vocal_set_beat_tempo(this.handle, command.bpm ?? NaN, command.swing ?? NaN);
        break;
      case "playing":
        applied = this.wasm.vocal_set_beat_playing(this.handle, Number(command.playing));
        break;
      case "bass_key":
        applied = this.wasm.vocal_beat_bass_key(this.handle, command.note, Number(command.pressed));
        break;
      case "toggle_hum":
        applied = this.wasm.vocal_toggle_beat_hum(this.handle, command.step);
        break;
    }
    if (!applied) throw new Error("ビートの操作を適用できません");
  }

  setManualTargets([tongueX, tongueY, lipAperture]: ManualTargets): void {
    if (!this.handle || !this.wasm.vocal_set_manual_targets(this.handle, tongueX, tongueY, lipAperture)) {
      throw new Error("舌体と唇の目標を更新できません");
    }
  }

  switchManualBody(body: VoiceBody): [number, number] {
    const cells = this.handle && this.wasm.vocal_switch_manual_body(this.handle, ...bodyAxes(body));
    if (!cells) throw new Error("手動発声の体型を切り替えられません");
    return [cells >>> 16, cells & 0xffff];
  }

  memoryGrowths(): number {
    return this.memoryGrowthCount;
  }

  readTract(): Readonly<Float64Array> {
    if (!this.handle || !this.tract || !this.wasm.vocal_tract_snapshot(this.handle)) {
      throw new Error("声道の状態を採取できません");
    }
    return this.tract;
  }

  readFixedAreaGrid(): number[][] {
    const offset = this.handle && this.wasm.vocal_fixed_area_grid(this.handle);
    if (!offset) throw new Error("固定姿勢の声道測定線を取得できません");
    const memory = this.wasm.memory.buffer;
    const count = new Float64Array(memory, offset, 1)[0];
    const words = AREA_GRID_COLUMNS.length;
    if (!Number.isSafeInteger(count) || count < 2) throw new Error("声道測定線の行数が不正です");
    const grid = new Float64Array(memory, offset + Float64Array.BYTES_PER_ELEMENT, count * words);
    return Array.from({ length: count }, (_, i) => Array.from(grid.subarray(i * words, (i + 1) * words)));
  }

  copyTractGridTo(target: Float64Array, offset: number): void {
    if (!this.handle || !this.tractGrid || !this.wasm.vocal_tract_grid_snapshot(this.handle)) {
      throw new Error("声道測定線を採取できません");
    }
    target.set(this.tractGrid, offset);
  }

  copyGlottalTraceTo(target: Float64Array, firstFrame: number, frames: number): void {
    const trace = this.glottalTrace;
    if (!trace) throw new Error("声門の観測領域がありません");
    const offset = firstFrame * GLOTTAL_COLUMNS.length;
    for (let i = 0; i < frames * GLOTTAL_COLUMNS.length; i++) {
      target[offset + i] = trace[i];
    }
  }

  // 直近のレンダー分を、出力フレーム順で呼び出し元の配列に写す。
  copyRadiationTraceTo(target: Float64Array, firstFrame: number): void {
    const trace = this.radiationTrace;
    const words = RADIATION_COLUMNS.length;
    const offset = firstFrame * words;
    const length = this.radiationFrames * words;
    if (!this.handle || !trace || length === 0) throw new Error("最新の放射観測がありません");
    if (!Number.isSafeInteger(firstFrame) || firstFrame < 0 || offset + length > target.length) {
      throw new Error("放射観測のコピー先が範囲外です");
    }
    for (let i = 0; i < length; i++) target[offset + i] = trace[i];
  }

  controlOutputFrames(): number {
    return this.wasm.vocal_control_output_frames();
  }

  buffersAreStable(): boolean {
    return Boolean(this.handle)
      && this.wasm.memory.buffer === this.pcm.buffer
      && this.pcm.byteOffset === this.wasm.vocal_pcm(this.handle)
      && this.last.byteOffset === this.wasm.vocal_observation(this.handle);
  }

  // 次のrenderIntoまで有効。呼び出し元で共有メモリを保持する場合は先に値をコピーする。
  readObservation(): Readonly<Float64Array> {
    if (!this.handle) {
      throw new Error("固定発声WASMは解放済みです");
    }
    if (!this.fricationRow) return this.last;
    const prefix = SPEECH_OBSERVATION_FIELDS.length;
    for (let i = 0; i < prefix; i++) this.fricationRow[i] = this.last[i];
    for (let i = 0; i < FRICATION_FIELDS.length; i++) {
      this.fricationRow[prefix + i] = this.last[BEAT_OBSERVATION_FIELDS.length + i];
    }
    return this.fricationRow;
  }

  close(): void {
    if (this.pendingPreparation) {
      this.wasm.vocal_free(this.pendingPreparation.handle);
      this.pendingPreparation = undefined;
    }
    if (this.handle) {
      this.wasm.vocal_free(this.handle);
      this.handle = 0;
    }
  }
}
