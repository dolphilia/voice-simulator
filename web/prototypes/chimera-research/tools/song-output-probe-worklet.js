// 計測用の並列ノード。歌唱の出力を読み取り、この枝の出力は無音にする。
class SongOutputProbe extends AudioWorkletProcessor {
  constructor({ processorOptions: { quantum, captureQuanta } }) {
    super();
    this.quantum = quantum;
    this.pcm = new Float32Array(quantum * captureQuanta);
    this.frames = new Float64Array(captureQuanta);
    this.index = 0;
  }

  process(inputs, outputs) {
    const output = outputs[0][0];
    output.fill(0);
    if (output.length !== this.quantum) {
      this.port.postMessage({ error: `出力の観測量子が ${output.length} フレームでした` });
      return false;
    }
    const channel = inputs[0]?.[0];
    // 接続前から呼ばれても、歌唱枝の入力が届いた量子を採取の起点にする。
    if (this.index === 0 && !channel) return true;
    if (channel) this.pcm.set(channel, this.index * this.quantum);
    this.frames[this.index++] = currentFrame;
    if (this.index < this.frames.length) return true;
    this.port.postMessage({ pcm: this.pcm, frames: this.frames }, [this.pcm.buffer, this.frames.buffer]);
    return false;
  }
}

registerProcessor("chimera-song-output-probe", SongOutputProbe);
