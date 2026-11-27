// 既知の振幅を持つ信号に、画面と同じスペクトル計算を適用する。
import { writeFileSync } from "node:fs";
import experiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-pcm-spectrum.json";
import { pcmSpectrum } from "../src/pcm-spectrum";

const { fft_size: size, analytic } = experiment.measurement;
const { tone_bin: toneBin, tone_peak: tonePeak, dc_peak: dcPeak, nyquist_peak: nyquistPeak } = analytic;
const run = (signal: (i: number) => number) =>
  pcmSpectrum(Float32Array.from({ length: size }, (_, i) => signal(i)), 48000, size / 2).amplitudes;

const tone = run((i) => tonePeak * Math.sin(2 * Math.PI * toneBin * i / size));
const dc = run(() => dcPeak);
const nyquist = run((i) => i % 2 === 0 ? nyquistPeak : -nyquistPeak);
const silence = run(() => 0);
writeFileSync(process.argv[2], JSON.stringify({
  tone_bin: tone.indexOf(Math.max(...tone)), tone_peak: tone[toneBin],
  dc_peak: dc[0], nyquist_peak: nyquist[size / 2], silence_peak: Math.max(...silence),
}) + "\n");
