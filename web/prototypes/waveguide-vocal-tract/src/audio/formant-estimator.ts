// フォルマント周波数推定
// 声道フィルター（反射係数）にインパルスを入力し、
// ソフトウェア波動管で伝搬させた応答に FFT を適用してスペクトルピークを検出する。
// AudioWorklet ではなくメインスレッドで実行し、断面積変化時のみ再計算する。

import { computeReflectionCoefficients, computeLossCoefficients } from "./tube-model";

const FFT_SIZE = 2048;
// 内部サンプルレート（2x オーバーサンプリングに合わせる）
const INTERNAL_SR = 88200;

// ─── Cooley–Tukey 基数2 FFT（複素数インプレース） ───────────────────────────

function fft(re: Float64Array, im: Float64Array): void {
  const N = re.length;
  // ビット逆順並べ替え
  for (let i = 1, j = 0; i < N; i++) {
    let bit = N >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) {
      [re[i], re[j]] = [re[j], re[i]];
      [im[i], im[j]] = [im[j], im[i]];
    }
  }
  // バタフライ演算
  for (let len = 2; len <= N; len <<= 1) {
    const ang = (-2 * Math.PI) / len;
    const wRe = Math.cos(ang);
    const wIm = Math.sin(ang);
    for (let i = 0; i < N; i += len) {
      let curRe = 1, curIm = 0;
      for (let j = 0; j < len / 2; j++) {
        const uRe = re[i + j];
        const uIm = im[i + j];
        const vRe = re[i + j + len / 2] * curRe - im[i + j + len / 2] * curIm;
        const vIm = re[i + j + len / 2] * curIm + im[i + j + len / 2] * curRe;
        re[i + j] = uRe + vRe;
        im[i + j] = uIm + vIm;
        re[i + j + len / 2] = uRe - vRe;
        im[i + j + len / 2] = uIm - vIm;
        const nextRe = curRe * wRe - curIm * wIm;
        curIm = curRe * wIm + curIm * wRe;
        curRe = nextRe;
      }
    }
  }
}

// ─── ソフトウェア波動管シミュレーション ─────────────────────────────────────

function simulateImpulseResponse(
  k: Float32Array,
  loss: Float32Array,
  numSamples: number
): Float64Array {
  const N = k.length;
  const right = new Float64Array(N);
  const left = new Float64Array(N);
  const rPrev = new Float64Array(N);
  const lPrev = new Float64Array(N);
  const output = new Float64Array(numSamples);

  for (let s = 0; s < numSamples; s++) {
    // 現在の状態を保存（ダブルバッファ）
    rPrev.set(right);
    lPrev.set(left);

    // グロッタル境界: s=0 のみインパルス入力
    right[0] = (s === 0 ? 1.0 : 0.0) + 0.95 * lPrev[0];

    // セクション間散乱（旧状態を参照）
    for (let i = 0; i < N - 1; i++) {
      const ki = k[i];
      const lo = loss[i];
      right[i + 1] = ((1 + ki) * rPrev[i] - ki * lPrev[i + 1]) * lo;
      left[i] = ((1 - ki) * lPrev[i + 1] + ki * rPrev[i]) * lo;
    }

    // 口端反射
    left[N - 1] = k[N - 1] * rPrev[N - 1] * loss[N - 1];

    // 出力: 口端の全圧力
    output[s] = rPrev[N - 1] + lPrev[N - 1];
  }

  return output;
}

// ─── ピーク検出 ──────────────────────────────────────────────────────────────

/** magnitude[bin] から f0_hz 〜 fMax_hz の範囲でピークを検出し、上位 count 個を返す */
function findPeaks(
  magnitude: Float64Array,
  binSize: number,
  minHz: number,
  maxHz: number,
  count: number
): number[] {
  const minBin = Math.ceil(minHz / binSize);
  const maxBin = Math.min(Math.floor(maxHz / binSize), magnitude.length - 2);

  // (prominence, freq) のリスト
  const candidates: { freq: number; prominence: number }[] = [];

  for (let b = minBin + 1; b < maxBin; b++) {
    if (magnitude[b] > magnitude[b - 1] && magnitude[b] > magnitude[b + 1]) {
      // 放物線補間でピーク周波数を精密化
      const alpha = magnitude[b - 1];
      const beta = magnitude[b];
      const gamma = magnitude[b + 1];
      const offset = (0.5 * (alpha - gamma)) / (alpha - 2 * beta + gamma + 1e-30);
      const freqHz = (b + offset) * binSize;

      // Prominence: ピーク高さ - 両側 500 Hz 以内の最小値
      const win = Math.round(500 / binSize);
      let minVal = beta;
      for (let d = 1; d <= win; d++) {
        if (b - d >= 0) minVal = Math.min(minVal, magnitude[b - d]);
        if (b + d < magnitude.length) minVal = Math.min(minVal, magnitude[b + d]);
      }
      const prominence = beta - minVal;

      candidates.push({ freq: freqHz, prominence });
    }
  }

  // prominence 降順ソート → 上位 count 個を周波数順に返す
  candidates.sort((a, b) => b.prominence - a.prominence);
  const top = candidates.slice(0, count).map(c => c.freq);
  top.sort((a, b) => a - b);
  return top;
}

// ─── 公開 API ────────────────────────────────────────────────────────────────

/**
 * 断面積配列からフォルマント周波数（F1〜F3）を推定する
 * @returns 周波数昇順の配列（1〜3 要素）
 */
export function estimateFormants(areas: number[]): number[] {
  const k = computeReflectionCoefficients(areas);
  const loss = computeLossCoefficients(areas);

  // インパルス応答取得
  const ir = simulateImpulseResponse(k, loss, FFT_SIZE);

  // Hann 窓適用
  const re = new Float64Array(FFT_SIZE);
  const im = new Float64Array(FFT_SIZE);
  for (let i = 0; i < FFT_SIZE; i++) {
    const w = 0.5 * (1 - Math.cos((2 * Math.PI * i) / (FFT_SIZE - 1)));
    re[i] = ir[i] * w;
  }

  // FFT
  fft(re, im);

  // 振幅スペクトル（対数スケール）
  const mag = new Float64Array(FFT_SIZE / 2);
  for (let i = 0; i < FFT_SIZE / 2; i++) {
    mag[i] = Math.log(Math.sqrt(re[i] * re[i] + im[i] * im[i]) + 1e-12);
  }

  // 周波数分解能: INTERNAL_SR / FFT_SIZE
  const binSize = INTERNAL_SR / FFT_SIZE;

  // F1〜F3 を検出（200 Hz 〜 4000 Hz、上位 3 ピーク）
  const formants = findPeaks(mag, binSize, 200, 4000, 3);

  // 3 個未満の場合は 1/4 波長近似で補完
  const c = 35000;
  const L = 17.0;
  while (formants.length < 3) {
    const m = formants.length + 1;
    formants.push(((2 * m - 1) * c) / (4 * L));
  }

  return formants;
}
