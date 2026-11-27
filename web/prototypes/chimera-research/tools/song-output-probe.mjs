// Playwrightの計測時だけ用いる。歌唱ノードと出力先の直接接続は維持する。
export function installSongOutputProbe(settings) {
  const Original = globalThis.AudioContext;
  const connect = AudioWorkletNode.prototype.connect;
  const disconnect = AudioWorkletNode.prototype.disconnect;
  if (settings.holdConnectionsThroughTail) {
    AudioWorkletNode.prototype.disconnect = function (...args) {
      const context = this.context;
      if (args.length === 0 && context.songOutputProbeConnected && context.songOutputProbeDeferred) {
        context.songOutputProbeDeferred.push(this);
        return;
      }
      return disconnect.apply(this, args);
    };
  }
  AudioWorkletNode.prototype.connect = function (target, ...indices) {
    const result = connect.call(this, target, ...indices);
    const context = this.context;
    if (this.numberOfInputs === 0 && target === context.destination
        && context.songOutputProbe && !context.songOutputProbeConnected) {
      context.songOutputProbeConnected = true;
      connect.call(this, context.songOutputProbe);
      connect.call(context.songOutputProbe, target);
    }
    return result;
  };
  globalThis.AudioContext = class extends Original {
    #worklet;

    constructor(options) {
      super(options);
      if (settings.holdConnectionsThroughTail) this.songOutputProbeDeferred = [];
      // Safariでも、書き換えたaddModuleを持つラッパーをContextの存続中は保持する。
      this.#worklet = this.audioWorklet;
      const register = this.#worklet.addModule.bind(this.#worklet);
      this.#worklet.addModule = async (url, moduleOptions) => {
        await register(url, moduleOptions);
        if (!String(url).includes("fixed-processor-entry")) return;
        await register("/research-song-output-probe.js");
        const probe = new AudioWorkletNode(this, "chimera-song-output-probe", {
          numberOfInputs: 1, numberOfOutputs: 1, channelCount: 1, channelCountMode: "explicit",
          outputChannelCount: [1], processorOptions: settings,
        });
        this.songOutputProbe = probe;
        this.songOutputProbeFinished = new Promise((resolve) => {
          probe.port.onmessage = ({ data }) => {
            globalThis.chimeraSongOutputProbe = { ...data, sampleRate: this.sampleRate,
              deferredDisconnects: this.songOutputProbeDeferred?.length };
            resolve();
          };
        });
      };
    }

    async close() {
      // 最終量子の後も観測できるよう、計測時だけContextの終了を待たせる。
      if (this.songOutputProbeConnected && this.state === "running") {
        let timer;
        try {
          await Promise.race([this.songOutputProbeFinished, new Promise((resolve) => {
            timer = setTimeout(resolve, 5000);
          })]);
        } finally {
          clearTimeout(timer);
          const deferred = this.songOutputProbeDeferred;
          this.songOutputProbeDeferred = undefined;
          deferred?.forEach((node) => disconnect.call(node));
        }
      }
      return super.close();
    }
  };
}

export function readSongOutputProbe() {
  const result = globalThis.chimeraSongOutputProbe;
  if (!result || result.error) throw new Error(result?.error ?? "歌唱出力の観測結果がありません");
  const { pcm, frames, sampleRate, deferredDisconnects } = result;
  const bytes = new Uint8Array(pcm.buffer);
  let binary = "";
  for (let start = 0; start < bytes.length; start += 8192) {
    binary += String.fromCharCode(...bytes.subarray(start, start + 8192));
  }
  return { pcm: btoa(binary), frames: Array.from(frames), sampleRate, deferredDisconnects };
}
