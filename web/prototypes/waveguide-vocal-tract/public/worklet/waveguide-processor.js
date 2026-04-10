// AudioWorkletProcessor: 改良版 Kelly–Lochbaum デジタル波動管
//
// 改修点（第2プロトタイプとの差分）:
//   1. ダブルバッファリング → セクションごとに正確な 1 サンプル遅延を実現
//   2. 2x 内部オーバーサンプリング → N=44 セクションで正確な共鳴周波数を実現
//   3. LF モデル声帯音源（α=0 簡易版）→ のこぎり波より自然な声質
//   4. セクションごとの損失係数 → 自然なスペクトル傾斜と Q 値

const NUM_SECTIONS = 44;

class WaveguideProcessor extends AudioWorkletProcessor {
  constructor() {
    super();

    // ── LF 音源パラメータ ──────────────────────────────────────
    this.frequency = 220;
    this.gain      = 0.12;
    this.tpFrac    = 0.5;    // Tp/T0 = 0.5/(Rg=1.0)
    this.teFrac    = 0.65;   // Te/T0 = 0.5*(1+Rk=0.3)/1.0
    this.ee        = Math.sin(Math.PI * 0.3); // sin(π·Rk)
    this.lfPhase   = 0;

    // ── 波動管状態（ダブルバッファ）─────────────────────────────
    // 現在値と前ステップ値をスワップして使用（アロケーションゼロ）
    this.rightA = new Float64Array(NUM_SECTIONS);
    this.rightB = new Float64Array(NUM_SECTIONS);
    this.leftA  = new Float64Array(NUM_SECTIONS);
    this.leftB  = new Float64Array(NUM_SECTIONS);
    // 現在の「書き込み先」バッファを A とする
    this.right    = this.rightA;
    this.left     = this.leftA;
    this.rightPrev = this.rightB;
    this.leftPrev  = this.leftB;

    // ── フィルター係数（メインスレッドから受信）────────────────
    this.k    = new Float32Array(NUM_SECTIONS); // 反射係数
    this.loss = new Float32Array(NUM_SECTIONS).fill(0.998); // 損失係数
    this.k[NUM_SECTIONS - 1] = -0.85; // 口端開放反射（初期値）

    // ── メッセージハンドラ ────────────────────────────────────
    this.port.onmessage = (event) => {
      const { type, data } = event.data;
      switch (type) {
        case "setReflectionCoeffs":
          this.k = new Float32Array(data);
          break;
        case "setLossCoeffs":
          this.loss = new Float32Array(data);
          break;
        case "setFrequency":
          this.frequency = data;
          break;
        case "setGain":
          this.gain = data;
          break;
        case "setLFParams":
          // rg, rk から tpFrac, teFrac, ee を再計算
          this.tpFrac = 0.5 / Math.max(0.3, data.rg);
          this.teFrac = Math.min(0.95, this.tpFrac * (1 + Math.max(0.05, data.rk)));
          this.ee     = Math.abs(Math.sin(Math.PI * Math.max(0.05, data.rk)));
          break;
      }
    };
  }

  // ─── LF 音源：正規化位相 φ から 1 サンプル生成 ───────────────
  // 内部サンプルレートに対して位相を進める
  nextLFSample() {
    const phi = this.lfPhase;

    let v;
    if (phi < this.teFrac) {
      // 開口相: 半正弦（0 → 正ピーク → 負ディップ）
      v = Math.sin((Math.PI * phi) / this.tpFrac);
    } else {
      // 戻り相: 線形復帰（-Ee → 0）
      v = this.ee * (phi - 1.0) / (1.0 - this.teFrac);
    }

    // 内部サンプルレート = 2 × sampleRate で位相を進める
    this.lfPhase += this.frequency / (2 * sampleRate);
    if (this.lfPhase >= 1.0) this.lfPhase -= 1.0;

    return v;
  }

  // ─── 波動管 1 内部ステップ ────────────────────────────────────
  // ダブルバッファ: rightPrev/leftPrev（旧値）→ right/left（新値）
  stepWaveguide(glottalInput) {
    const N   = NUM_SECTIONS;
    const k   = this.k;
    const los = this.loss;
    const rp  = this.rightPrev;
    const lp  = this.leftPrev;
    const r   = this.right;
    const l   = this.left;

    // グロッタル境界（声門側: 軟壁反射 0.95）
    r[0] = glottalInput + 0.95 * lp[0];

    // 内部セクション境界の散乱（すべて旧値 rp/lp を参照）
    for (let i = 0; i < N - 1; i++) {
      const ki  = k[i];
      const lo  = los[i];
      r[i + 1] = ((1 + ki) * rp[i]     - ki * lp[i + 1]) * lo;
      l[i]     = ((1 - ki) * lp[i + 1] + ki * rp[i])     * lo;
    }

    // 口端反射（開放端）
    l[N - 1] = k[N - 1] * rp[N - 1] * los[N - 1];

    // 口端出力: 現在口端に到達していた右進行波 + 左進行波（旧値）
    const out = rp[N - 1] + lp[N - 1];

    // バッファスワップ: 新値が次ステップの旧値になる
    let tmp;
    tmp = this.right; this.right = this.rightPrev; this.rightPrev = tmp;
    tmp = this.left;  this.left  = this.leftPrev;  this.leftPrev  = tmp;

    return out;
  }

  // ─── AudioWorklet process ────────────────────────────────────
  process(_inputs, outputs) {
    const out = outputs[0]?.[0];
    if (!out) return true;

    for (let i = 0; i < out.length; i++) {
      // 2x 内部オーバーサンプリング: 1 出力サンプルあたり 2 内部ステップ
      const src1 = this.nextLFSample() * 0.4;
      const s1   = this.stepWaveguide(src1);

      const src2 = this.nextLFSample() * 0.4;
      const s2   = this.stepWaveguide(src2);

      // 単純平均でダウンサンプル（声道の低域特性がすでに帯域制限）
      out[i] = (s1 + s2) * 0.5 * this.gain;
    }

    return true;
  }
}

registerProcessor("waveguide-processor", WaveguideProcessor);
