// 再生位置と遷移は固定上流の src/show/transport.ts（Jameson Hodge、MIT）を参照。
// ライセンスは研究ワークスペースの LICENSE-CHIMERA に記載。

const restartMargin = 0.05;

export class DuetTransport {
  private readonly context: AudioContext;
  private audio?: AudioBuffer;
  private source?: AudioBufferSourceNode;
  private offset = 0;
  private startedAt = 0;
  private playing = false;
  private rendered = false;
  private wasRunning = false;
  private playbackGeneration = 0;
  private epoch = 0;

  constructor(context = new AudioContext({ latencyHint: "playback" })) {
    this.context = context;
    this.wasRunning = context.state === "running";
    context.onstatechange = () => {
      const running = context.state === "running";
      if (this.wasRunning && !running) this.pause();
      this.wasRunning = running;
    };
  }

  async load(wave: ArrayBuffer) {
    this.audio = await this.context.decodeAudioData(wave);
  }

  get duration() {
    return this.audio?.duration ?? 0;
  }

  snapshot() {
    const time = this.time();
    return { time, playing: this.playing, duration: this.duration, epoch: this.epoch };
  }

  play() {
    if (!this.audio || this.playing) return;
    const generation = ++this.playbackGeneration;
    const session = (navigator as Navigator & { audioSession?: { type: string } }).audioSession;
    try {
      if (session && session.type !== "playback") session.type = "playback";
    } catch {
      // 再生用のセッションを設定できないブラウザでは既定のまま続ける。
    }
    void this.context.resume().catch(() => {
      if (generation === this.playbackGeneration) this.pause();
    });
    if (this.offset >= this.duration - restartMargin) this.offset = 0;
    this.startSource(this.audio);
    this.playing = true;
  }

  pause() {
    if (!this.playing) return;
    this.playbackGeneration++;
    this.offset = this.time();
    this.playing = false;
    this.stopSource();
  }

  seek(seconds: number) {
    if (!Number.isFinite(seconds)) return;
    // シークは同じ再生要求の途中なので、保留中の再開が失敗したら停止する。
    this.epoch++;
    this.offset = Math.min(this.duration, Math.max(0, seconds));
    if (this.playing && this.audio) {
      this.stopSource();
      this.startSource(this.audio);
    }
  }

  dispose() {
    this.playbackGeneration++;
    this.playing = false;
    this.context.onstatechange = null;
    this.stopSource();
    void this.context.close().catch(() => {});
  }

  private startSource(audio: AudioBuffer) {
    const node = this.context.createBufferSource();
    node.buffer = audio;
    node.connect(this.context.destination);
    node.onended = () => {
      if (this.source === node) this.rendered = true;
    };
    this.source = node;
    this.rendered = false;
    this.startedAt = this.context.currentTime;
    node.start(this.startedAt, this.offset);
  }

  private stopSource() {
    const node = this.source;
    this.source = undefined;
    if (!node) return;
    node.onended = null;
    if (!this.rendered) {
      try {
        node.stop();
      } catch {
        // コンテキストがすでに閉じていても接続を外す。
      }
    }
    node.disconnect();
    this.rendered = false;
  }

  private time() {
    if (!this.playing) return this.offset;
    const { context } = this;
    const { contextTime, performanceTime } = context.getOutputTimestamp?.() ?? {};
    const audible = contextTime && Number.isFinite(contextTime) && contextTime > 0
        && performanceTime !== undefined && Number.isFinite(performanceTime)
      ? Math.min(context.currentTime, contextTime + Math.max(0, (performance.now() - performanceTime) / 1000))
      : context.currentTime - (context.outputLatency || context.baseLatency || 0);
    const position = Math.min(this.duration, this.offset + Math.max(0, audible - this.startedAt));
    if (this.rendered && position >= this.duration) {
      this.offset = this.duration;
      this.playing = false;
      this.stopSource();
    }
    return position;
  }
}
