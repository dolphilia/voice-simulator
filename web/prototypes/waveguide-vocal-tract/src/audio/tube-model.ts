// Kelly–Lochbaum 波動管モデルの静的計算ユーティリティ
// AudioWorklet への送信データを生成する。
// 実際の波動伝搬（時間領域サンプル更新）は waveguide-processor.js 内で行う。

import { MIN_AREA } from "./vowel-presets";

/**
 * 断面積配列から Kelly–Lochbaum 反射係数列を算出
 * k[i] = (A[i+1] - A[i]) / (A[i+1] + A[i])   境界 i と i+1 の間
 * k[N-1] = -0.85  口端開放反射
 */
export function computeReflectionCoefficients(areas: number[]): Float32Array {
  const N = areas.length;
  const k = new Float32Array(N);
  for (let i = 0; i < N - 1; i++) {
    const a0 = Math.max(MIN_AREA, areas[i]);
    const a1 = Math.max(MIN_AREA, areas[i + 1]);
    k[i] = (a1 - a0) / (a1 + a0);
  }
  k[N - 1] = -0.85; // 口端開放反射係数
  return k;
}

/**
 * 断面積配列からセクションごとの損失係数を算出
 * 粘性・熱損失は断面積が小さいほど大きい（表面積/体積比が高い）
 *
 * loss[i] = exp(-alpha / sqrt(A[i]))
 * alpha は実験的に調整（声道での典型的な損失量に合わせる）
 */
export function computeLossCoefficients(areas: number[]): Float32Array {
  const N = areas.length;
  const loss = new Float32Array(N);
  const ALPHA_BASE = 0.0008; // 調整済み損失係数（小さすぎるとQ値が高すぎる）
  for (let i = 0; i < N; i++) {
    const a = Math.max(MIN_AREA, areas[i]);
    loss[i] = Math.exp(-ALPHA_BASE / Math.sqrt(a));
  }
  return loss;
}
