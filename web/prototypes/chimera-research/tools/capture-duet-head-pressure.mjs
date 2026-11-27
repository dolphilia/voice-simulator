import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { chromium } from "playwright-core";
import { Vector3 } from "three";
import { preview } from "vite";
import { duetPressureColor, duetPressureLevel, duetPressureNodes, duetPressureRings,
  duetPressureStyle } from "../src/duet-head-pressure.ts";

const [casePath, upstream, out] = process.argv.slice(2);
const spec = JSON.parse(readFileSync(casePath, "utf8"));
const { browser: options } = spec;
const root = fileURLToPath(new URL("../", import.meta.url));
const selector = ".duet-heads canvas";
const rate = options.sample_rate_hz;

function installReadout({ selector, photoSample, photoVoice }) {
  const canvases = () => [...document.querySelectorAll(selector)];
  window.readPressure = () => {
    const output = document.querySelector('output[aria-label="音源フレーム"]');
    const heads = canvases().map((canvas) => {
      let data;
      canvas.dispatchEvent(new CustomEvent("chimera:read-duet-pressure", { detail: (value) => { data = value; } }));
      return data;
    });
    if (!output || heads.length !== 2 || heads.some((head) => !head)) return undefined;
    const epoch = Number(output.dataset.epoch);
    if (!heads.every((head) => head.clock.epoch === epoch)) return undefined;
    return { sample: Number(output.textContent), epoch, heads };
  };
  window.firstPressureEpochs = {};
  window.pressurePhotos = {};
  new MutationObserver(() => {
    const state = window.readPressure();
    if (!state) return;
    const playing = state.heads.every((head) => head.clock.playing);
    if (playing && !window.firstPlayingPressure) window.firstPlayingPressure = state;
    if (state.sample === photoSample) {
      const voice = state.heads[photoVoice - 1];
      const kind = playing ? "playing" : voice.rings.length > 0 ? "paused" : "hidden";
      window.pressurePhotos[kind] ??= canvases()[photoVoice - 1].toDataURL();
    }
    if (window.firstPressureEpochs[state.epoch]) return;
    window.firstPressureEpochs[state.epoch] = state;
  }).observe(document, { attributes: true, attributeFilter: ["data-head-epoch"], subtree: true });
}

async function capture(browser, url, width, height) {
  const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
  const evidence = { width, height, errors: [], paused: [], live: [], photos: {} };
  page.on("pageerror", ({ message }) => evidence.errors.push(message));
  await page.addInitScript(installReadout, { selector, photoSample: options.photo_sample, photoVoice: options.photo_voice });
  try {
    await page.goto(url);
    await page.getByRole("link", { name: "デュエットの再生時計", exact: true }).click();
    await page.waitForFunction(() => window.firstPressureEpochs[0]);
    await page.getByRole("checkbox", { name: "表情と頭部の動き" }).uncheck();
    const turbulence = page.getByRole("checkbox", { name: "乱流源", exact: true });
    if (await turbulence.count()) await turbulence.uncheck();
    const slider = page.getByRole("slider", { name: "音源の位置" });
    const read = () => page.evaluate(() => window.readPressure());
    let epoch = 0;
    const seek = async (sample) => {
      await slider.evaluate((input, seconds) => {
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(input, String(seconds));
        input.dispatchEvent(new Event("input", { bubbles: true }));
      }, sample / rate);
      return page.evaluate((target) => window.firstPressureEpochs[target], ++epoch);
    };
    const exact = async (sample) => {
      const first = await seek(sample);
      if (first) return first;
      await page.waitForFunction((target) => window.firstPressureEpochs[target], epoch);
      return page.evaluate((target) => window.firstPressureEpochs[target], epoch);
    };
    for (const [step, sample] of spec.samples.entries()) {
      evidence.paused.push(step === 0 ? await read() : await exact(sample));
    }
    await page.getByRole("button", { name: "再生", exact: true }).click();
    await page.waitForFunction(() => window.firstPlayingPressure);
    evidence.started = await page.evaluate(() => window.firstPlayingPressure);
    for (const sample of options.live_seeks) evidence.live.push(await exact(sample));
    await page.getByRole("button", { name: "一時停止", exact: true }).click();
    evidence.held = [await read()];
    await page.waitForTimeout(options.hold_ms);
    evidence.held.push(await read());
    // 一時停止直後が比較位置と一致した場合も、実際に入力値が変わるようにする。
    await exact(options.live_seeks[0]);
    await exact(options.photo_sample);
    const toggle = page.getByRole("checkbox", { name: "声道の圧力" });
    await toggle.uncheck();
    evidence.hidden = await read();
    await toggle.check();
    evidence.restored = await read();
    const photos = await page.evaluate(() => window.pressurePhotos);
    for (const kind of ["paused", "playing", "hidden"]) {
      const png = photos[kind];
      if (!png?.startsWith("data:image/png;base64,")) throw new Error(`${width}pxの画像を採取できません (${kind})`);
      const name = `pressure-${width}-${kind}.png`;
      evidence.photos[kind] = name;
      writeFileSync(join(out, name), Buffer.from(png.split(",")[1], "base64"));
    }
    return evidence;
  } finally {
    writeFileSync(join(out, `browser-pressure-${width}.json`), JSON.stringify(evidence) + "\n");
    await page.close();
  }
}

const server = await preview({ root, preview: { host: "127.0.0.1", port: 0 } });
let browser;
const logs = [];
try {
  browser = await chromium.launch({ headless: true, executablePath: process.env.CHIMERA_CHROMIUM,
    args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
  const url = `http://127.0.0.1:${server.httpServer.address().port}`;
  for (const [width, height] of options.viewports) logs.push(await capture(browser, url, width, height));
  writeFileSync(join(out, "browser-pressure.json"), JSON.stringify({ browser: browser.version(), viewports: logs }) + "\n");
} finally {
  if (browser) await browser.close();
  await new Promise((resolve) => server.httpServer.close(resolve));
}

const upper = (path) => import(pathToFileURL(join(upstream, path)));
const { initChimera } = await upper("src/wasm/chimera.ts");
await initChimera(readFileSync(join(upstream, "target/wasm32-unknown-unknown/release/chimera_wasm.wasm")));
const { VoiceModel } = await upper("src/ui/analysis.ts");
const { Anatomy3D } = await upper("src/ui/render/anatomy3d.ts");
const { TeleTrack } = await upper("src/show/tele.ts");
const { heat, pressureLevel } = await upper("src/ui/colors.ts");
const { ARTIC_KEYS, airwayModel, airwayFrame, dropAirwayModel } = await upper("src/wasm/engine.ts");

function upperRings(model, frame, tele, eye, scale) {
  const anatomy = new Anatomy3D();
  const captured = [];
  anatomy.eye.fromArray(eye);
  anatomy.beams.poly = (poly, color, width, { alpha }) => {
    if (width === 0.85) captured.push({ color: parseInt(color.slice(1), 16), opacity: alpha,
      vertices: Array.from(poly.a.subarray(0, poly.n * 3)) });
  };
  try {
    anatomy.airway(model, frame, tele, { pressure: true, grid: false }, scale);
    return captured;
  } finally {
    anatomy.dispose();
  }
}

const sharedFrame = (grid) => ({ glottis: { x: 0, y: 0 }, grid: grid.map((r) => ({
  inner: { x: r[1], y: r[2] }, outer: { x: r[3], y: r[4] }, d: r[8], area: r[9], s: r[10],
})) });
const readGrid = (frame) => frame.grid.map(({ inner, outer, d, area, s }) => [inner.x, inner.y, outer.x, outer.y, d, area, s]);
const diagnostic = spec.diagnostic;
const inputs = { nPh: diagnostic.n_pharynx, nOr: diagnostic.n_oral,
  phLen: diagnostic.lengths_cm[0], orLen: diagnostic.lengths_cm[1], pressureRms: diagnostic.pressure_dyn_cm2 };
const diagnosticGrid = diagnostic.distances_cm.map((s, i) =>
  [0, i, 0, i + (i === 4 ? 0 : i < 4 ? 1 : -1), 0, i, 0, i === 4 ? 0 : 1,
    diagnostic.gaps_cm[i], diagnostic.areas_cm2[i], s]);
const diagnosticModel = Object.assign(Object.create(VoiceModel.prototype), { nPh: inputs.nPh, nOr: inputs.nOr });
const nodes = duetPressureNodes(inputs);
const control = {
  grid: diagnosticGrid, nodes: Array.from(nodes), upperNodes: Array.from(diagnosticModel.nodeS(inputs.phLen, inputs.orLen)),
  rings: duetPressureRings(diagnosticGrid, diagnostic.body_scale).map((ring) => ({ row: ring.index,
    ...duetPressureStyle(ring, new Vector3(...diagnostic.eye), inputs, nodes), vertices: Array.from(Float32Array.from(ring.vertices)) })),
  upper: upperRings(diagnosticModel, sharedFrame(diagnosticGrid), { t: inputs }, diagnostic.eye, diagnostic.body_scale),
  palette: [0, ...diagnostic.pressure_dyn_cm2, 8000].map((rms) => {
    const level = duetPressureLevel(rms), upperLevel = pressureLevel(rms) ** 0.85;
    return { rms, level, upperLevel, color: duetPressureColor(level), upperColor: parseInt(heat(upperLevel).slice(1), 16) };
  }),
};
const voices = [1, 2].map((voice) => {
  const data = readFileSync(join(root, "public", "shows", "duet-clock", `voice-${voice}.tele`));
  const track = new TeleTrack(Uint8Array.from(data).buffer);
  const model = new VoiceModel(track.body, track.sampleRate);
  const rawModel = airwayModel(track.body, track.sampleRate);
  try {
    return spec.samples.map((sample, index) => {
      const head = logs[0].paused[index].heads[voice - 1];
      const row = track.indexAt(sample / rate);
      const tele = track.message(row);
      const artic = VoiceModel.articFromArray(tele.t.artic);
      const frame = model.frame(artic);
      const bodyScale = model.tract.scale;
      return { sample, row, bodyScale, nodes: Array.from(model.nodeS(tele.t.phLen, tele.t.orLen)),
        grid: readGrid(frame), rawGrid: readGrid(airwayFrame(rawModel, artic)),
        cacheKey: ARTIC_KEYS.map((key) => artic[key].toFixed(3)).join(","),
        actual: upperRings(model, frame, tele, head.eye, bodyScale),
        shared: upperRings(model, sharedFrame(head.grid), tele, head.eye, head.scale) };
    });
  } finally {
    model.dispose();
    dropAirwayModel(rawModel);
  }
});
writeFileSync(join(out, "upstream-pressure.json"), JSON.stringify({ control, voices }) + "\n");
