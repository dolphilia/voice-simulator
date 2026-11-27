// 実ブラウザの録画状態と、必要に応じてCanvasの作画を記録する。
export function trackRecorder({ webm, nativeFormats, observeClipDraws }) {
  const taps = [];
  const takes = [];
  const closedContexts = [];
  const capabilityChecks = [];
  let nativeCapabilities;
  if (webm || nativeFormats) {
    const native = MediaRecorder.isTypeSupported.bind(MediaRecorder);
    nativeCapabilities = nativeFormats?.map((type) => ({ type, supported: native(type) }));
    MediaRecorder.isTypeSupported = (type) => {
      const nativeSupported = native(type);
      const suppressed = webm?.suppressed_mime_types?.includes(type) ?? (type.split(";")[0] === webm?.suppressed_mime_essence);
      const reported = nativeSupported && !suppressed;
      capabilityChecks.push({ type, nativeSupported, reported });
      return reported;
    };
  }
  const closeContext = AudioContext.prototype.close;
  AudioContext.prototype.close = async function () {
    await closeContext.call(this);
    closedContexts.push(this.state);
  };
  const createTap = AudioContext.prototype.createMediaStreamDestination;
  AudioContext.prototype.createMediaStreamDestination = function () {
    const destination = createTap.call(this);
    taps.push({ context: this, tracks: destination.stream.getAudioTracks() });
    return destination;
  };
  const capturedCanvases = [];
  if (observeClipDraws) {
    const drawsByCanvas = new WeakMap();
    const captureStream = HTMLCanvasElement.prototype.captureStream;
    HTMLCanvasElement.prototype.captureStream = function (...args) {
      const stream = captureStream.apply(this, args);
      const context = taps.at(-1).context;
      const draw = { startedAtMs: performance.now(), startedContextFrame: Math.round(context.currentTime * context.sampleRate), frames: [] };
      drawsByCanvas.set(this, { context, frames: draw.frames });
      capturedCanvases.push(draw);
      return stream;
    };
    const drawImage = CanvasRenderingContext2D.prototype.drawImage;
    CanvasRenderingContext2D.prototype.drawImage = function (...args) {
      drawImage.apply(this, args);
      const captured = drawsByCanvas.get(this.canvas);
      if (captured) {
        const { context, frames } = captured;
        frames.push({ atMs: performance.now(), contextFrame: Math.round(context.currentTime * context.sampleRate) });
      }
    };
  }
  globalThis.MediaRecorder = new Proxy(MediaRecorder, {
    construct(target, args) {
      const recorder = Reflect.construct(target, args);
      const take = { recorder, requestedMime: args[1]?.mimeType, tracks: recorder.stream.getTracks(),
        requested: null, stopped: null, chunks: [], chunkMimes: [] };
      const stop = recorder.stop.bind(recorder);
      recorder.stop = () => {
        take.requested = performance.now();
        return stop();
      };
      recorder.addEventListener("start", () => { take.started = performance.now(); });
      recorder.addEventListener("dataavailable", ({ data }) => {
        take.chunks.push(data.size);
        if (data.size) take.chunkMimes.push(data.type);
      });
      take.finished = new Promise((resolve) => {
        recorder.addEventListener("stop", () => {
          take.stopped = performance.now();
          resolve();
        }, { once: true });
      });
      takes.push(take);
      return recorder;
    },
  });
  window.inspectRecording = () => ({
    contexts: taps.map((tap) => tap.context.state),
    closedContexts: [...closedContexts],
    capabilityChecks: [...capabilityChecks],
    ...(nativeCapabilities && { nativeCapabilities }),
    ...(observeClipDraws && { capturedCanvases }),
    takes: takes.map(({ recorder, tracks, started, stopped, requested, chunks, requestedMime, chunkMimes }) => ({
      state: recorder.state, started, stopped, requested, chunks, requestedMime, chunkMimes,
      tracks: tracks.map(({ kind, id, readyState }) => ({ kind, id, readyState })),
    })),
  });
  window.awaitRecordingStop = (index) => takes[index].finished;
}
