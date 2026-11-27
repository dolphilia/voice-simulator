export function smoothMarkerPCM(marker) {
  const width = marker.frames_per_chip;
  const channel = new Float32Array(marker.chips * width);
  let state = marker.seed;
  const chips = Array.from({ length: marker.chips }, () => {
    state ^= state << 13;
    state ^= state >>> 17;
    state ^= state << 5;
    return state & 1 ? 1 : -1;
  });
  for (let j = 0; j < marker.chips; j++) {
    const initial = chips[j];
    const final = chips[(j + 1) % marker.chips];
    for (let i = 0; i < width; i++) {
      const t = i / width;
      const fraction = (3 - 2 * t) * t * t;
      channel[j * width + i] = (initial + (final - initial) * fraction) / marker.scale;
    }
  }
  return channel;
}

export function installSharedContextMarker(settings, makeSmoothMarker) {
  const Original = globalThis.AudioContext;
  globalThis.AudioContext = class extends Original {
    #markerWorklet;

    constructor(options) {
      super(options);
      // Safariでは登録を差し替えたラッパーをContextの存続中保持する。
      this.#markerWorklet = this.audioWorklet;
      const addModule = this.#markerWorklet.addModule.bind(this.#markerWorklet);
      this.#markerWorklet.addModule = async (url, moduleOptions) => {
        if (!String(url).includes(settings.moduleName ?? "live-processor")) return addModule(url, moduleOptions);
        await addModule("/research-shared-context-marker.js");
        await addModule(url, moduleOptions);
        const q = settings.quantum;
        const startFrame = (Math.ceil(this.currentTime * this.sampleRate / q) + settings.initial_lead_quanta) * q;
        const smooth = settings.smooth_marker && makeSmoothMarker(settings.smooth_marker);
        const inPhase = settings.in_phase_marker && makeSmoothMarker(settings.in_phase_marker);
        const channels = inPhase ? 2 : 1;
        const buffer = this.createBuffer(channels, smooth?.length ?? settings.capture_quanta * q, this.sampleRate);
        const data = buffer.getChannelData(0);
        if (smooth) {
          data.set(smooth);
        } else {
          for (let i = 0; i < data.length; i++) {
            data[i] = ((i * settings.multiplier + settings.offset) % settings.modulus - settings.center) / settings.scale;
          }
        }
        if (inPhase) buffer.getChannelData(1).set(inPhase);
        const source = this.createBufferSource();
        source.buffer = buffer;
        source.loop = true;
        const observer = new AudioWorkletNode(this, "chimera-shared-context-marker", {
          numberOfInputs: 1, numberOfOutputs: 1,
          outputChannelCount: [settings.stereo_difference ? 2 : 1], channelCount: channels,
          processorOptions: { startFrame, quantum: q, readyQuanta: settings.ready_quanta,
            captureQuanta: settings.capture_quanta,
            traceAttachQuanta: settings.trace_request_before_marker ? undefined : settings.trace_attach_quanta,
            observeInput: settings.observe_input, observeTiming: settings.observe_timing },
        });
        let finishMarker;
        if (settings.defer_close_until_marker) {
          this.markerCompletion = new Promise((resolve) => { finishMarker = resolve; });
        }
        const requestTrace = () => globalThis.chimeraWaitForSystemTrace({
          epochMs: performance.timeOrigin + performance.now(),
          contextFrame: Math.round(this.currentTime * this.sampleRate),
        });
        let attachTrace;
        const attached = settings.waitForSystemTrace && settings.trace_attach_quanta
          ? new Promise((resolve) => { attachTrace = resolve; }) : null;
        const ready = new Promise((resolve) => {
          observer.port.onmessage = ({ data: result }) => {
            if (result === "ready") {
              resolve();
            } else if (result === "trace-attach") {
              attachTrace?.();
            } else {
              globalThis.chimeraSharedContextMarker = { ...result, startFrame, sampleRate: this.sampleRate };
              finishMarker?.();
            }
          };
        });
        source.connect(observer).connect(this.destination);
        source.start(startFrame / this.sampleRate);
        if (settings.trace_request_before_marker) attachTrace?.();
        await (attached ? Promise.all([ready, attached.then(requestTrace)]) : ready);
        if (settings.waitForSystemTrace) {
          if (!attached) await requestTrace();
          console.timeStamp("chimera-audioipc-gate-open");
        }
      };
    }

    async close() {
      if (this.markerCompletion && this.state === "running") {
        let timeout;
        try {
          await Promise.race([
            this.markerCompletion,
            new Promise((resolve) => { timeout = setTimeout(resolve, 5000); }),
          ]);
        } finally {
          clearTimeout(timeout);
        }
      }
      return super.close();
    }
  };
}

export function readSharedContextMarker() {
  const { pcm, frames, inputFrames, callbackEpochMs, startFrame, sampleRate } = globalThis.chimeraSharedContextMarker;
  const bytes = new Uint8Array(pcm.buffer);
  let binary = "";
  for (let first = 0; first < bytes.length; first += 8192) {
    binary += String.fromCharCode(...bytes.subarray(first, first + 8192));
  }
  return { pcm: btoa(binary), frames: Array.from(frames), startFrame, sampleRate,
    ...(inputFrames && { inputFrames: Array.from(inputFrames) }),
    ...(callbackEpochMs && { callbackEpochMs: Array.from(callbackEpochMs) }) };
}
