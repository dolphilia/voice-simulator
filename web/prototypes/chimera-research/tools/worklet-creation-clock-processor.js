// モジュール作成時の時計と、再開後に届く連番PCMを記録する。
const moduleClock = { frame: currentFrame, time: currentTime, rate: sampleRate };

class CreationClockProbe extends AudioWorkletProcessor {
  constructor({ processorOptions: { blocks } }) {
    super();
    this.limit = blocks;
    this.blocks = [];
    this.port.postMessage({ type: "created", evaluation: moduleClock,
      constructor: { frame: currentFrame, time: currentTime, rate: sampleRate } });
  }

  process(inputs, outputs) {
    const output = outputs[0][0];
    output.fill(0);
    if (this.blocks.length === this.limit) return false;
    const input = inputs[0];
    this.blocks.push({ frame: currentFrame, time: currentTime, quantum: output.length,
      channels: input.length, samples: input[0] ? Array.from(input[0]) : [] });
    if (this.blocks.length < this.limit) return true;
    this.port.postMessage({ type: "captured", blocks: this.blocks });
    return false;
  }
}

registerProcessor("chimera-creation-clock-probe", CreationClockProbe);
