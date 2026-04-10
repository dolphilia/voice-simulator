// 声道断面積プロファイル
// 16 個の制御点を定義し、NUM_SECTIONS=44 に線形補間して使用する。
// 制御点は Maeda (1979)、Chiba & Kajiyama (1942)、splab.net の記述をもとに設定。
// 単位: cm²、グロッタル側（咽頭後壁）→ 口側（口唇）の順

export type VowelId = "a" | "i" | "u" | "e" | "o";

// 2x オーバーサンプリング時に 1 サンプル/セクション となるよう
// NUM_SECTIONS = round(17cm * 2 * 44100Hz / 35000 cm/s) ≈ 43 → 44
export const NUM_SECTIONS = 44;

export const MIN_AREA = 0.2;
export const MAX_AREA = 12.0;

// 16 制御点
// 出典: splab.net 「声道モデル実物展示」3.4.3 日本語5母音
//   Chiba & Kajiyama (1942) の X 線計測をもとにした 16 枚プレートモデルの
//   直径値（mm）を断面積（cm²）に変換し、口側→声帯側の原データを逆順にしたもの。
//   変換式: A = π × (d/20)²
const CONTROL_POINTS: Record<VowelId, number[]> = {
  // /a/: 口腔中央〜後方が最も広い。咽頭下部にやや狭窄あり
  a: [1.13, 1.13, 5.31, 2.01, 1.13, 1.54, 3.14, 5.31, 7.07, 9.08, 11.34, 11.34, 9.08, 7.07, 6.16, 8.04],
  // /i/: 咽頭が広く、口蓋〜歯槽部（声帯側から約70%）に強い狭窄
  i: [1.13, 1.13, 8.04, 8.04, 8.04, 8.04, 8.04, 8.04, 4.52, 2.01, 0.79, 0.79, 0.79, 1.13, 1.54, 4.52],
  // /u/: 中咽頭が広く、軟口蓋部（声帯側から約55%）に狭窄。唇も丸まる
  u: [1.13, 1.13, 7.07, 7.07, 7.07, 7.07, 5.31, 2.55, 1.54, 3.80, 5.31, 4.52, 3.80, 3.14, 1.54, 2.01],
  // /e/: 咽頭が広く、口蓋部に中程度の狭窄（/i/ より緩やか）
  e: [1.13, 1.13, 7.07, 7.07, 7.07, 7.07, 6.16, 4.52, 2.55, 2.01, 2.01, 2.55, 3.14, 3.80, 3.80, 4.52],
  // /o/: 口腔後方〜中央が広く、咽頭部と唇の双方が狭い
  o: [1.13, 1.13, 7.07, 3.80, 2.01, 1.54, 2.01, 3.80, 6.16, 9.08, 11.34, 11.34, 8.04, 5.31, 3.80, 1.54],
};

/** 制御点列を targetN 点に線形補間する */
function interpolateAreas(src: number[], targetN: number): number[] {
  const srcN = src.length;
  const result: number[] = new Array(targetN);
  for (let i = 0; i < targetN; i++) {
    const t = (i / (targetN - 1)) * (srcN - 1);
    const j = Math.floor(t);
    const frac = t - j;
    const a0 = src[Math.min(j, srcN - 1)];
    const a1 = src[Math.min(j + 1, srcN - 1)];
    result[i] = a0 + frac * (a1 - a0);
  }
  return result;
}

// NUM_SECTIONS 点に展開済みのプリセット
export const VOWEL_PRESETS: Record<VowelId, number[]> = {
  a: interpolateAreas(CONTROL_POINTS.a, NUM_SECTIONS),
  i: interpolateAreas(CONTROL_POINTS.i, NUM_SECTIONS),
  u: interpolateAreas(CONTROL_POINTS.u, NUM_SECTIONS),
  e: interpolateAreas(CONTROL_POINTS.e, NUM_SECTIONS),
  o: interpolateAreas(CONTROL_POINTS.o, NUM_SECTIONS),
};

export const VOWEL_LABELS: Record<VowelId, string> = {
  a: "あ", i: "い", u: "う", e: "え", o: "お",
};

export const VOWEL_ORDER: VowelId[] = ["a", "i", "u", "e", "o"];
