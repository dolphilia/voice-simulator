import type { SpeechVoiceInput } from "./render-fixed-voice";

function object(value: unknown, label: string): Record<string, unknown> {
  if (value == null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label}をオブジェクトで指定してください`);
  }
  return value as Record<string, unknown>;
}

function number(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`${label}を有限の数値で指定してください`);
  }
  return value;
}

function optional(value: unknown, label: string): number | undefined {
  return value == null ? undefined : number(value, label);
}

function point(value: unknown, label: string): [number, number] {
  if (!Array.isArray(value) || value.length !== 2) {
    throw new Error(`${label}の2座標を指定してください`);
  }
  return [number(value[0], label), number(value[1], label)];
}

function body(value: unknown): SpeechVoiceInput["body"] {
  if (value == null || value === "male") return "male";
  if (value === "female" || value === "child") return value;
  const mix = object(value, "体型");
  return { female: optional(mix.female, "女性比") ?? 0, child: optional(mix.child, "子ども比") ?? 0 };
}

export function readEnglishSpeechCase(value: unknown) {
  const root = object(value, "英語発話ケース");
  const spec = object(root.speech_voice, "speech_voice");
  const input = object(spec.input, "発話入力");
  const posture = object(spec.posture, "初期姿勢");
  const voice = object(spec.voice, "音源と出力");
  if (spec.language !== "english" || typeof input.text !== "string" || !input.text.trim()) {
    throw new Error("英語の本文を含む発話ケースを選んでください");
  }
  if (spec.lateral_opening_scale != null || input.segments != null
    || (input.additional_gestures != null
      && (!Array.isArray(input.additional_gestures) || input.additional_gestures.length > 0))) {
    throw new Error("この発話ケースにはブラウザで再演できない調音設定があります");
  }
  const variation = spec.source_variation == null ? undefined : object(spec.source_variation, "音源の揺らぎ");
  const turbulence = spec.turbulence == null ? undefined : object(spec.turbulence, "乱流");
  const config: SpeechVoiceInput = {
    body: body(spec.body),
    posture: {
      jaw_cm: number(posture.jaw_cm, "顎"),
      tongue_body_cm: point(posture.tongue_body_cm, "舌体"),
      tongue_tip_cm: point(posture.tongue_tip_cm, "舌先"),
      tongue_root_cm: number(posture.tongue_root_cm, "舌根"),
      tip_curl: number(posture.tip_curl, "舌先の反り"),
      dorsum: number(posture.dorsum, "舌背"),
      lip_aperture_cm: number(posture.lip_aperture_cm, "唇の高さ"),
      lip_protrusion_cm: number(posture.lip_protrusion_cm, "唇の突き出し"),
      lip_spread: number(posture.lip_spread, "唇の広がり"),
      labiodental: number(posture.labiodental, "唇歯の開き"),
      velum_cm2: number(posture.velum_cm2, "鼻腔への断面"),
      larynx_cm: number(posture.larynx_cm, "喉頭"),
      lateral: optional(posture.lateral, "側面開口"),
      epilarynx: optional(posture.epilarynx, "喉頭蓋上部"),
      ventricular: optional(posture.ventricular, "仮声帯"),
    },
    fixed_airway: {
      sample_rate_hz: number(spec.internal_sample_rate_hz, "内部サンプルレート"),
      impulse_volume_cm3: 0,
      sample_count: 0,
    },
    voice: {
      pressure_cm_h2o: number(voice.pressure_cm_h2o, "肺圧"),
      gate: number(voice.gate, "呼気ゲート"),
      f0_hz: optional(voice.f0_hz, "基準F0"),
      breathiness: number(voice.breathiness, "息漏れ"),
      tension: number(voice.tension, "声帯の張力"),
      output_gain: number(voice.output_gain, "出力ゲイン"),
      output_sample_rate_hz: number(voice.output_sample_rate_hz, "出力サンプルレート"),
    },
    source_variation: variation && {
      pitch_drift_cents: optional(variation.pitch_drift_cents, "ドリフト"),
      period_jitter: optional(variation.period_jitter, "周期ジッター"),
      amplitude_shimmer: optional(variation.amplitude_shimmer, "振幅シマー"),
    },
    turbulence: turbulence && {
      scale: number(turbulence.scale, "乱流係数"),
      glottis_gain_multiplier: optional(turbulence.glottis_gain_multiplier, "声門乱流のゲイン"),
      constriction_gain_multiplier: optional(turbulence.constriction_gain_multiplier, "狭窄乱流のゲイン"),
      teeth_lowpass_floor_hz: optional(turbulence.teeth_lowpass_floor_hz, "歯の乱流フィルタ下限"),
    },
  };
  return { config, text: input.text, rate: optional(input.rate, "話速") ?? 1, start: optional(input.start_seconds, "発話の開始時刻"),
    inputId: typeof input.id === "string" ? input.id : undefined,
    caseId: typeof root.id === "string" ? root.id : typeof input.id === "string" ? input.id : undefined };
}
