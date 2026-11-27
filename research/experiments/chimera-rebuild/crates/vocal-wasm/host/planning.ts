// ページ側で計画を実行し、Workletで使うスコアを線形メモリから取り出す。
import { bodyAxes, type VoiceBody, type VoiceScore } from "./fixed-voice";

type Planner = {
  memory: WebAssembly.Memory;
  vocal_plan_input(bytes: number): number;
  vocal_ipa_plan_with_body(start: number, rate: number, f0: number, female: number, child: number): number;
  vocal_plan_dictionary(bytes: number): number;
  vocal_english_plan_with_body(start: number, rate: number, f0: number, female: number, child: number): number;
  vocal_song_plan_with_body(female: number, child: number): number;
  vocal_lyric_syllables(): number;
  vocal_plan_report(): number;
  vocal_plan_score(): number;
  vocal_plan_score_words(): number;
};

export type TimedPhone = { segment: { ipa: string }; start_seconds: number; end_seconds: number };

export type IpaSpeech = {
  utterances: { segments: TimedPhone[] }[];
  render_end_seconds: number;
  rate: number;
};

export type EnglishSpeech = {
  phrases: { timing: { segments: TimedPhone[] } }[];
  shown: string;
  render_end_seconds: number;
};

type IpaPlan = {
  speech: IpaSpeech;
  noise_scale: number | null;
  base_pitch_hz: number;
  initial_pitch_hz: number;
  glide_from_initial: boolean;
};

type PitchedPlan = {
  noise_scale: number | null;
  base_pitch_hz: number;
  initial_pitch_hz: number;
};

type EnglishPlan = PitchedPlan & { speech: EnglishSpeech };
type SongPlan = PitchedPlan & {
  song: {
    id: string;
    syllables: unknown[];
    plan: { render_end_seconds: number; notes: { beat_seconds: number; note: { midi: number } }[] };
  };
};
type PlannedGesture = { label?: string; targets: Partial<Record<string, number>> };

export type LyricSyllable = { text: string; melisma?: boolean; wordEnd?: boolean };

export type SongInput = ({
  lyrics: string;
  syllables?: never;
} | {
  lyrics?: never;
  syllables: unknown[];
}) & {
  id: string;
  notes: { midi: number; beats: number }[];
  bpm: number;
  start_seconds: number;
  vibrato_cents: number;
};

function planner(module: WebAssembly.Module): Planner {
  return new WebAssembly.Instance(module, {
    chimera_probe: { mark_phase: () => {} },
  }).exports as unknown as Planner;
}

function writeInput(wasm: Planner, text: string): void {
  const bytes = new TextEncoder().encode(text);
  const offset = wasm.vocal_plan_input(bytes.length);
  if (!offset) throw new Error("計画の入力が空か、バイト数が上限を超えています");
  new Uint8Array(wasm.memory.buffer, offset, bytes.length).set(bytes);
}

function writeDictionary(wasm: Planner, dictionary: Uint8Array): void {
  const offset = wasm.vocal_plan_dictionary(dictionary.length);
  if (!offset) throw new Error("英語の発音辞書の長さが範囲外です");
  new Uint8Array(wasm.memory.buffer, offset, dictionary.length).set(dictionary);
}

function readResult<T>(wasm: Planner, length: number) {
  const report = JSON.parse(new TextDecoder().decode(
    new Uint8Array(wasm.memory.buffer, wasm.vocal_plan_report(), length),
  )) as { plan: T; gestures: PlannedGesture[] } | { error: string };
  if ("error" in report) throw new Error(report.error);
  const words = new Float64Array(wasm.memory.buffer, wasm.vocal_plan_score(), wasm.vocal_plan_score_words()).slice();
  return { ...report, words };
}

export function planIpa(module: WebAssembly.Module, text: string, start: number, rate: number,
  f0: number | undefined, body: VoiceBody = "male") {
  const wasm = planner(module);
  writeInput(wasm, text);
  const length = wasm.vocal_ipa_plan_with_body(start, rate, f0 ?? NaN, ...bodyAxes(body));
  const { plan, gestures, words } = readResult<IpaPlan>(wasm, length);
  const score: VoiceScore = {
    words, noiseScale: plan.noise_scale, basePitchHz: plan.glide_from_initial ? plan.base_pitch_hz : undefined,
    observeIpa: plan.noise_scale === null ? "speech" : "frication",
  };
  return { speech: plan.speech, gestures, score, basePitchHz: plan.base_pitch_hz, initialPitchHz: plan.initial_pitch_hz };
}

export function planSong(module: WebAssembly.Module, input: SongInput, dictionary: Uint8Array | undefined,
  body: VoiceBody = "male", mark?: (phase: string) => void) {
  const wasm = planner(module);
  mark?.("planner_instance");
  writeInput(wasm, JSON.stringify(input));
  if (dictionary) writeDictionary(wasm, dictionary);
  mark?.("planner_input");
  const length = wasm.vocal_song_plan_with_body(...bodyAxes(body));
  mark?.("planner_wasm");
  const { plan, gestures, words } = readResult<SongPlan>(wasm, length);
  mark?.("planner_result");
  const score: VoiceScore = {
    words, noiseScale: plan.noise_scale, basePitchHz: plan.base_pitch_hz,
    observeNasal: gestures.some((gesture) => gesture.targets.velum_cm2 !== undefined),
    observeTongue: gestures.some((gesture) => gesture.label === "j" || gesture.label === "ɰ"),
  };
  return { song: plan.song, gestures, score, initialPitchHz: plan.initial_pitch_hz };
}

export function lyricSyllables(module: WebAssembly.Module, text: string, dictionary: Uint8Array): LyricSyllable[] {
  if (!text) return [];
  const wasm = planner(module);
  writeInput(wasm, text);
  writeDictionary(wasm, dictionary);
  return readResult<LyricSyllable[]>(wasm, wasm.vocal_lyric_syllables()).plan;
}

const englishPlanners = new WeakMap<WebAssembly.Module, Planner>();

export function planEnglish(
  module: WebAssembly.Module, text: string, dictionary: Uint8Array, start: number, rate: number,
  f0: number | undefined, body: VoiceBody = "male",
) {
  let wasm = englishPlanners.get(module);
  if (!wasm) {
    wasm = planner(module);
    englishPlanners.set(module, wasm);
  }
  writeInput(wasm, text);
  writeDictionary(wasm, dictionary);
  const length = wasm.vocal_english_plan_with_body(start, rate, f0 ?? NaN, ...bodyAxes(body));
  const { plan, gestures, words } = readResult<EnglishPlan>(wasm, length);
  const score: VoiceScore = { words, noiseScale: plan.noise_scale, basePitchHz: plan.base_pitch_hz, observeNasal: true };
  return { speech: plan.speech, gestures, score, initialPitchHz: plan.initial_pitch_hz };
}
