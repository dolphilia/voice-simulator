import type { LiveTractSample } from "./fixed-worklet-types";
import type { RecordedTract } from "./recorded-tract";

// 録画形式の優先順は固定上流の src/song/record.ts（Jameson Hodge、MIT）に合わせる。
// ライセンスは研究ワークスペースの LICENSE-CHIMERA に記載。
const width = 720;
const height = 1280;
const fps = 30;
const tailMs = 230;
const formats = [
  "video/mp4;codecs=avc1.42E01E,mp4a.40.2", "video/mp4",
  "video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm",
];

export function songRecordingType(): string | undefined {
  if (typeof MediaRecorder === "undefined" || !("captureStream" in HTMLCanvasElement.prototype)) return;
  return formats.find((type) => MediaRecorder.isTypeSupported(type));
}

export type SongRecordingRequest = {
  canvas: HTMLCanvasElement;
  onStarted: () => void;
  includeTract?: boolean;
};

export type SongRecordingOptions = SongRecordingRequest & {
  notes: readonly { note: { midi: number }; beat_seconds: number }[];
  frames: number;
};

export class SongRecording {
  private readonly recorder: MediaRecorder;
  private readonly tracks: MediaStreamTrack[];
  private readonly stopped: Promise<void>;
  private readonly chunks: Blob[] = [];
  private readonly drawnBeats: { index: number; contextFrame: number }[] = [];
  private readonly drawing = { frames: 0, firstContextFrame: 0, lastContextFrame: 0, maximumGapFrames: 0,
    maximumGapEndContextFrame: 0, maximumPaintMilliseconds: 0, maximumPaintContextFrame: 0 };
  private readonly recordingStartContextFrame: number;
  private readonly rate: number;
  private readonly mimeType: string;
  private silence?: ConstantSourceNode;
  private scheduledFrame?: number;
  private animation = 0;
  private failed = false;

  constructor(
    private readonly context: AudioContext, output: AudioNode, options: SongRecordingOptions,
    private readonly tract?: RecordedTract,
  ) {
    const type = songRecordingType();
    if (!type) throw new Error("このブラウザで合成音声付きの動画を録画できません");
    this.mimeType = type;
    this.rate = context.sampleRate;
    const { canvas, notes, frames } = options;
    canvas.width = width;
    canvas.height = height;
    // 録画の各フレームは読み出してエンコーダーへ渡す。
    const paint = canvas.getContext("2d", { alpha: false, willReadFrequently: true });
    if (!paint) throw new Error("録画用キャンバスを準備できません");
    const beats = notes.map(({ beat_seconds }) => Math.round(beat_seconds * this.rate));
    // 末尾の観測は合成が終わってから届くため、採取の2周期だけ識別欄を残す。
    const tractCodeEnd = frames + Math.ceil(2 * this.rate / fps);
    let active = -1;
    const draw = () => {
      const started = performance.now();
      const contextFrame = Math.round(context.currentTime * this.rate);
      const drawing = this.drawing;
      if (drawing.frames === 0) drawing.firstContextFrame = contextFrame;
      else if (contextFrame - drawing.lastContextFrame > drawing.maximumGapFrames) {
        drawing.maximumGapFrames = contextFrame - drawing.lastContextFrame;
        drawing.maximumGapEndContextFrame = contextFrame;
      }
      drawing.frames++;
      drawing.lastContextFrame = contextFrame;
      const frame = this.scheduledFrame === undefined ? -1 : contextFrame - this.scheduledFrame;
      while (active + 1 < beats.length && frame >= beats[active + 1]) {
        active++;
        this.drawnBeats.push({ index: active, contextFrame });
      }
      paint.fillStyle = "#102722";
      paint.fillRect(0, 0, width, height);
      paint.fillStyle = "#e5f1e9";
      paint.textAlign = "center";
      paint.font = "52px system-ui";
      paint.fillText("Voice Simulator", width / 2, tract ? 100 : 245);
      if (tract) {
        paint.save();
        tract.paint(paint, contextFrame, frame < tractCodeEnd);
        paint.restore();
      }
      paint.font = "38px system-ui";
      paint.fillText(active < 0 ? "歌唱を準備中" : `拍 ${active + 1} / ${beats.length}`, width / 2, tract ? 533 : 485);
      paint.fillStyle = active < 0 ? "#748b95" : active % 2 === 0 ? "#36bf7e" : "#ef8750";
      paint.fillRect(168, 550, 384, 180);
      paint.fillStyle = "#102722";
      paint.font = "38px system-ui";
      if (active >= 0) paint.fillText(`MIDI ${notes[active].note.midi}`, width / 2, 655);
      paint.fillStyle = "#e5f1e9";
      paint.font = "30px monospace";
      const elapsed = Math.max(0, Math.min(frame, frames)) / this.rate;
      paint.fillText(`${elapsed.toFixed(3)} s`, width / 2, 842);
      paint.fillStyle = "#294740";
      paint.fillRect(110, 944, 500, 12);
      paint.fillStyle = "#b7d7c8";
      paint.fillRect(110, 944, 500 * elapsed * this.rate / frames, 12);
      const paintMilliseconds = performance.now() - started;
      if (paintMilliseconds > drawing.maximumPaintMilliseconds) {
        drawing.maximumPaintMilliseconds = paintMilliseconds;
        drawing.maximumPaintContextFrame = contextFrame;
      }
      this.animation = requestAnimationFrame(draw);
    };

    const tap = context.createMediaStreamDestination();
    this.tracks = tap.stream.getAudioTracks();
    let recorder: MediaRecorder | undefined;
    try {
      tap.channelCount = 1;
      draw();
      const videoTracks = canvas.captureStream(fps).getVideoTracks();
      this.tracks.push(...videoTracks);
      if (this.tracks.length !== 2 || videoTracks.length !== 1) {
        throw new Error("録画用の音声または映像トラックを取得できません");
      }
      recorder = new MediaRecorder(new MediaStream(this.tracks), { mimeType: type, videoBitsPerSecond: 5_000_000 });
      this.recorder = recorder;
      this.stopped = new Promise((resolve) => {
        this.recorder.onstop = () => {
          this.release();
          resolve();
        };
      });
      recorder.ondataavailable = ({ data }) => {
        if (data.size) this.chunks.push(data);
      };
      recorder.onerror = () => { this.failed = true; };
      output.connect(tap);
      // 歌唱のWorkletが止まった後の無音も同じ音声トラックへ送る。
      const silence = new ConstantSourceNode(context, { offset: 0 });
      silence.connect(tap);
      silence.start();
      this.silence = silence;
      this.recordingStartContextFrame = Math.round(context.currentTime * this.rate);
      recorder.start(500);
      options.onStarted();
    } catch (error) {
      if (recorder?.state === "recording") recorder.stop();
      this.release();
      throw error;
    }
  }

  schedule(contextFrame: number) {
    this.scheduledFrame = contextFrame;
  }

  observeTract(sample: LiveTractSample) {
    this.tract?.receive(sample);
  }

  async finish(contextFrame: number, signal?: AbortSignal) {
    if (contextFrame !== this.scheduledFrame) throw new Error("録画と歌唱の開始フレームが一致しません");
    if (contextFrame <= this.recordingStartContextFrame) throw new Error("録画開始前に合成が始まりました");
    if (this.recorder.state !== "recording") throw new Error("動画の録画が途中で停止しました");
    // 末尾の音声ブロックがトラックとエンコーダーに届くまで待つ。
    await new Promise<void>((resolve) => setTimeout(resolve, tailMs));
    signal?.throwIfAborted();
    const recordingEndContextFrame = Math.round(this.context.currentTime * this.rate);
    if (this.recorder.state === "recording") this.recorder.stop();
    await this.stopped;
    signal?.throwIfAborted();
    if (this.failed || !this.chunks.length) throw new Error("動画の録画結果を取得できません");
    const type = this.mimeType.split(";")[0];
    return {
      file: new File(this.chunks, `worklet-song.${type === "video/mp4" ? "mp4" : "webm"}`, { type }),
      observation: {
        mimeType: this.chunks[0].type || this.mimeType,
        targetVideoFps: fps, width, height, drainWaitMs: tailMs,
        recordingStartContextFrame: this.recordingStartContextFrame,
        recordingEndContextFrame, scheduledContextFrame: contextFrame, drawnBeats: this.drawnBeats,
        drawing: this.drawing,
        trackStates: this.tracks.map(({ kind, readyState }) => ({ kind, readyState })),
        ...(this.tract && { tract: this.tract.observation() }),
      },
    };
  }

  cancel() {
    if (this.recorder.state === "recording") this.recorder.stop();
    this.release();
  }

  private release() {
    cancelAnimationFrame(this.animation);
    if (this.silence) {
      this.silence.stop();
      this.silence.disconnect();
      this.silence = undefined;
    }
    for (const track of this.tracks) track.stop();
  }
}
