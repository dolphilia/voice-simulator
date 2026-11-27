// 計測ページ専用。既存音の入力をそのまま出力し、採取時刻とPCMを保存する。
class SharedContextMarker extends AudioWorkletProcessor {
  constructor({ processorOptions: settings }) {
    super();
    this.settings = settings;
    this.pcm = new Float32Array(settings.captureQuanta * settings.quantum);
    this.frames = new Uint32Array(settings.captureQuanta);
    this.inputFrames = settings.observeInput ? new Uint32Array(settings.captureQuanta) : undefined;
    this.callbackEpochMs = settings.observeTiming ? new Float64Array(settings.captureQuanta) : undefined;
    this.index = 0;
  }

  process(inputs, outputs) {
    const epochMs = this.callbackEpochMs ? Date.now() : undefined;
    if (epochMs === undefined) console.timeStamp(`chimera-marker:${currentFrame}`);
    const input = inputs[0]?.[0];
    const inPhase = inputs[0]?.[1];
    const [left, right] = outputs[0];
    if (input) left.set(input);
    if (right && inPhase) {
      for (let i = 0; i < left.length; i++) {
        const difference = left[i];
        left[i] = inPhase[i] + difference;
        right[i] = inPhase[i] - difference;
      }
    } else if (right) {
      // モノラル歌唱は両チャンネルに入り、逆相の先行音は差分で復元できる。
      for (let i = 0; i < left.length; i++) right[i] = -left[i];
    }
    const { startFrame, quantum, readyQuanta, captureQuanta, traceAttachQuanta } = this.settings;
    if (currentFrame < startFrame || this.index === captureQuanta) return true;
    this.frames[this.index] = currentFrame;
    if (this.inputFrames) this.inputFrames[this.index] = input?.length ?? 0;
    if (this.callbackEpochMs) this.callbackEpochMs[this.index] = epochMs;
    this.pcm.set(inPhase && input ? input : left, this.index * quantum);
    this.index++;
    if (this.index === traceAttachQuanta) this.port.postMessage("trace-attach");
    if (this.index === readyQuanta) this.port.postMessage("ready");
    if (this.index === captureQuanta) {
      const transfers = [this.pcm.buffer, this.frames.buffer];
      if (this.inputFrames) transfers.push(this.inputFrames.buffer);
      if (this.callbackEpochMs) transfers.push(this.callbackEpochMs.buffer);
      this.port.postMessage({ pcm: this.pcm, frames: this.frames, inputFrames: this.inputFrames,
        callbackEpochMs: this.callbackEpochMs }, transfers);
    }
    return true;
  }
}

const register = globalThis.registerProcessor.bind(globalThis);
register("chimera-shared-context-marker", SharedContextMarker);
// 発声の本体は通常のモジュールに任せ、コンストラクターの境界だけを採る。
globalThis.registerProcessor = (name, Processor) => register(name, name !== "chimera-fixed-live" ? Processor
  : class extends Processor {
    constructor(options) {
      console.timeStamp(`chimera-live-start:${currentFrame}`);
      super(options);
      console.timeStamp(`chimera-live-end:${currentFrame}`);
    }
  });
