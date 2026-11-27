// 拍区間と音節の対応は固定上流の src/show/words.ts（Jameson Hodge、MIT）を参照。
import type { LyricSyllable } from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/planning";

type Melody = { bpm: number; t0?: number; notes: [number, number][] } & (
  { syllables: LyricSyllable[] } | { syllables?: undefined; lyrics: string });
export type Word = { key: number; text: string };
export type DuetWords = { start: number; end: number; word: Word }[];

export function readDuetMelody(value: unknown): Melody {
  if (typeof value !== "object" || value === null) throw new Error("旋律をJSONのオブジェクトで指定してください");
  const { bpm, t0, notes, lyrics, syllables } = value as Partial<Melody & { lyrics: string }>;
  if (typeof bpm !== "number" || !Number.isFinite(bpm) || bpm <= 0
      || (t0 !== undefined && (typeof t0 !== "number" || !Number.isFinite(t0)))
      || !Array.isArray(notes) || !notes.every((note) => Array.isArray(note) && note.length === 2
        && note.every((value) => Number.isFinite(value)) && note[1] > 0)) {
    throw new Error("旋律のテンポ・開始時刻・音符が不正です");
  }
  if (syllables !== undefined) {
    if (!Array.isArray(syllables) || !syllables.every((syllable) => syllable && typeof syllable.text === "string"
      && (syllable.melisma === undefined || typeof syllable.melisma === "boolean")
      && (syllable.wordEnd === undefined || typeof syllable.wordEnd === "boolean"))) {
      throw new Error("旋律の音節が不正です");
    }
    return { bpm, t0, notes, syllables };
  }
  if (typeof lyrics !== "string") throw new Error("旋律の歌詞または音節がありません");
  return { bpm, t0, notes, lyrics };
}

function alignBoundary(seconds: number, sampleRate: number) {
  const sample = Math.round(seconds * sampleRate);
  if (!Number.isSafeInteger(sample)) return seconds;
  const aligned = sample / sampleRate;
  const roundoff = Number.EPSILON * Math.max(1, Math.abs(seconds));
  return Math.abs(aligned - seconds) <= roundoff ? aligned : seconds;
}

export function buildDuetWords(melody: Melody, syllables: LyricSyllable[], sampleRate: number,
  spell: Record<string, string> = {}): DuetWords {
  const noteCount = melody.notes.filter(([midi]) => midi > 0).length;
  if (syllables.length !== noteCount) throw new Error(`音節数 ${syllables.length} と発音する音符数 ${noteCount} が一致しません`);
  const spelling = new Map(Object.entries(spell).map(([from, to]) => [from.toLowerCase(), to]));
  const words: DuetWords = [];
  const beat = 60 / melody.bpm;
  let time = melody.t0 ?? 0.3;
  for (const [midi, beats] of melody.notes) {
    const end = time + beats * beat;
    if (!Number.isFinite(end) || end <= time) throw new Error("旋律の拍区間が範囲外です");
    if (midi > 0) {
      const index = words.length;
      const syllable = syllables[index];
      const previous = words.at(-1);
      const word = syllable.melisma && previous ? previous.word : {
        key: index,
        text: (spelling.get(syllable.text.toLowerCase()) ?? syllable.text) + (syllable.wordEnd ? "" : "-"),
      };
      // 丸め誤差でサンプル境界をまたぐ場合だけ表示の境界を揃える。
      const start = alignBoundary(time, sampleRate);
      const finish = alignBoundary(end, sampleRate);
      words.push(start < finish ? { start, end: finish, word } : { start: time, end, word });
    }
    time = end;
  }
  return words;
}

export function duetWordAt(words: DuetWords, time: number): Word | null {
  let low = 0;
  let high = words.length;
  while (low < high) {
    const midpoint = low + Math.floor((high - low) / 2);
    if (words[midpoint].start <= time) low = midpoint + 1;
    else high = midpoint;
  }
  const note = words[low - 1];
  return note && time < note.end ? note.word : null;
}
