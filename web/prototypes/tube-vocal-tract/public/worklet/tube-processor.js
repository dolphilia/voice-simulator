// AudioWorkletProcessor: Kelly–Lochbaum デジタル波動管による音声合成

const NUM_SECTIONS = 16;

class TubeProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.frequency = 220;
    this.gain = 0.12;
    this.sawPhase = 0;
    this.rightWave = new Float32Array(NUM_SECTIONS + 1);
    this.leftWave = new Float32Array(NUM_SECTIONS + 1);
    this.reflectionCoeffs = new Float32Array(NUM_SECTIONS);
    // デフォルト: 均一管（反射なし）+ 口端開放
    this.reflectionCoeffs[NUM_SECTIONS - 1] = -0.85;

    this.port.onmessage = (event) => {
      const { type, data } = event.data;
      if (type === "setReflectionCoeffs") {
        this.reflectionCoeffs = new Float32Array(data);
      } else if (type === "setFrequency") {
        this.frequency = data;
      } else if (type === "setGain") {
        this.gain = data;
      }
    };
  }

  nextSawtooth() {
    this.sawPhase += this.frequency / sampleRate;
    if (this.sawPhase >= 1.0) this.sawPhase -= 1.0;
    return 2.0 * this.sawPhase - 1.0;
  }

  stepTube(glottalPressure) {
    const N = NUM_SECTIONS;
    const k = this.reflectionCoeffs;
    const right = this.rightWave;
    const left = this.leftWave;

    // グロッタル端入力
    const glottalReflect = 0.95;
    right[0] = glottalPressure + glottalReflect * left[0];

    // セクション間散乱
    for (let i = 0; i < N - 1; i++) {
      const ki = k[i];
      const r = right[i];
      const l = left[i + 1];
      right[i + 1] = (1 + ki) * r - ki * l;
      left[i]     = (1 - ki) * l + ki * r;
    }

    // 口端反射
    left[N - 1] = k[N - 1] * right[N - 1];

    return right[N - 1];
  }

  process(_inputs, outputs) {
    const output = outputs[0]?.[0];
    if (!output) return true;

    for (let i = 0; i < output.length; i++) {
      const saw = this.nextSawtooth();
      output[i] = this.stepTube(saw * 0.5) * this.gain;
    }

    return true;
  }
}

registerProcessor("tube-processor", TubeProcessor);
