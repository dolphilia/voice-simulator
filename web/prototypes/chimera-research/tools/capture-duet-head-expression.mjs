import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { chromium } from "playwright-core";
import { preview } from "vite";
import { DuetHeadExpression, duetExpressionRandom, duetMouthPressure } from "../src/duet-head-expression.ts";

const [casePath, upstream, out] = process.argv.slice(2);
const spec = JSON.parse(readFileSync(casePath, "utf8"));
const { browser: options } = spec;
const rate = options.sample_rate_hz;
const root = fileURLToPath(new URL("../", import.meta.url));
const { Expression, mouthPressure } = await import(pathToFileURL(join(upstream, "src/ui/render/expression.ts")));
const fields = ["puff", "brow", "lid", "lookUp", "nod", "tilt"];
const nativeRandom = Math.random;
const controls = [];
let candidate, upper;
function reset() {
  Math.random = duetExpressionRandom(spec.seed);
  upper = new Expression();
  candidate = new DuetHeadExpression(duetExpressionRandom(spec.seed));
}
try {
  reset();
  for (const group of spec.controls) {
    if (group.reset) reset();
    const { f0 = 110, gate = 1, voicing = 1, outRms = 0.1, beatStep = -1, pressure_cmh2o = 0 } = group.source ?? {};
    const pressureRms = Float32Array.from([42, 19, 100000, 102000, pressure_cmh2o * spec.cg_per_cmh2o, 105000, 108000]);
    const tele = group.source && { nPh: 2, nOr: 5, beatStep, t: { pressureRms, f0, gate, voicing, outRms } };
    const pressure = duetMouthPressure(pressureRms, 2, 5);
    for (let i = 0; i < group.frames; i++) {
      const face = candidate.update(tele && { f0, gate, voicing, outRms, pressure, beatStep }, group.elapsed);
      upper.update(tele, Math.min(0.5, group.elapsed));
      const expected = Object.fromEntries(fields.map((key) => [key, upper[key]]));
      const upperState = { time: upper.clock, referencePitch: upper.ref, recentPitch: upper.fast, heldSeconds: upper.held,
        closure: upper.hold, lastBeat: upper.lastStep, motions: [upper.cheeks, upper.nodSpring, upper.tiltSpring].map(({ x, v }) => [x, v]) };
      controls.push({ group: group.name, face, expected, upperState, state: candidate.read(),
        pressure, upperPressure: tele ? mouthPressure(tele) : 0 });
    }
  }
} finally {
  Math.random = nativeRandom;
}
writeFileSync(join(out, "controlled-expression.json"), JSON.stringify(controls) + "\n");

function installObserver({ hop, minimumPuff }) {
  window.expressionTrace = [[], []];
  window.expressionPhotos = {};
  const canvases = () => [...document.querySelectorAll(".duet-heads canvas")];
  new MutationObserver(() => {
    for (const [i, canvas] of canvases().entries()) {
      let frame;
      canvas.dispatchEvent(new CustomEvent("chimera:read-duet-expression", { detail: (data) => { frame = data; } }));
      if (!frame || frame.tick === window.expressionTrace[i].at(-1)?.tick) continue;
      window.expressionTrace[i].push(frame);
      if (i !== 1 || !window.expressionPhotoArmed) continue;
      const sample = frame.index * hop;
      if (frame.clock.playing && !window.expressionPauseRequested && frame.face.puff >= minimumPuff) {
        window.expressionPauseRequested = true;
        document.querySelector("button").click();
      } else if (!frame.clock.playing && frame.expressive && window.expressionPauseRequested
          && !window.expressionPhotos.enabled) {
        window.expressionPhotos.enabled = { sample, tick: frame.tick, data: canvas.toDataURL() };
      } else if (!frame.clock.playing && !frame.expressive && sample === window.expressionPhotos.enabled?.sample
          && frame.clock.epoch === window.expressionPhotoEpoch) {
        window.expressionPhotos.disabled = { sample, tick: frame.tick, data: canvas.toDataURL() };
      }
    }
  }).observe(document, { attributes: true, attributeFilter: ["data-expression-tick"], subtree: true });
}

async function capture(browser, endpoint, width, height) {
  const page = await browser.newPage({ viewport: { width, height } });
  const markers = {};
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const withBeat = width === options.viewports.at(-1)[0];
  try {
    if (withBeat) {
      await page.route("**/shows/duet-clock/show.json", async (route) => {
        const response = await route.fetch();
        const data = await response.json();
        await route.fulfill({ response, json: { ...data, bpm: options.diagnostic_bpm, downbeat: options.diagnostic_downbeat_seconds } });
      });
    }
    await page.addInitScript(installObserver, { hop: 768, minimumPuff: options.minimum_cheek_peak });
    await page.goto(endpoint);
    await page.getByRole("link", { name: "デュエットの再生時計", exact: true }).click();
    await page.waitForFunction(() => window.expressionTrace?.every((frames) => frames.length));
    const slider = page.getByRole("slider", { name: "音源の位置", exact: true });
    const toggle = () => page.getByRole("button", { name: "再生", exact: true }).click();
    let epoch = 0;
    async function seek(sample) {
      await slider.evaluate((input, position) => {
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(input, String(position));
        input.dispatchEvent(new Event("input", { bubbles: true }));
      }, sample / rate);
      const next = ++epoch;
      await page.waitForFunction((target) => window.expressionTrace.every((trace) => trace.some((frame) => frame.clock.epoch === target)), next);
      return next;
    }
    const waitUntil = (sample) => page.waitForFunction(({ sample, rate, epoch }) =>
      window.expressionTrace.every((trace) => trace.some(({ clock }) => clock.playing && clock.epoch === epoch
        && clock.time >= sample / rate)), { sample, rate, epoch });
    markers.start = await seek(options.start_sample);
    await toggle();
    await waitUntil(options.live_until_sample);
    await page.getByRole("button", { name: "一時停止", exact: true }).click();
    await page.waitForFunction(() => window.expressionTrace.every((trace) => !trace.at(-1).clock.playing));
    markers.pause = await page.evaluate(() => window.expressionTrace.map((trace) => trace.at(-1).tick));
    await page.waitForTimeout(options.pause_ms);
    markers.settled = await page.evaluate(() => window.expressionTrace.map((trace) => trace.at(-1).tick));
    await toggle();
    markers.seeks = [];
    for (const sample of options.live_seeks) {
      markers.seeks.push(await seek(sample));
      await waitUntil(sample + 1200);
    }
    await page.getByRole("button", { name: "一時停止", exact: true }).click();
    await seek(29200);
    await page.evaluate(() => { window.expressionPhotoArmed = true; });
    await toggle();
    await page.waitForFunction(() => !!window.expressionPhotos.enabled);
    const picture = await page.evaluate(() => window.expressionPhotos.enabled.sample);
    await page.getByRole("checkbox", { name: "表情と頭部の動き", exact: true }).uncheck();
    await page.evaluate((next) => { window.expressionPhotoEpoch = next; }, epoch + 1);
    await seek(picture);
    const data = await page.evaluate(() => ({ trace: window.expressionTrace, photos: window.expressionPhotos }));
    for (const key of ["enabled", "disabled"]) {
      const photo = data.photos[key];
      if (!photo?.data.startsWith("data:image/png;base64,")) throw new Error(`${width}pxの${key}の画像を採取できません`);
      photo.path = `expression-${width}-${key}.png`;
      writeFileSync(join(out, photo.path), Buffer.from(photo.data.split(",")[1], "base64"));
      delete photo.data;
    }
    return { width, withBeat, markers, errors, ...data };
  } catch (error) {
    const trace = await page.evaluate(() => window.expressionTrace);
    writeFileSync(join(out, `expression-${width}-incomplete.json`), JSON.stringify({ trace, markers, errors }) + "\n");
    throw error;
  } finally {
    await page.close();
  }
}

const host = "127.0.0.1";
const server = await preview({ root, preview: { host, port: 0 } });
let browser;
const result = { viewports: [] };
try {
  browser = await chromium.launch({ headless: true, executablePath: process.env.CHIMERA_CHROMIUM,
    args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
  result.browser = browser.version();
  for (const [width, height] of options.viewports) {
    result.viewports.push(await capture(browser, `http://${host}:${server.httpServer.address().port}`, width, height));
  }
} finally {
  if (browser) await browser.close();
  await new Promise((resolve) => server.httpServer.close(resolve));
  writeFileSync(join(out, "browser-expression.json"), JSON.stringify(result) + "\n");
}
