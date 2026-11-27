import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { chromium } from "playwright-core";
import { preview } from "vite";
import { DuetAirflow } from "../src/duet-head-airflow.ts";
import { duetExpressionRandom } from "../src/duet-head-expression.ts";
import { duetTractSections } from "../src/tract-3d-geometry.ts";

const [casePath, upstream, out] = process.argv.slice(2);
const spec = JSON.parse(readFileSync(casePath, "utf8"));
const { browser: options, diagnostic } = spec;
const root = fileURLToPath(new URL("../", import.meta.url));
const write = (name, data) => writeFileSync(join(out, name), JSON.stringify(data) + "\n");
const upper = (path) => import(pathToFileURL(join(upstream, path)));
const { initChimera } = await upper("src/wasm/chimera.ts");
await initChimera(readFileSync(join(upstream, "target/wasm32-unknown-unknown/release/chimera_wasm.wasm")));
const { VoiceModel } = await upper("src/ui/analysis.ts");

async function recorded() {
  const { airwayModel, airwayFrame, dropAirwayModel } = await upper("src/wasm/engine.ts");
  const { TeleTrack } = await upper("src/show/tele.ts");
  return [1, 2].map((voice) => {
    const bytes = readFileSync(join(root, "public", "shows", "duet-clock", `voice-${voice}.tele`));
    const track = new TeleTrack(Uint8Array.from(bytes).buffer);
    const model = airwayModel(track.body, track.sampleRate);
    try {
      return options.samples.map((sample) => {
        const index = track.indexAt(sample / track.sampleRate);
        const { t } = track.message(index);
        const geometry = airwayFrame(model, VoiceModel.articFromArray(t.artic));
        return { sample, index, flow: Array.from(t.flow), areas: [...t.phAreas, ...t.orAreas],
          glottis: [geometry.glottis.x, geometry.glottis.y], lipS: geometry.lipS };
      });
    } finally {
      dropAirwayModel(model);
    }
  });
}

async function controlled() {
  const { Anatomy3D } = await upper("src/ui/render/anatomy3d.ts");
  const { n_pharynx: nPh, n_oral: nOr, lengths_cm: [phLen, orLen], areas_cm2, flow_cm3_s, start_distances_cm } = diagnostic;
  const input = { nPh, nOr, phLen, orLen, phAreas: Float32Array.from(areas_cm2.slice(0, nPh)),
    orAreas: Float32Array.from(areas_cm2.slice(nPh)), flow: Float32Array.from(flow_cm3_s) };
  const scale = 0.9;
  const glottis = [0.4, 0.2];
  const grid = [0.8, 1.3, 3, 4.1, 5, 6.1].map((s, i) => {
    const gap = [0.7, 1.4, 0, 0.2, 0.01, 0.5][i];
    return [0, i, 0.2 * i, i + (i < 3 ? 0.4 : -0.5), 0.2 * i + 0.8, 0, 0, 1, gap, 2 * gap, s];
  });
  const initial = [...start_distances_cm, 1.5, -0.1, 6.13].map((s, i) => ({
    s, u: (i % 2 ? -1 : 1) * 0.45, v: 0.65, life: i === 4 ? 0.001 : 0.85, previous: null,
  }));
  const [zero, short, long] = diagnostic.elapsed_seconds;
  const steps = [{ elapsed: zero }, { elapsed: short }, { elapsed: long, paused: true }, { elapsed: short },
    { elapsed: long }, { elapsed: short, reset: true }, { elapsed: short }];
  const tract = { sections: duetTractSections(grid, scale), glottis, scale };
  const seed = spec.dynamics.initial_random_seed;
  const candidate = new DuetAirflow(duetExpressionRandom(seed), initial);
  const reference = new Anatomy3D();
  const model = Object.assign(Object.create(VoiceModel.prototype), { nPh, nOr });
  const frame = { glottis: { x: glottis[0], y: glottis[1] }, lipS: grid.at(-1)[10], grid: grid.map((r) => ({
    inner: { x: r[1], y: r[2] }, outer: { x: r[3], y: r[4] }, d: r[8], area: r[9], s: r[10],
  })) };
  reference.k = scale;
  reference.beams.poly = () => {};
  reference.airway(model, frame, null, { pressure: false, grid: false }, scale);
  reference.particles = initial.map(({ s, u, v, life }) => ({ s, u, v, life, px: NaN, py: NaN, pz: NaN }));
  const originalRandom = Math.random;
  let segments;
  reference.beams.seg = (x, y, z, a, b, c, _color, _width, alpha) => {
    segments.push({ from: [x, y, z], to: [a, b, c], alpha });
  };
  try {
    Math.random = duetExpressionRandom(seed);
    const trace = steps.map((step) => {
      if (step.reset) {
        candidate.resetTrails();
        reference.resetMotion();
      }
      segments = [];
      const draw = step.paused ? null : candidate.step(tract, input, step.elapsed);
      if (!step.paused) reference.drawParticles(model, frame, { t: input }, Math.min(0.05, step.elapsed));
      const states = reference.particles.map(({ s, u, v, life, px, py, pz }) => ({
        s, u, v, life, previous: Number.isFinite(px) ? [px, py, pz] : null,
      }));
      return { ...step, draw: draw && { ...draw, nodes: Array.from(draw.nodes) }, candidate: candidate.snapshot(),
        upstreamParticles: states, upstreamSegments: segments };
    });
    write("controlled-airflow.json", { glottis, scale, grid, initial, trace });
  } finally {
    Math.random = originalRandom;
    reference.dispose();
  }
}

function installReadout() {
  window.airflowRead = () => {
    const output = document.querySelector('output[aria-label="音源フレーム"]');
    const heads = [...document.querySelectorAll(".duet-heads canvas")].map((canvas) => {
      let data;
      canvas.dispatchEvent(new CustomEvent("chimera:read-duet-airflow", { detail: (frame) => { data = frame; } }));
      return data;
    });
    if (!output || heads.length !== 2 || heads.some((head) => !head)) return undefined;
    const epoch = Number(output.dataset.epoch);
    if (!heads.every((head) => head.clock.epoch === epoch)) return undefined;
    return { epoch, sample: Number(output.textContent), heads };
  };
  window.airflowFrames = [];
  new MutationObserver(() => {
    const frame = window.airflowRead();
    if (frame) window.airflowFrames.push(frame);
  }).observe(document, { attributes: true, attributeFilter: ["data-head-epoch"], subtree: true });
}

async function capture(browser, url, width, height) {
  const page = await browser.newPage({ viewport: { width, height } });
  const result = { width, height, errors: [], paused: [], live: [] };
  page.on("pageerror", ({ message }) => result.errors.push(message));
  await page.addInitScript(installReadout);
  try {
    await page.goto(url);
    await page.getByRole("link", { name: "デュエットの再生時計", exact: true }).click();
    await page.waitForFunction(() => window.airflowFrames.length);
    await page.getByRole("checkbox", { name: "表情と頭部の動き" }).uncheck();
    const slider = page.getByRole("slider", { name: "音源の位置" });
    const read = () => page.evaluate(() => window.airflowRead());
    const count = () => page.evaluate(() => window.airflowFrames.length);
    let epoch = 0;
    const waitEpoch = async (target, amount) => {
      await page.waitForFunction(([target, amount]) => window.airflowFrames.filter((item) => item.epoch === target).length >= amount,
        [target, amount]);
      return page.evaluate(([target, amount]) => window.airflowFrames.filter((item) => item.epoch === target).slice(0, amount),
        [target, amount]);
    };
    const seek = async (sample, amount) => {
      await slider.evaluate((input, value) => {
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(input, String(value));
        input.dispatchEvent(new Event("input", { bubbles: true }));
      }, sample / options.sample_rate_hz);
      return waitEpoch(++epoch, amount);
    };
    const play = async () => {
      const start = await count();
      await page.getByRole("button", { name: "再生", exact: true }).click();
      await page.waitForFunction((start) => window.airflowFrames.slice(start).some((frame) => frame.heads.every((h) => h.clock.playing)), start);
      return page.evaluate((start) => window.airflowFrames.slice(start).find((frame) => frame.heads.every((h) => h.clock.playing)), start);
    };
    for (const [i, sample] of options.samples.entries()) result.paused.push(i === 0 ? await read() : (await seek(sample, 1))[0]);
    result.started = await play();
    for (const sample of options.live_seeks) result.live.push({ target: sample, frames: await seek(sample, 2) });
    await page.getByRole("button", { name: "一時停止", exact: true }).click();
    result.held = [await read()];
    await page.waitForTimeout(options.hold_ms);
    result.held.push(await read());
    result.resumed = await play();
    const toggle = page.getByRole("checkbox", { name: "気流の軌跡", exact: true });
    await toggle.uncheck();
    result.hidden = await read();
    const first = await count();
    await toggle.check();
    await page.waitForFunction((index) => window.airflowFrames.slice(index).some((frame) => frame.heads.every((h) => h.enabled)), first);
    result.restored = await page.evaluate((index) => window.airflowFrames.slice(index).find((frame) => frame.heads.every((h) => h.enabled)), first);
    return result;
  } finally {
    write(`browser-airflow-${width}.json`, result);
    await page.close();
  }
}

await controlled();
write("recorded-airflow.json", await recorded());
const host = "127.0.0.1";
const server = await preview({ root, preview: { host, port: 0 } });
let browser;
try {
  browser = await chromium.launch({ headless: true, executablePath: process.env.CHIMERA_CHROMIUM,
    args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
  const url = `http://${host}:${server.httpServer.address().port}`;
  const viewports = [];
  for (const [width, height] of options.viewports) {
    await capture(browser, url, width, height);
    viewports.push(`browser-airflow-${width}.json`);
  }
  write("browser-airflow.json", { browser: browser.version(), viewports });
} finally {
  if (browser) await browser.close();
  await new Promise((resolve) => server.httpServer.close(resolve));
}
