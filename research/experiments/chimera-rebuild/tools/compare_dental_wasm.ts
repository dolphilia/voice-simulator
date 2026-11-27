// 固定した発話ケースをWASMの計画・描画へ通し、CLIの全PCMと照合する。
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { gunzipSync } from "node:zlib";
import { FixedVoiceEngine } from "../crates/vocal-wasm/host/fixed-voice.ts";
import { planEnglish, planIpa, planSong } from "../crates/vocal-wasm/host/planning.ts";

const [wasmPath, artifacts, casePath] = process.argv.slice(2);
const module = new WebAssembly.Module(readFileSync(wasmPath));
const dictionary = gunzipSync(readFileSync(new URL("../data/cmudict.txt.gz", import.meta.url)));
const { contexts, noise_scales }: { contexts: string[]; noise_scales?: Record<string, number | null> } =
  JSON.parse(readFileSync(casePath, "utf8"));
const output: Record<string, unknown> = {};

function readFloatSamples(path: string) {
  const file = readFileSync(path);
  if (file.toString("ascii", 0, 4) !== "RIFF" || file.toString("ascii", 8, 12) !== "WAVE") {
    throw new Error(`WAVヘッダーがありません (${path})`);
  }
  let format: Buffer | undefined;
  let samples: Buffer | undefined;
  for (let start = 12; start + 8 <= file.length;) {
    const tag = file.toString("ascii", start, start + 4);
    const length = file.readUInt32LE(start + 4);
    const begin = start + 8;
    const end = begin + length;
    if (end > file.length) throw new Error(`WAVのチャンクが途中で終わっています (${path})`);
    if (tag === "fmt ") format = file.subarray(begin, end);
    if (tag === "data") samples = file.subarray(begin, end);
    start = end + (length % 2);
  }
  if (!format || format.length < 16 || format.readUInt16LE(0) !== 3 ||
      format.readUInt16LE(2) !== 1 || format.readUInt32LE(4) !== 48_000 ||
      format.readUInt16LE(14) !== 32 || !samples || samples.length % 4 !== 0) {
    throw new Error(`CLIのモノラルfloat32 WAV形式が条件外です (${path})`);
  }
  return samples;
}

for (const id of contexts) {
  const folder = join(artifacts, id);
  const fixture = JSON.parse(readFileSync(join(folder, "case.json"), "utf8"));
  const source = fixture.song_voice ?? fixture.speech_voice;
  const reference = readFloatSamples(join(folder, "pcm-128.wav"));
  const { f0_hz } = source.voice;
  const plan = fixture.song_voice
    ? planSong(module, { ...source.score, vibrato_cents: source.vibrato_cents }, dictionary, source.body)
    : source.language === "english"
      ? planEnglish(module, source.input.text, dictionary, 0.05, source.input.rate, f0_hz, source.body)
      : planIpa(module, source.input.text, 0.05, source.input.rate, f0_hz, source.body);
  const end = "song" in plan ? plan.song.plan.render_end_seconds : plan.speech.render_end_seconds;
  const frames = Math.round(end * source.voice.output_sample_rate_hz);
  const expectedNoise = noise_scales && id in noise_scales ? noise_scales[id] : 1;
  if (frames * 4 !== reference.length || plan.score.noiseScale !== expectedNoise) {
    throw new Error(`WASMの出力フレーム数または乱流設定が条件外です (${id})`);
  }
  const input = { ...source,
    voice: { ...source.voice, f0_hz: plan.initialPitchHz },
    fixed_airway: { sample_rate_hz: source.internal_sample_rate_hz, sample_count: frames * 2, impulse_volume_cm3: 0 },
  };
  const engine = new FixedVoiceEngine(module, input, plan.score);
  let firstBitDifference: number | null = null;
  let maximumAbsoluteDifference = 0;
  try {
    for (let first = 0; first < frames; first += 128) {
      const samples = new Float32Array(Math.min(frames - first, 128));
      const bits = new Uint32Array(samples.buffer);
      engine.renderInto(samples);
      for (let i = 0; i < samples.length; i++) {
        const frame = first + i;
        const offset = frame * 4;
        maximumAbsoluteDifference = Math.max(maximumAbsoluteDifference, Math.abs(reference.readFloatLE(offset) - samples[i]));
        if (firstBitDifference === null && reference.readUInt32LE(offset) !== bits[i]) firstBitDifference = frame;
      }
    }
  } finally {
    engine.close();
  }
  output[id] = { frames, firstBitDifference, maximumAbsoluteDifference };
}
console.log(JSON.stringify(output, null, 2));
