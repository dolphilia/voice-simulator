import experiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-pcm-spectrum.json";
import { fft } from "../../../shared/audio/fft";

const { fft_size: size, window: windowName } = experiment.measurement;
const blackman = Float64Array.from({ length: size }, (_, i) => {
  const phase = 2 * Math.PI * i / size;
  return 0.42 - 0.5 * Math.cos(phase) + 0.08 * Math.cos(2 * phase);
});
const windowSum = blackman.reduce((sum, weight) => sum + weight, 0);

export function pcmSpectrum(pcm: Float32Array, sampleRate: number, frame: number) {
  const firstFrame = frame - size / 2;
  const sourceFirstFrame = Math.max(0, firstFrame);
  const sourceEndFrame = Math.min(pcm.length, firstFrame + size);
  const real = new Float64Array(size);
  const imaginary = new Float64Array(size);
  for (let i = sourceFirstFrame; i < sourceEndFrame; i++) {
    const offset = i - firstFrame;
    real[offset] = pcm[i] * blackman[offset];
  }
  fft(real, imaginary);
  const amplitudes = Array.from({ length: size / 2 + 1 }, (_, bin) => {
    // 実信号の正負の周波数をまとめる。DCとナイキストは片側にしかない。
    const factor = bin === 0 || bin === size / 2 ? 1 : 2;
    return factor * Math.hypot(real[bin], imaginary[bin]) / windowSum;
  });
  return {
    source: "rendered-pcm",
    frame, sampleRate, fftSize: size, window: windowName,
    firstFrame, sourceFirstFrame, sourceEndFrame,
    normalization: "one-sided-peak-full-scale",
    amplitudes,
  };
}
