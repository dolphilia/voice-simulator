// 固定上流の歌唱画面を操作し、録画と描画の証拠を保存する。
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { chromium } from "playwright-core";
import { createServer } from "vite";
import { trackRecorder } from "./observe-song-recorder.mjs";

const [out, casePath, upstream] = process.argv.slice(2);
const spec = JSON.parse(readFileSync(casePath, "utf8"));
const host = "127.0.0.1";

async function observeHead(settings) {
  const [{ engine }, { recording }, { Anatomy3D }, { useStore }, { useSing, roll, TUNES }] = await Promise.all([
    import("/src/audio/AudioEngine.ts"), import("/src/song/record.ts"), import("/src/ui/render/anatomy3d.ts"),
    import("/src/ui/store.ts"), import("/src/ui/singing.ts"),
  ]);
  const headCanvas = () => document.querySelector('.screen.left canvas[aria-label^="Vocal tract in 3D"]');
  const owners = new WeakMap();
  const origins = new Map();
  const owner = () => {
    const clip = recording.owner;
    if (!clip) return null;
    if (!owners.has(clip)) owners.set(clip, origins.size + 1);
    return owners.get(clip);
  };
  const head = [];
  const copies = [];
  const samples = [];
  const telemetry = [];
  const plans = [];
  const phase = {};
  const sampleCanvas = document.createElement("canvas");
  [sampleCanvas.width, sampleCanvas.height] = settings.frame_comparison_size_px;
  const small = sampleCanvas.getContext("2d", { willReadFrequently: true });
  let update;
  engine.onTelemetry(({ t, load }) => telemetry.push({
    owner: owner(), atMs: performance.now(), contextTime: engine.ctx.currentTime, rate: engine.sampleRate,
    clock: t.clock, f0: t.f0, voicing: t.voicing, outRms: t.outRms, load,
  }));
  engine.onPlanned((plan) => plans.push({
    ...plan, owner: owner(), atMs: performance.now(),
    notes: roll.notes.filter((note) => note.demo && note.t0 >= plan.t0).map((note) => ({ ...note })),
  }));
  const originalUpdate = Anatomy3D.prototype.update;
  Anatomy3D.prototype.update = function (...args) {
    const [, , , tele, view] = args;
    update = {
      owner: owner(), calipers: view.calipers, grid: view.grid,
      tele: tele && { clock: tele.t.clock, f0: tele.t.f0, voicing: tele.t.voicing, artic: Array.from(tele.t.artic) },
    };
    return originalUpdate.apply(this, args);
  };
  const draw = CanvasRenderingContext2D.prototype.drawImage;
  CanvasRenderingContext2D.prototype.drawImage = function (source, ...args) {
    draw.call(this, source, ...args);
    const face = headCanvas();
    if (this.canvas === face && update && args.length === 4 && source instanceof HTMLCanvasElement
        && args[2] === face.width && args[3] === face.height) {
      head.push({ ...update, atMs: performance.now(), readouts: [] });
      update = undefined;
    }
    const take = owner();
    if (!take || !face || source !== face || !head.length || this.canvas.width !== 720 || this.canvas.height !== 1280) return;
    const now = performance.now();
    if (!origins.has(take)) origins.set(take, { atMs: now, voiceClock: engine.voiceClock(), contextTime: engine.ctx?.currentTime });
    const elapsed = (now - origins.get(take).atMs) / 1000;
    const item = { take, head: head.length - 1, elapsed, source: [face.width, face.height], placement: args };
    copies.push(item);
    const next = settings.frame_sample_seconds[samples.length];
    if (take === 1 && next !== undefined && elapsed >= next) {
      draw.call(small, this.canvas, 0, 0, sampleCanvas.width, sampleCanvas.height);
      samples.push({ ...item, rgba: btoa(String.fromCharCode(...small.getImageData(0, 0, sampleCanvas.width, sampleCanvas.height).data)) });
    }
  };
  const fill = CanvasRenderingContext2D.prototype.fillText;
  CanvasRenderingContext2D.prototype.fillText = function (value, ...args) {
    fill.call(this, value, ...args);
    if (head.length && this.canvas === headCanvas() && /^(F[123]|RING (ON|OFF)|NOTE )/.test(value)) {
      head.at(-1).readouts.push(value);
    }
  };
  window.headProbe = {
    head, copies, samples, telemetry, plans, phase,
    mark(name) {
      phase[name] = { headFrames: head.length, owner: owner(), atMs: performance.now(),
        voiceClock: engine.voiceClock(), contextTime: engine.ctx?.currentTime };
    },
    report() {
      const { mode, body, view } = useStore.getState();
      const { tune, tempo, lyrics, key } = useSing.getState();
      return { head, copies, samples, telemetry, plans, phase, origins: [...origins],
        input: { mode, body, view, tune, tempo, lyrics, key }, tune: TUNES.find((entry) => entry.id === tune),
        engineError: engine.error, recorder: window.inspectRecording() };
    },
  };
}

const server = await createServer({ root: upstream, server: { host, port: 0, hmr: false, watch: null } });
let browser, page;
const errors = [];
const warnings = [];
const wasmRequests = [];
try {
  await server.listen();
  browser = await chromium.launch({ headless: true, executablePath: process.env.CHIMERA_CHROMIUM,
    args: process.env.CHIMERA_RECORDING_GRAPHICS === "native" ? [] : ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
  page = await browser.newPage({ acceptDownloads: true, viewport: { width: spec.input.viewport_width_css_px, height: 1000 } });
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (msg) => { if (["error", "warning"].includes(msg.type())) warnings.push(msg.text()); });
  page.on("response", (response) => {
    const { pathname, search } = new URL(response.url());
    if (pathname.endsWith("/chimera.wasm")) wasmRequests.push({
      path: pathname + search, type: response.headers()["content-type"],
    });
  });
  await page.addInitScript(trackRecorder, { observeClipDraws: true });
  const [servedWasm] = await Promise.all([
    // Viteは同じパスからURLを返すJSモジュールとWASM本体を配信する。
    page.waitForResponse((response) => response.ok() && new URL(response.url()).pathname.endsWith("/chimera.wasm")
      && response.headers()["content-type"]?.startsWith("application/wasm")),
    page.goto(`http://${host}:${server.httpServer.address().port}/`),
  ]);
  const wasmSha256 = createHash("sha256").update(await servedWasm.body()).digest("hex");
  await page.getByRole("radio", { name: "Sing", exact: true }).click();
  await page.getByRole("radio", { name: "Male", exact: true }).click();
  await page.getByRole("combobox", { name: "Tune", exact: true }).selectOption(spec.input.upstream_tune);
  await page.getByRole("textbox", { name: "Lyrics to sing" }).fill(spec.input.lyrics);
  await page.evaluate(observeHead, spec.measurement);
  await page.getByRole("checkbox", { name: "Measurements", exact: true }).check();
  await page.getByRole("checkbox", { name: "Grid", exact: true }).check();
  await page.getByRole("checkbox", { name: "3D", exact: true }).check();
  const record = page.getByRole("button", { name: "Record video", exact: true });
  const cancel = page.getByRole("button", { name: "Cancel", exact: true });
  const save = page.getByRole("link", { name: "Save", exact: true });
  const mark = (name) => page.evaluate((label) => window.headProbe.mark(label), name);
  const readouts = (phase) => page.waitForFunction((label) =>
    window.headProbe.head.slice(window.headProbe.phase[label]?.headFrames ?? 0).slice(-10)
      .some((row) => row.owner === null && row.calipers && row.grid && row.readouts.includes("F1")), phase);
  await readouts("before");
  await mark("before");
  await record.click();
  await save.waitFor({ timeout: 60000 });
  const [download] = await Promise.all([page.waitForEvent("download"), save.click()]);
  const filename = download.suggestedFilename();
  await download.saveAs(join(out, filename));
  await mark("finished");
  await readouts("finished");
  await mark("restored");
  await record.click();
  await page.waitForFunction((seconds) => window.headProbe.copies.some((row) => row.take === 2 && row.elapsed >= seconds),
    spec.measurement.cancel_after_seconds);
  await mark("beforeCancel");
  await cancel.click();
  await record.waitFor();
  await page.waitForFunction(() => window.inspectRecording().takes[1]?.stopped !== null);
  await mark("cancelled");
  await readouts("cancelled");
  const result = await page.evaluate(() => window.headProbe.report());
  writeFileSync(join(out, "head-recording-browser.json"), JSON.stringify({
    browser: browser.version(), wasmSha256, wasmRequests, filename, cancelledWithoutFile: await save.count() === 0,
    errors, warnings, ...result,
  }) + "\n");
} catch (error) {
  const partial = await page?.evaluate(() => window.headProbe?.report()).catch(() => null);
  writeFileSync(join(out, "head-recording-failure.json"), JSON.stringify({ error: String(error), wasmRequests, errors, warnings, partial }) + "\n");
  throw error;
} finally {
  await browser?.close();
  await server.close();
}
