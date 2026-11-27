import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { chromium } from "playwright-core";
import { preview } from "vite";

const [casePath, upstream, out] = process.argv.slice(2);
const spec = JSON.parse(readFileSync(casePath, "utf8"));
const rate = spec.sample_rate_hz;
const root = fileURLToPath(new URL("../", import.meta.url));
const host = "127.0.0.1";
const selector = ".duet-heads canvas";
const result = { errors: [], viewports: [] };

function installReadout({ selector }) {
  window.readDuetHeads = () => {
    const node = document.querySelector('output[aria-label="音源フレーム"]');
    const heads = [...document.querySelectorAll(selector)].map((canvas) => {
      let measured;
      canvas.dispatchEvent(new CustomEvent("chimera:read-duet-head", { detail: (value) => { measured = value; } }));
      return measured;
    });
    if (!node || heads.length !== 2 || heads.some((head) => !head)) return undefined;
    return { frame: Number(node.textContent), time: Number(node.dataset.time), epoch: Number(node.dataset.epoch), heads };
  };
  window.firstHeadEpochs = {};
  new MutationObserver(() => {
    const epoch = document.querySelector(`${selector}[data-head-epoch]`)?.dataset.headEpoch;
    if (epoch === undefined || window.firstHeadEpochs[epoch]) return;
    const snapshot = window.readDuetHeads();
    if (snapshot?.heads.every((head) => head.clock.epoch === snapshot.epoch)) {
      window.firstHeadEpochs[epoch] = snapshot;
    }
  }).observe(document, { attributes: true, attributeFilter: ["data-head-epoch"], subtree: true });
}

async function capture(endpoint, browser, width, height) {
  const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 2 });
  const log = { width, height, paused: [], live: [], held: [], screenshots: {} };
  page.on("pageerror", (error) => result.errors.push(error.message));
  await page.addInitScript(installReadout, { selector });
  try {
    await page.goto(endpoint);
    await page.getByRole("link", { name: "デュエットの再生時計", exact: true }).click();
    await page.waitForURL("**/?show=duet-clock");
    const slider = page.getByRole("slider", { name: "音源の位置", exact: true });
    const read = () => page.evaluate(() => window.readDuetHeads());
    let epoch = 0;
    const seek = async (sample) => {
      await slider.evaluate((input, at) => {
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(input, String(at));
        input.dispatchEvent(new Event("input", { bubbles: true }));
      }, sample / rate);
      await page.waitForFunction((target) => window.firstHeadEpochs[target] !== undefined, ++epoch);
    };
    await page.waitForFunction(() => window.firstHeadEpochs[0] !== undefined);
    await page.getByRole("checkbox", { name: "表情と頭部の動き", exact: true }).uncheck();
    const canvases = page.locator(selector);
    log.canvas = await canvases.evaluateAll((elements) => elements.map((canvas) => {
      const { x, y } = canvas.getBoundingClientRect();
      return { x, y, css: [canvas.clientWidth, canvas.clientHeight], pixels: [canvas.width, canvas.height] };
    }));
    for (const [step, at] of spec.paused_samples.entries()) {
      if (step > 0) await seek(at);
      log.paused.push(await read());
      if (spec.screenshot_samples.includes(at) && !log.screenshots[at]) {
        const names = [1, 2].map((voice) => `head-${width}-${at}-voice-${voice}.png`);
        for (const [i, name] of names.entries()) await canvases.nth(i).screenshot({ path: join(out, name) });
        log.screenshots[at] = names;
      }
    }

    await page.getByRole("button", { name: "再生", exact: true }).click();
    await page.waitForFunction(() => window.readDuetHeads()?.heads.every((head) => head.clock.playing));
    for (const sample of spec.live_seek_samples) {
      await seek(sample);
      const first = await page.evaluate((target) => window.firstHeadEpochs[target], epoch);
      await page.waitForFunction(({ time, epoch }) => {
        const output = document.querySelector('output[aria-label="音源フレーム"]');
        return Number(output.dataset.epoch) === epoch && Number(output.dataset.time) >= time;
      }, { epoch, time: (sample + spec.live_advance_samples) / rate });
      log.live.push({ requested: sample, first, advanced: await read() });
    }
    await page.getByRole("button", { name: "一時停止", exact: true }).click();
    log.held.push(await read());
    await page.waitForTimeout(100);
    log.held.push(await read());
  } finally {
    await page.close();
  }
  return log;
}

const server = await preview({ root, preview: { host, port: 0 } });
let browser;
try {
  browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHIMERA_CHROMIUM,
    args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
  });
  result.browser = browser.version();
  for (const [width, height] of spec.viewports) {
    result.viewports.push(await capture(`http://${host}:${server.httpServer.address().port}`, browser, width, height));
  }
} finally {
  if (browser) await browser.close();
  await new Promise((resolve) => server.httpServer.close(resolve));
}
writeFileSync(join(out, "browser-heads.json"), JSON.stringify(result) + "\n");

const upper = (path) => import(pathToFileURL(join(upstream, path)));
const { initChimera } = await upper("src/wasm/chimera.ts");
const upperWasm = readFileSync(join(upstream, "target/wasm32-unknown-unknown/release/chimera_wasm.wasm"));
await initChimera(upperWasm);
const { VoiceModel } = await upper("src/ui/analysis.ts");
const { ARTIC_KEYS, airwayFrame, airwayModel, dropAirwayModel } = await upper("src/wasm/engine.ts");
const { TeleTrack } = await upper("src/show/tele.ts");
const groups = [
  "outer", "inner", "tongue", "velum", "upperLip", "lowerLip", "upperTeeth", "lowerTeeth", "jawBone", "epiglottis", "nasalCavity",
];
const capturePaths = (shape) => Object.fromEntries(groups.map((name) => [
  name.replace(/[A-Z]/g, (part) => `_${part.toLowerCase()}`),
  shape[name].flatMap(({ x, y }) => [x, y]),
]));
const upperData = [1, 2].map((voice) => {
  const data = readFileSync(join(root, "public", "shows", "duet-clock", `voice-${voice}.tele`));
  const track = new TeleTrack(Uint8Array.from(data).buffer);
  const model = new VoiceModel(track.body, track.sampleRate);
  const rawModel = airwayModel(track.body, track.sampleRate);
  const rows = new Map();
  const poseAt = (index) => VoiceModel.articFromArray(track.message(index).t.artic);
  try {
    const clocks = result.viewports.flatMap(({ paused, live, held }) =>
      [...paused, ...live.flatMap(({ first, advanced }) => [first, advanced]), ...held].map(({ time }) => time));
    const selections = [...new Set(clocks)].map((time) => {
      const index = track.indexAt(time);
      if (!rows.has(index)) {
        const pose = poseAt(index);
        rows.set(index, { artic: ARTIC_KEYS.map((key) => pose[key]), paths: capturePaths(model.frame(pose)),
          rawPaths: capturePaths(airwayFrame(rawModel, pose)) });
      }
      return { time, index };
    });
    let cacheControl;
    if (voice === spec.cache_control.voice) {
      const order = spec.cache_control.rows;
      const poses = order.map(poseAt);
      const replay = (indices) => {
        const run = new VoiceModel(track.body, track.sampleRate);
        try { return indices.map((i) => capturePaths(run.frame(poseAt(i)))); }
        finally { run.dispose(); }
      };
      cacheControl = {
        rowKeys: poses.map((pose) => ARTIC_KEYS.map((key) => pose[key].toFixed(3)).join(",")),
        artic: poses.map((pose) => ARTIC_KEYS.map((key) => pose[key])),
        theoreticalPaths: poses.map((pose) => capturePaths(airwayFrame(rawModel, pose))),
        forward: replay(order),
        reverse: replay(order.toReversed()),
      };
    }
    return { body: track.body, hop: track.hop, frames: track.frames, selections, rows: Object.fromEntries(rows), cacheControl };
  } finally {
    model.dispose();
    dropAirwayModel(rawModel);
  }
});
writeFileSync(join(out, "upstream-heads.json"), JSON.stringify({ keys: ARTIC_KEYS, voices: upperData }) + "\n");
