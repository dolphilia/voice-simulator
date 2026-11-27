// 固定の音声時計と事前登録した期待値を候補・上流の両方に渡す。
class ModelContext {
  currentTime = 0;
  state = "suspended";
  destination = {};
  sources = [];

  constructor(duration, outputLatency, baseLatency) {
    Object.assign(this, { duration, outputLatency, baseLatency });
  }

  createBufferSource() {
    const source = {
      connect() {},
      disconnect() { this.disconnected = true; },
      stop() { this.stopped = true; },
      start(when, offset) {
        this.startArgs = [when, offset];
        this.queuedEnd = this.onended;
      },
    };
    this.sources.push(source);
    return source;
  }

  async decodeAudioData() { return { duration: this.duration }; }

  setState(state) {
    this.state = state;
    this.onstatechange?.();
  }

  async resume() {
    if (this.rejectResume) throw new Error("観測用の中断");
    if (this.deferResume) return new Promise((_resolve, reject) => { this.rejectPending = reject; });
    this.setState("running");
  }

  async close() { this.setState("closed"); }
}

export async function checkDuetClock(engines, caseSpec) {
  const spec = caseSpec.virtual_clock;
  const onlyTiming = spec.maximum_time_error_seconds;
  let now = 0;
  const original = Object.getOwnPropertyDescriptor(performance, "now");
  Object.defineProperty(performance, "now", { configurable: true, value: () => now });
  try {
    const output = {};
    for (const [name, { make, read }] of Object.entries(engines)) {
      output[name] = [];
      for (const scenario of spec.scenarios) {
        const context = new ModelContext(caseSpec.source.duration_seconds,
          scenario.output_latency_seconds ?? spec.output_latency_seconds, spec.base_latency_seconds);
        const engine = make(context);
        const steps = [];
        await engine.load(new ArrayBuffer(0));
        for (const [index, step] of scenario.steps.entries()) {
          const expected = name === "upstream" && step.upstream_playing !== undefined
            ? { ...step, playing: step.upstream_playing } : step;
          now = 1000 + index * 100;
          context.currentTime = expected.at;
          if (expected.stamp) {
            const [contextTime, age] = expected.stamp;
            context.getOutputTimestamp = () => ({ contextTime, performanceTime: contextTime > 0 ? now - age : 0 });
          }
          const count = context.sources.length;
          const previous = context.sources.at(-1);
          switch (expected.action) {
            case "play": engine.play(); break;
            case "pause": engine.pause(); break;
            case "seek": engine.seek(expected.offset); break;
            case "end": previous.queuedEnd(); break;
            case "old_end": context.sources.at(-2).queuedEnd(); break;
            case "interrupt": context.setState("interrupted"); break;
            case "reject_resume":
              context.rejectResume = true;
              engine.play();
              break;
            case "defer_resume":
              context.deferResume = true;
              engine.play();
              break;
            case "reject_pending":
              context.rejectPending(new Error("保留中の再開を拒否"));
              await new Promise((settled) => setImmediate(settled));
              break;
          }
          await Promise.resolve();
          const actual = read(engine);
          const started = context.sources.length > count ? context.sources.at(-1).startArgs : null;
          const startMatches = expected.start ? context.sources.length === count + 1 && started?.every(
            (value, i) => Math.abs(value - expected.start[i]) <= onlyTiming) : started === null;
          const shouldStopPrevious = previous && (expected.action === "pause" || expected.action === "interrupt"
            || (expected.action === "seek" && expected.playing) || (expected.action === "reject_pending" && !expected.playing));
          const passed = Math.abs(actual.time - expected.time) <= onlyTiming && actual.playing === expected.playing
            && actual.epoch === expected.epoch && startMatches
            && (!shouldStopPrevious || (previous.stopped && previous.disconnected));
          steps.push({ index, expected, actual, started, passed });
        }
        engine.dispose();
        await Promise.resolve();
        const released = context.state === "closed" && context.sources.at(-1).disconnected === true;
        output[name].push({ id: scenario.id, steps, released, passed: steps.every((step) => step.passed) && released });
      }
    }
    return output;
  } finally {
    if (original) Object.defineProperty(performance, "now", original);
    else delete performance.now;
  }
}
