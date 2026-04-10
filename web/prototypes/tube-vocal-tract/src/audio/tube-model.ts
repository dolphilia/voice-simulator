// Kelly–Lochbaum 多管チューブモデル
// 断面積配列から反射係数を算出し、デジタル波動管フィルターのパラメータを提供する

import { NUM_SECTIONS, MIN_AREA } from "./vowel-presets";

export type TubeModelParams = {
  reflectionCoefficients: Float32Array; // 長さ N+1（セクション境界の数）
  areas: Float32Array;
};

/**
 * 断面積配列から Kelly–Lochbaum 反射係数を算出する
 * k[i] = (A[i+1] - A[i]) / (A[i+1] + A[i])
 * 両端（グロッタル側・口側）にも境界反射を追加する
 */
export function computeReflectionCoefficients(areas: number[]): Float32Array {
  const n = areas.length;
  // セクション間境界: n-1 個 + 口端: 1 個 = n 個
  const k = new Float32Array(n);

  for (let i = 0; i < n - 1; i++) {
    const a0 = Math.max(MIN_AREA, areas[i]);
    const a1 = Math.max(MIN_AREA, areas[i + 1]);
    k[i] = (a1 - a0) / (a1 + a0);
  }

  // 口端（開放端）: 反射係数 = -1 に近い値（放射モデル簡易版）
  k[n - 1] = -0.85;

  return k;
}

/**
 * フォルマント周波数を推定する（DFT によるスペクトルピーク検出）
 * AudioWorklet 側でも使えるよう純粋な計算のみ
 */
export function estimateFormants(
  areas: number[],
  sampleRate: number,
  tractLengthCm = 17.0
): number[] {
  const n = areas.length;
  const k = computeReflectionCoefficients(areas);

  // インパルス応答をシミュレートして伝達関数を得る
  // 管一本あたりの遅延サンプル数
  const speedOfSound = 35000; // cm/s
  const sectionLengthCm = tractLengthCm / n;
  const delaySamples = (sectionLengthCm / speedOfSound) * sampleRate;

  // 簡易的にフォルマントを 1/4 波長共鳴式で推定
  // 均一管の場合: F_m = (2m-1) * c / (4L)
  // 断面積の重み付き有効長で補正
  const formants: number[] = [];
  const c = speedOfSound; // cm/s
  const L = tractLengthCm; // cm

  for (let m = 1; m <= 3; m++) {
    let freq = ((2 * m - 1) * c) / (4 * L);

    // 断面積の変化による補正（細いほどフォルマントが下がる傾向）
    const meanArea = areas.reduce((s, a) => s + a, 0) / areas.length;
    const refArea = 5.0; // 参照断面積 cm²
    const correction = 1.0 + 0.1 * Math.log(Math.max(0.1, meanArea / refArea));

    // 反射係数の影響（簡易摂動補正）
    let perturbation = 0;
    for (let i = 0; i < k.length - 1; i++) {
      const positionRatio = i / (k.length - 1);
      // cos で位置依存の摂動
      perturbation += k[i] * Math.cos(m * Math.PI * positionRatio);
    }
    perturbation = (perturbation / k.length) * 200;

    formants.push(Math.max(100, freq * correction + perturbation));
  }

  // delaySamples は現時点では使用しないが将来の拡張のため残す
  void delaySamples;

  return formants;
}

/**
 * TubeModel: 断面積配列を管理し、反射係数とパラメータを提供する
 */
export class TubeModel {
  private areas: number[];

  constructor(initialAreas: number[]) {
    this.areas = [...initialAreas];
  }

  setAreas(areas: number[]): void {
    this.areas = [...areas];
  }

  getAreas(): number[] {
    return [...this.areas];
  }

  getParams(sampleRate: number): TubeModelParams {
    const k = computeReflectionCoefficients(this.areas);
    const areasF32 = new Float32Array(this.areas);
    return { reflectionCoefficients: k, areas: areasF32 };
  }

  getFormants(sampleRate: number): number[] {
    return estimateFormants(this.areas, sampleRate);
  }

  get numSections(): number {
    return NUM_SECTIONS;
  }
}
