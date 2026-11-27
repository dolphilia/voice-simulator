// 固定上流の通常録画を動かし、音声出力と録画時刻を観測する。
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { createServer } from "vite";
import { withSafari } from "./safari-webdriver.mjs";

const [casePath, output, upstream] = process.argv.slice(2);
const study = JSON.parse(readFileSync(casePath, "utf8"));

function workletProbe() {
  const processor = join(upstream, "src/worklet/processor.ts");
  return {
    name: "research-song-pcm-observer",
    enforce: "pre",
    transform(source, id) {
      if (id.split("?")[0] !== processor || !source.includes("class ChimeraProcessor")) return;
      const schedule = "const off = x.engine_schedule(h, n, m.lead ?? 0.03, m.replace ? 1 : 0);";
      const render = "const p = this.x.engine_render(this.h, ch0.length);";
      if (!source.includes(schedule) || !source.includes(render)) throw new Error("固定上流の観測点が見つかりません");
      const tail = study.measurement.capture_after_plan_seconds;
      const analysisEnd = Math.max(...study.measurement.audio_alignment_windows_seconds.map(([, end]) => end));
      let observed = source.replace("private failed = false;", `
        private audit?: { samples: Float32Array; used: number; offset: number; end: number;
          initialEngineFrame?: number; rows: number[][] };
        private failed = false;
      `).replace(schedule, `${schedule}
        const auditEnd = Math.max(m.end + ${tail}, ${analysisEnd});
        this.audit = { samples: new Float32Array(Math.ceil((auditEnd + (m.lead ?? 0.03)) * sampleRate)),
          used: 0, offset: off, end: m.end, rows: [] };
      `).replace(render, `
        const audit = this.audit;
        const engineFrame = audit ? Math.round(this.x.engine_clock(this.h) * sampleRate) : 0;
        ${render}
        if (audit) {
          const contextFrame = globalThis.currentFrame;
          if (audit.initialEngineFrame === undefined) {
            audit.initialEngineFrame = engineFrame;
            this.port.postMessage({ type: "research-armed", contextFrame, engineFrame, offset: audit.offset, end: audit.end });
          }
          const valid = Math.min(ch0.length, audit.samples.length - audit.used);
          const view = new Float32Array(this.mem, p, valid);
          audit.samples.set(view, audit.used);
          audit.rows.push([contextFrame, engineFrame, valid, Date.now()]);
          audit.used += valid;
          if (audit.used === audit.samples.length) {
            this.port.postMessage({ type: "research-samples", rows: audit.rows, samples: audit.samples }, [audit.samples.buffer]);
            this.audit = undefined;
          }
        }
      `);
      if (study.schedule_engine_frames) {
        const fields = "private failed = false;";
        const setup = "this.h = this.x.engine_new(sampleRate);";
        const receive = "this.handle(e.data);";
        const next = "const audit = this.audit;";
        for (const point of [fields, setup, receive, next]) {
          if (!observed.includes(point)) throw new Error("固定フレームの観測点が見つかりません");
        }
        observed = observed.replace(fields, `${fields}
          private researchTargetFrame?: number;
          private researchPending?: Extract<ToWorklet, { type: "schedule" }>;
        `).replace(setup, `${setup}
          this.researchTargetFrame = (options.processorOptions as { researchScheduleEngineFrame?: number }).researchScheduleEngineFrame;
        `).replace(receive, `
          const target = this.researchTargetFrame;
          if (target !== undefined && e.data.type === "schedule") {
            const receivedFrame = Math.round(this.x.engine_clock(this.h) * sampleRate);
            if (this.researchPending || receivedFrame > target) {
              throw new Error(\`譜面を指定位置へ渡せません (\${receivedFrame}, \${target})\`);
            }
            this.researchPending = e.data;
            this.port.postMessage({ type: "research-schedule-received", receivedFrame, target });
          } else {
            ${receive}
          }
        `).replace(next, `
          if (this.researchPending && this.researchTargetFrame !== undefined) {
            const appliedFrame = Math.round(this.x.engine_clock(this.h) * sampleRate);
            if (appliedFrame > this.researchTargetFrame) {
              throw new Error(\`譜面の指定位置を過ぎました (\${appliedFrame}, \${this.researchTargetFrame})\`);
            }
            if (appliedFrame === this.researchTargetFrame) {
              const pending = this.researchPending;
              this.researchPending = undefined;
              this.researchTargetFrame = undefined;
              this.handle(pending);
              this.port.postMessage({ type: "research-schedule-applied", appliedFrame });
            }
          }
          ${next}
        `);
      }
      return observed;
    },
  };
}

async function install(mode, score, spec, targetEngineFrame) {
  const [{ engine }, { TUNES, useSing, roll }, { useStore }] = await Promise.all([
    import("/src/audio/AudioEngine.ts"), import("/src/ui/singing.ts"), import("/src/ui/store.ts"),
  ]);
  const result = { mode, events: [], draws: [], recorderEvents: [] };
  window.upstreamPauseReport = result;
  if (targetEngineFrame !== null) {
    const NativeWorkletNode = window.AudioWorkletNode;
    window.AudioWorkletNode = class extends NativeWorkletNode {
      constructor(context, name, options) {
        const settings = name === "chimera" ? { ...options,
          processorOptions: { ...options?.processorOptions, researchScheduleEngineFrame: targetEngineFrame } } : options;
        super(context, name, settings);
      }
    };
    result.stateSnapshots = [];
  }
  TUNES.push({ id: score.id, name: score.id, bpm: score.bpm, lyrics: score.lyrics,
    octave: { male: 0, female: 0, child: 0 }, phrases: [score.notes] });
  useStore.getState().setMode("sing");
  useSing.getState().setTune(score.id);
  useSing.getState().setTempo(1);
  useSing.getState().setKey(0);
  useSing.getState().setVibrato(score.vibrato_cents);
  result.input = { body: useStore.getState().body, source: useStore.getState().source,
    tune: useSing.getState().tune, lyrics: useSing.getState().lyrics, volume: useStore.getState().volume };

  const saveLink = () => [...document.querySelectorAll("a[download]")].find((a) => a.textContent.trim() === "Save");
  const frame = () => Math.round(engine.ctx.currentTime * engine.ctx.sampleRate);
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  let zero, originFrame, captureCanvas, recorder;
  const wall = () => performance.now() - zero;
  const mark = (phase) => result.events.push({ phase, wallMs: wall(), frame: frame(), state: engine.ctx.state,
    recorderState: recorder?.state });
  document.addEventListener("click", (event) => {
    if (event.target.closest("button")?.textContent.trim() === "Record video") result.clickTrusted = event.isTrusted;
  }, true);
  engine.onPlanned((plan) => { result.plan = plan; });

  const drawCodes = (paint) => {
    const wallMs = wall();
    const contextFrame = frame();
    const wallCode = Math.round(wallMs);
    const contextCode = Math.round((contextFrame - originFrame) * 1000 / engine.ctx.sampleRate);
    paint.save();
    paint.fillStyle = "#000";
    paint.fillRect(16, 16, 192, 48);
    paint.fillStyle = "#fff";
    for (const [row, code] of [wallCode, contextCode].entries()) {
      for (let bit = 0; bit < 12; bit++) {
        if (code & (1 << bit)) paint.fillRect(16 + 16 * bit, 16 + 32 * row, 16, 16);
      }
    }
    paint.restore();
    result.draws.push({ wallMs, contextFrame, wallCode, contextCode });
  };
  const capture = HTMLCanvasElement.prototype.captureStream;
  HTMLCanvasElement.prototype.captureStream = function (...args) {
    if (this.width === 720 && this.height === 1280 && engine.ctx) {
      captureCanvas = this;
      zero = performance.now();
      originFrame = frame();
      drawCodes(this.getContext("2d"));
      result.captureStartFrame = originFrame;
      result.captureFps = args[0];
    }
    return capture.apply(this, args);
  };
  const drawImage = CanvasRenderingContext2D.prototype.drawImage;
  CanvasRenderingContext2D.prototype.drawImage = function (...args) {
    const value = drawImage.apply(this, args);
    if (this.canvas === captureCanvas) drawCodes(this);
    return value;
  };
  const NativeRecorder = window.MediaRecorder;
  window.MediaRecorder = class extends NativeRecorder {
    constructor(...args) {
      super(...args);
      recorder = this;
      result.recordTracks = this.stream.getTracks().map(({ kind }) => kind).sort();
      for (const type of ["start", "stop", "error"]) {
        this.addEventListener(type, () => result.recorderEvents.push({ type, wallMs: wall(), frame: frame(), mimeType: this.mimeType }));
      }
    }
  };

  const handlePause = async (armed) => {
    result.armed = armed;
    const rate = result.sampleRate = engine.ctx.sampleRate;
    const planOrigin = armed.contextFrame + Math.round(armed.offset * rate) - armed.engineFrame;
    const shift = Math.round((score.candidate_first_beat_seconds - score.first_beat_seconds) * rate);
    const target = result.targetFrame = planOrigin + spec.candidate_target_output_frames - shift;
    while (frame() < target) {
      if (wall() > spec.timeout_ms) throw new Error("停止位置に達しませんでした");
      await wait(2);
    }
    mark("hold_requested");
    if (mode === "paused") await engine.ctx.suspend();
    mark("held");
    await wait(spec.hold_ms);
    mark("resume_requested");
    if (mode === "paused") await engine.ctx.resume();
    mark("resumed");
  };
  const recordStream = engine.recordStream;
  engine.recordStream = function () {
    const stream = recordStream.call(this);
    this.node.port.addEventListener("message", ({ data }) => {
      if (data.type === "research-armed") void handlePause(data).catch((error) => { result.error = String(error); });
      if (data.type === "research-samples") {
        result.rows = data.rows;
        window.upstreamPausePCM = new Blob([data.samples]);
      }
      if (data.type === "research-schedule-received") result.scheduleReceived = data;
      if (data.type === "research-schedule-applied") result.scheduleApplied = data;
      if (targetEngineFrame !== null && result.armed && data.type === "telemetry") {
        const state = { ...data.t };
        for (const key of ["artic", "phAreas", "orAreas", "pressureRms", "flow", "glottalArea", "glottalFlow"]) {
          state[key] = Array.from(state[key]);
        }
        result.stateSnapshots.push(state);
      }
    });
    return stream;
  };
  window.upstreamPauseRead = () => {
    const link = saveLink();
    return { ...result, saved: link?.download ?? null, hasPCM: !!window.upstreamPausePCM, engineError: engine.error,
      midi: roll.notes.filter((note) => note.demo).map(({ midi, text, t0, t1 }) => ({ midi, text, t0, t1 })),
      wasm: performance.getEntriesByType("resource").find((entry) => entry.name.includes("/chimera.wasm")
        && entry.initiatorType === "fetch")?.name };
  };
}

const server = await createServer({ root: upstream, plugins: [workletProbe()],
  server: { host: "127.0.0.1", port: 0, hmr: false, watch: null } });
try {
  await server.listen();
  const url = `http://127.0.0.1:${server.httpServer.address().port}/`;
  for (const [index, order] of study.condition_order.entries()) {
    for (const mode of order) {
      const targetEngineFrame = study.schedule_engine_frames?.[index] ?? null;
      const folder = join(output, `${index + 1}-${mode}`);
      mkdirSync(folder);
      const report = { mode };
      try {
        await withSafari(async (command, capabilities) => {
          report.capabilities = capabilities;
          await command("/url", { url });
          const execute = (script) => command("/execute/sync", { script, args: [] });
          const readyDeadline = performance.now() + study.measurement.timeout_ms;
          while (!(await execute("return [...document.querySelectorAll('button')].some(b => b.textContent.trim() === 'Record video')"))) {
            if (performance.now() > readyDeadline) throw new Error("上流の録画画面が準備できませんでした");
            await delay(50);
          }
          const installed = await command("/execute/async", { args: [mode, study.score, study.measurement, targetEngineFrame], script:
            `(${install})(...Array.from(arguments).slice(0, 4)).then(() => arguments[4]({}), e => arguments[4]({ error: String(e) }))` });
          if (installed.error) throw new Error(installed.error);
          const button = await command("/element", { using: "xpath", value: "//button[normalize-space(.)='Record video']" });
          await command(`/element/${button["element-6066-11e4-a52e-4f735466cecf"]}/click`, {});
          const stop = performance.now() + study.measurement.timeout_ms;
          do {
            Object.assign(report, await execute("return window.upstreamPauseRead()"));
            if (report.error || report.engineError) throw new Error(report.error ?? report.engineError);
            if (report.saved && report.hasPCM) break;
            await delay(50);
          } while (performance.now() < stop);
          if (!report.saved || !report.hasPCM) throw new Error("通常の保存リンクと加工前PCMの取得が完了しませんでした");
          report.wasmSha256 = createHash("sha256").update(Buffer.from(await (await fetch(report.wasm)).arrayBuffer())).digest("hex");
          for (const [media, name] of [[false, "worklet.f32le"], [true, "recording.mp4"]]) {
            const saved = await command("/execute/async", { args: [media], script: `
              const done = arguments[1];
              const blob = arguments[0]
                ? fetch([...document.querySelectorAll("a[download]")].find(a => a.textContent.trim() === "Save").href).then(r => r.blob())
                : Promise.resolve(window.upstreamPausePCM);
              blob.then(data => {
                const read = new FileReader();
                read.onload = () => done({ base64: read.result.slice(read.result.indexOf(";base64,") + 8), bytes: data.size });
                read.onerror = () => done({ error: String(read.error) });
                read.readAsDataURL(data);
              }).catch(e => done({ error: String(e) }));
            ` });
            if (saved.error) throw new Error(saved.error);
            const buffer = Buffer.from(saved.base64, "base64");
            if (!buffer.length || buffer.length !== saved.bytes) throw new Error(`転送した長さが一致しません (${name})`);
            writeFileSync(join(folder, name), buffer);
          }
        });
      } catch (error) {
        report.error = String(error);
      }
      writeFileSync(join(folder, "browser.json"), JSON.stringify(report, null, 2) + "\n");
    }
  }
} finally {
  await server.close();
}
