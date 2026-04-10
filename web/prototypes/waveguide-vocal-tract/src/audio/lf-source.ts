// LF モデル（Liljencrants–Fant 1985）による声門流速微分波形の生成
//
// 開口相（0 ≤ φ < teFrac）:
//   u'(φ) = sin(π · φ / tpFrac)          … α=0 簡易版（音響的に十分）
//
// 閉鎖戻り相（teFrac ≤ φ < 1）:
//   u'(φ) = Ee · (φ - 1) / (1 - teFrac)  … 線形復帰
//
// φ ∈ [0, 1) はピッチ周期内の正規化位相。
// 出力は 0 から始まり正のピークを経て負のディップ（-Ee）へ、
// その後 0 に戻るという LF 波形の基本形状を再現する。

export type LFParams = {
  /** 開口比 Rg = 0.5T₀/Tp（大きいほど短い開口相）。範囲: 0.5–2.0, 標準: 1.0 */
  rg: number;
  /** 非対称比 Rk = (Te–Tp)/Tp（大きいほどディップが深い）。範囲: 0.1–0.6, 標準: 0.3 */
  rk: number;
};

/** LF 波形の計算に必要な導出パラメータ */
export type LFDerived = {
  /** Tp/T₀: ピーク位相（正規化） */
  tpFrac: number;
  /** Te/T₀: 閉鎖開始位相（正規化） */
  teFrac: number;
  /** 閉鎖時の振幅 Ee = sin(π·Rk) */
  ee: number;
};

/** Rg, Rk から導出パラメータを計算 */
export function deriveLFParams(p: LFParams): LFDerived {
  const tpFrac = 0.5 / Math.max(0.3, p.rg);
  const teFrac = tpFrac * (1 + Math.max(0.05, p.rk));
  // teFrac が 1 を超えないよう clamp（高 Rg × 高 Rk の組み合わせ対策）
  const teFracClamped = Math.min(0.95, teFrac);
  const ee = Math.abs(Math.sin(Math.PI * Math.max(0.05, p.rk)));
  return { tpFrac, teFrac: teFracClamped, ee };
}

/**
 * 正規化位相 φ ∈ [0, 1) から LF 波形の 1 サンプルを返す
 * 戻り値の範囲: [-Ee, +1.0] 程度
 */
export function lfSample(phi: number, d: LFDerived): number {
  const { tpFrac, teFrac, ee } = d;
  if (phi < teFrac) {
    // 開口相: 半正弦 → 負へ
    return Math.sin((Math.PI * phi) / tpFrac);
  } else {
    // 線形戻り相: -ee から 0 へ線形復帰
    return ee * (phi - 1.0) / (1.0 - teFrac);
  }
}
