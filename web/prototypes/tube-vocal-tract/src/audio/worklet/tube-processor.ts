// AudioWorkletProcessor: Kelly–Lochbaum デジタル波動管による音声合成
// このファイルは AudioWorklet スコープで実行される（DOM API 不可）

const NUM_SECTIONS = 16;
const TRACT_LENGTH_CM = 17.0;
const SPEED_OF_SOUND = 35000; // cm/s

class TubeProcessor extends AudioWorkletProcessor {
  private phase = 0;
  private frequency = 220;
  private gain = 0.12;

  // Kelly–Lochbaum 波動管の状態
  // 各セクションの右進行波・左進行波の圧力
  private rightWave: Float32Array;
  private leftWave: Float32Array;
  private reflectionCoeffs: Float32Array;

  // のこぎり波の周期カウンタ
  private sawPhase = 0;

  constructor() {
    super();
    this.rightWave = new Float32Array(NUM_SECTIONS + 1);
    this.leftWave = new Float32Array(NUM_SECTIONS + 1);
    this.reflectionCoeffs = new Float32Array(NUM_SECTIONS);

    // 初期反射係数（均一管）
    this.reflectionCoeffs.fill(0);
    this.reflectionCoeffs[NUM_SECTIONS - 1] = -0.85; // 口端開放

    this.port.onmessage = (event: MessageEvent) => {
      const { type, data } = event.data as { type: string; data: unknown };
      if (type === "setReflectionCoeffs" && data instanceof Float32Array) {
        this.reflectionCoeffs = data;
      } else if (type === "setFrequency" && typeof data === "number") {
        this.frequency = data;
      } else if (type === "setGain" && typeof data === "number") {
        this.gain = data;
      }
    };
  }

  // のこぎり波を 1 サンプル生成（-1 〜 +1）
  private nextSawtooth(): number {
    this.sawPhase += this.frequency / sampleRate;
    if (this.sawPhase >= 1.0) this.sawPhase -= 1.0;
    return 2.0 * this.sawPhase - 1.0;
  }

  // Kelly–Lochbaum 1 ステップ
  // 入力: グロッタル側励振圧力
  // 出力: 口端の圧力（音声出力）
  private stepTube(glottalPressure: number): number {
    const N = NUM_SECTIONS;
    const k = this.reflectionCoeffs;
    const right = this.rightWave;
    const left = this.leftWave;

    // グロッタル端: 声門は軟壁（反射係数 ~0.95）
    const glottalReflect = 0.95;
    right[0] = glottalPressure + glottalReflect * left[0];

    // セクション境界での散乱
    for (let i = 0; i < N - 1; i++) {
      const ki = k[i];
      const r = right[i];
      const l = left[i + 1];
      right[i + 1] = (1 + ki) * r - ki * l;
      left[i] = (1 - ki) * l + ki * r;
    }

    // 口端反射（開放端）
    const km = k[N - 1];
    left[N - 1] = km * right[N - 1];

    // 出力: 口端の圧力（右進行波）
    const output = right[N - 1];

    return output;
  }

  process(
    _inputs: Float32Array[][],
    outputs: Float32Array[][],
    _parameters: Record<string, Float32Array>
  ): boolean {
    const output = outputs[0]?.[0];
    if (!output) return true;

    // 声道の長さから1セクションのサンプル遅延を計算
    const sectionDelaySamples =
      (TRACT_LENGTH_CM / NUM_SECTIONS / SPEED_OF_SOUND) * sampleRate;

    // 簡略化: サンプル毎に波動管を 1 ステップ進める
    // （本来は sectionDelaySamples 分の遅延バッファが必要だが、
    //   ここでは直接散乱を実行する簡易モデルを使用）
    void sectionDelaySamples;

    for (let i = 0; i < output.length; i++) {
      const saw = this.nextSawtooth();
      const sample = this.stepTube(saw * 0.5);
      output[i] = sample * this.gain;
    }

    return true;
  }
}

registerProcessor("tube-processor", TubeProcessor);
