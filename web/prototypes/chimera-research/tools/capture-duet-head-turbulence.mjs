import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { chromium } from "playwright-core";
import { preview } from "vite";
import { DuetTurbulence } from "../src/duet-head-turbulence.ts";
import { duetTractSections } from "../src/tract-3d-geometry.ts";

const [casePath, upstream, out, fixture, dist] = process.argv.slice(2);
const spec = JSON.parse(readFileSync(casePath, "utf8"));
const { browser: options } = spec;
const root = fileURLToPath(new URL("../", import.meta.url));
const showId = fixture ? spec.show_id : "duet-clock";
const assetRoot = fixture ?? join(root, "public", "shows", showId);
const write = (name, data) => writeFileSync(join(out, name), JSON.stringify(data) + "\n");
const upper = (path) => import(pathToFileURL(join(upstream, path)));
const { initChimera } = await upper("src/wasm/chimera.ts");
await initChimera(readFileSync(join(upstream, "target/wasm32-unknown-unknown/release/chimera_wasm.wasm")));
const { VoiceModel } = await upper("src/ui/analysis.ts");
const { Anatomy3D } = await upper("src/ui/render/anatomy3d.ts");
const { TeleTrack } = await upper("src/show/tele.ts");

function control() {
  const layout = { pharynx: { base: 4, cells: 4 }, oral: { base: 9, cells: 4 }, glottis_port: 19, sample_rate_hz: 48000 };
  const scale = 0.9;
  const glottis = [0.25, 0.15];
  const grid = [0.8, 1.8, 3.2, 4.5, 6.2, 7.05].map((s, i) => {
    const gap = [0.6, 1.3, 0.8, 0, 0.5, 0.45][i];
    return [0, i, i * 0.4, i + 0.55, i * 0.4 + 0.9, 0, 0, 1, gap, gap * 1.6, s];
  });
  const frame = { glottis: { x: glottis[0], y: glottis[1] }, grid: grid.map((r) => ({
    inner: { x: r[1], y: r[2] }, outer: { x: r[3], y: r[4] }, d: r[8], area: r[9], s: r[10],
  })) };
  const model = Object.assign(Object.create(VoiceModel.prototype), { model: { glottisPort: layout.glottis_port,
    pharynxBranches: { base: layout.pharynx.base, n: layout.pharynx.cells },
    oralBranches: { base: layout.oral.base, n: layout.oral.cells } } });
  const anatomy = new Anatomy3D();
  anatomy.k = scale;
  anatomy.beams.poly = () => {};
  anatomy.airway(model, frame, null, { pressure: false, grid: false }, scale);
  const candidate = new DuetTurbulence();
  const tract = { sections: duetTractSections(grid, scale), glottis, scale };
  const choices = [...spec.diagnostic.levels.map((level) => [layout.glottis_port, level]), [4, 80], [11, 100],
    [12, 400], [-1, 400], [19, 40]];
  try {
    const trace = choices.map(([noiseNode, noiseLevel]) => {
      const source = { phLen: 3, orLen: 4, noiseNode, noiseLevel };
      const upperSegments = [];
      anatomy.beams.seg = (x, y, z, tx, ty, tz, _color, _width, alpha) =>
        upperSegments.push({ from: [x, y, z], to: [tx, ty, tz], alpha });
      const upperBefore = anatomy.sparkSeed;
      anatomy.drawTurbulence(model, frame, { t: source });
      return { source, candidate: candidate.step(tract, layout, source), upperSegments,
        upperS: model.branchS(noiseNode, source.phLen, source.orLen), upperBefore, upperAfter: anatomy.sparkSeed };
    });
    write("controlled-turbulence.json", { layout, scale, glottis, grid, trace });
  } finally {
    anatomy.dispose();
  }
}

function recorded() {
  return [1, 2].map((voice) => {
    const bytes = readFileSync(join(assetRoot, "voice-" + voice + ".tele"));
    const track = new TeleTrack(Uint8Array.from(bytes).buffer);
    const model = new VoiceModel(track.body, track.sampleRate);
    try {
      const ph = model.model.pharynxBranches, or = model.model.oralBranches;
      const layout = { pharynx: { base: ph.base, cells: ph.n }, oral: { base: or.base, cells: or.n },
        glottis_port: model.model.glottisPort, sample_rate_hz: track.sampleRate };
      const frames = options.samples.map((sample) => {
        const index = track.indexAt(sample / track.sampleRate);
        const { t: { phLen, orLen, noiseLevel, noiseNode } } = track.message(index);
        return { sample, index, phLen, orLen, noiseLevel, noiseNode, s: model.branchS(noiseNode, phLen, orLen) };
      });
      const native = fixture ? JSON.parse(readFileSync(join(out, "upper-" + voice + "-noise.json"), "utf8")) : null;
      const nativeFrames = native?.rows.map(({ sample, phLen, orLen, noiseNode }) =>
        ({ sample, s: model.branchS(noiseNode, phLen, orLen) }));
      return { layout, frames, ...(nativeFrames ? { nativeFrames, body: track.body } : {}) };
    } finally {
      model.dispose();
    }
  });
}

function installObserver(includeBody) {
  function inspect(canvas, kind) {
    let value;
    canvas.dispatchEvent(new CustomEvent(`chimera:read-duet-${kind}`, { detail: (data) => { value = data; } }));
    return value;
  }
  window.readTurbulence = () => {
    const output = document.querySelector('output[aria-label="音源フレーム"]');
    const canvases = [...document.querySelectorAll(".duet-heads canvas")];
    const heads = canvases.map((canvas) => inspect(canvas, "turbulence"));
    if (!output || heads.length !== 2 || heads.some((head) => !head?.clock)) return undefined;
    const epoch = Number(output.dataset.epoch);
    if (!heads.every((head) => head.clock.epoch === epoch)) return undefined;
    for (const [index, head] of heads.entries()) {
      head.grid = inspect(canvases[index], "pressure").grid;
      if (includeBody) head.body = inspect(canvases[index], "head").body;
    }
    return { epoch, sample: Number(output.textContent), heads };
  };
  window.turbulenceEpochs = {};
  new MutationObserver(() => {
    const frame = window.readTurbulence();
    if (!frame) return;
    window.turbulenceEpochs[frame.epoch] ??= frame;
    if (frame.heads.every((h) => h.clock.playing)) window.firstPlayingTurbulence ??= frame;
  }).observe(document, { attributes: true, attributeFilter: ["data-head-epoch"], subtree: true });
}

async function capture(browser, url, width, height) {
  const page = await browser.newPage({ viewport: { width, height } });
  const evidence = { width, errors: [], paused: [], live: [] };
  page.on("pageerror", ({ message }) => evidence.errors.push(message));
  page.on("console", (item) => { if (item.type() === "error") evidence.errors.push(item.text()); });
  await page.addInitScript(installObserver, Boolean(fixture));
  try {
    if (fixture) {
      await page.goto(url + "/?show=" + showId);
    } else {
      await page.goto(url);
      await page.getByRole("link", { name: "デュエットの再生時計", exact: true }).click();
    }
    await page.waitForFunction(() => window.turbulenceEpochs[0]);
    for (const name of ["表情と頭部の動き", "気流の軌跡", "声道の圧力"]) {
      await page.getByRole("checkbox", { name, exact: true }).uncheck();
    }
    const slider = page.getByRole("slider", { name: "音源の位置" });
    const read = () => page.evaluate(() => window.readTurbulence());
    let epoch = 0;
    const seek = async (sample) => {
      await slider.evaluate((input, time) => {
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(input, String(time));
        input.dispatchEvent(new Event("input", { bubbles: true }));
      }, sample / options.sample_rate_hz);
      await page.waitForFunction((epoch) => window.turbulenceEpochs[epoch], ++epoch);
      return page.evaluate((epoch) => window.turbulenceEpochs[epoch], epoch);
    };
    for (const [index, sample] of options.samples.entries()) evidence.paused.push(index === 0 ? await read() : await seek(sample));
    await page.getByRole("button", { name: "再生", exact: true }).click();
    await page.waitForFunction(() => window.firstPlayingTurbulence);
    evidence.started = await page.evaluate(() => window.firstPlayingTurbulence);
    for (const sample of [...options.samples.filter((sample) => !options.live_seeks.includes(sample)), ...options.live_seeks]) {
      evidence.live.push({ target: sample, observed: await seek(sample) });
    }
    const toggle = page.getByRole("checkbox", { name: "乱流源", exact: true });
    await toggle.uncheck();
    evidence.hidden = await read();
    await toggle.check();
    evidence.restored = await read();
    await page.getByRole("button", { name: "一時停止", exact: true }).click();
    evidence.held = await read();
  } finally {
    write(`browser-turbulence-${width}.json`, evidence);
    await page.close();
  }
}

async function legacyAndInvalid(browser, url) {
  const checks = {};
  for (const mutation of fixture ? ["legacy", "rate", "swap"] : ["legacy", "rate"]) {
    const page = await browser.newPage();
    try {
      await page.addInitScript(installObserver);
      await page.route("**/shows/" + showId + "/show.json", async (route) => {
        const response = await route.fetch();
        const data = await response.json();
        if (mutation === "rate") data.voices[0].noise_branches.sample_rate_hz = 44100;
        else if (mutation === "swap") {
          const [first, second] = data.voices;
          [first.noise_branches, second.noise_branches] = [second.noise_branches, first.noise_branches];
        }
        else for (const voice of data.voices) delete voice.noise_branches;
        await route.fulfill({ response, json: data });
      });
      await page.goto(url + "/?show=" + showId);
      if (mutation !== "legacy") {
        checks[mutation === "rate" ? "badLayout" : "swappedBodies"] = await page.getByRole("alert").textContent();
      } else {
        await page.waitForFunction(() => window.turbulenceEpochs[0]);
        await page.getByRole("button", { name: "再生", exact: true }).click();
        await page.waitForFunction(() => window.firstPlayingTurbulence);
        const frame = await page.evaluate(() => window.firstPlayingTurbulence);
        const count = await page.getByRole("checkbox", { name: "乱流源", exact: true }).count();
        checks.legacyPlayback = count === 0 && frame.heads.every((h) => h.clock.playing && h.frame === null);
      }
    } finally {
      await page.close();
    }
  }
  return checks;
}

control();
write("recorded-turbulence.json", recorded());
const host = "127.0.0.1";
const server = await preview({ root, ...(dist ? { build: { outDir: dist } } : {}), preview: { host, port: 0 } });
let browser;
try {
  browser = await chromium.launch({ headless: true, executablePath: process.env.CHIMERA_CHROMIUM,
    args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
  const url = `http://${host}:${server.httpServer.address().port}`;
  const viewports = [];
  for (const [width, height] of options.viewports) {
    await capture(browser, url, width, height);
    viewports.push(`browser-turbulence-${width}.json`);
  }
  write("browser-turbulence.json", { browser: browser.version(), viewports, metadata: await legacyAndInvalid(browser, url) });
} finally {
  if (browser) await browser.close();
  await new Promise((resolve) => server.httpServer.close(resolve));
}
