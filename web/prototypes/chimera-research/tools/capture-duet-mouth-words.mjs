import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { chromium } from "playwright-core";
import { preview } from "vite";
import { DuetMouthTrail } from "../src/duet-mouth-words.ts";

const [casePath, upstream, out, reference] = process.argv.slice(2);
const spec = JSON.parse(readFileSync(casePath, "utf8"));
const root = fileURLToPath(new URL("../", import.meta.url));
const rate = spec.sample_rate_hz;
const host = "127.0.0.1";
const run = { errors: [], viewports: [] };

function setupReadout() {
  const measure = document.createElement("canvas").getContext("2d");
  window.readMouth = () => {
    const output = document.querySelector('output[aria-label="音源フレーム"]');
    const heads = [...document.querySelectorAll(".duet-heads figure")].map((figure) => {
      const canvas = figure.querySelector("canvas");
      const layer = figure.querySelector(".duet-mouth-words");
      let shape, overlay, matrix;
      canvas.dispatchEvent(new CustomEvent("chimera:read-duet-head", { detail: (value) => { shape = value; } }));
      canvas.dispatchEvent(new CustomEvent("chimera:read-duet-expression", { detail: ({ mesh }) => { matrix = mesh.model; } }));
      layer.dispatchEvent(new CustomEvent("chimera:read-duet-mouth", { detail: (value) => { overlay = value; } }));
      if (!shape || !overlay) return null;
      const box = layer.getBoundingClientRect();
      const baseSize = Math.max(26, Math.min(64, overlay.view.pxPerCm * 1.7));
      measure.font = `600 ${baseSize}px system-ui`;
      const labels = [...layer.querySelectorAll(".duet-mouth-word")].map((label) => {
        const rect = label.getBoundingClientRect();
        return { text: label.textContent, key: +label.dataset.wordKey, departing: label.dataset.departing === "true",
          x: parseFloat(label.style.left), y: parseFloat(label.style.top), alpha: +label.style.opacity,
          size: parseFloat(label.style.fontSize), bounds: [rect.left - box.left, rect.top - box.top,
            rect.right - box.left, rect.bottom - box.top], baseWidth: measure.measureText(label.textContent).width };
      });
      const { lipRims, facing, projection, view } = shape.geometry;
      return { index: shape.index, clock: shape.clock, facing, projection, view, model: matrix, lipCenters:
        lipRims.map((rim) => rim.slice(48, 51)), css: [canvas.clientWidth, canvas.clientHeight],
        guide: !layer.querySelector(".duet-mouth-guide").hidden, overlay, labels };
    });
    if (!output || heads.length !== 2 || heads.some((head) => head === null)) return;
    return { sample: +output.textContent, time: +output.dataset.time, epoch: +output.dataset.epoch, heads,
      table: [...document.querySelectorAll(".duet-lyrics dd")].map((element) => element.dataset.wordKey === undefined
        ? null : { key: +element.dataset.wordKey, text: element.textContent }) };
  };
  window.firstMouthEpoch = {};
  window.liveMouthFrames = [];
  window.liveMouthMatches = {};
  new MutationObserver(() => {
    const canvases = document.querySelectorAll(".duet-heads canvas[data-head-epoch]");
    const epoch = canvases[0]?.dataset.headEpoch;
    if (epoch === undefined) return;
    const watch = window.liveMouthWatch;
    if (watch?.epoch === Number(epoch)) {
      const output = document.querySelector('output[aria-label="音源フレーム"]');
      const sample = Number(output?.textContent);
      const spoken = [...document.querySelectorAll(".duet-heads figure:first-child .duet-mouth-word")].map((label) => ({
        key: Number(label.dataset.wordKey), departing: label.dataset.departing === "true",
      }));
      window.liveMouthFrames.push({ sample, spoken });
      if (sample >= watch.melisma && spoken.some((word) => word.key === 0 && !word.departing)) remember("melisma");
      if (sample >= watch.rest && spoken.some((word) => word.key === 0 && word.departing)) remember("rest");
      if (sample >= watch.rest_faded && !spoken.length) remember("restFaded");
      if (sample >= watch.repeat && spoken.some((word) => word.key === 2 && !word.departing)) remember("repeat");
      if (sample >= watch.following && spoken.some((word) => word.key === 3 && !word.departing)
          && spoken.some((word) => word.key === 2 && word.departing)) remember("following");
    }
    if (window.firstMouthEpoch[epoch]) return;
    const snapshot = window.readMouth();
    if (snapshot?.heads.every((head) => head.clock.epoch === snapshot.epoch)) {
      window.firstMouthEpoch[epoch] = snapshot;
    }
  }).observe(document, { attributes: true, attributeFilter: ["data-head-epoch"], subtree: true });

  function remember(key) {
    if (window.liveMouthMatches[key]) return;
    const snapshot = window.readMouth();
    if (snapshot?.heads.every((head) => head.clock.playing)) window.liveMouthMatches[key] = snapshot;
  }
}

async function installDiagnostic(page) {
  const local = (name) => join(reference, "diagnostic", name);
  const show = JSON.parse(readFileSync(local("show.json"), "utf8"));
  show.voices.forEach((voice, i) => { voice.tele = `voice-${i + 1}.tele`; });
  await page.route("**/shows/duet-mouth-diagnostic/*", (route) => {
    const name = new URL(route.request().url()).pathname.split("/").at(-1);
    if (name === "show.json") return route.fulfill({ json: show });
    const isTele = name.endsWith(".tele");
    const source = isTele ? join(root, "public", "shows", "duet-clock", name) : local(name);
    return route.fulfill({ path: source });
  });
}

async function capture(browser, endpoint, viewport, scene) {
  const page = await browser.newPage({ viewport });
  page.on("pageerror", (error) => run.errors.push(error.message));
  const result = { paused: [], screenshots: {} };
  await page.addInitScript(setupReadout);
  try {
    if (scene === "demo") {
      await page.goto(endpoint);
      await page.getByRole("link", { name: "デュエットの再生時計", exact: true }).click();
    } else {
      await installDiagnostic(page);
      await page.goto(`${endpoint}/?show=duet-mouth-diagnostic`);
    }
    await page.waitForFunction(() => window.firstMouthEpoch[0] !== undefined);
    const slider = page.getByRole("slider", { name: "音源の位置", exact: true });
    const read = () => page.evaluate(() => window.readMouth());
    let epoch = 0;
    const seek = async (sample) => {
      await slider.evaluate((input, seconds) => {
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(input, String(seconds));
        input.dispatchEvent(new Event("input", { bubbles: true }));
      }, sample / rate);
      await page.waitForFunction((target) => window.firstMouthEpoch[target] !== undefined, ++epoch);
      return page.evaluate((target) => window.firstMouthEpoch[target], epoch);
    };
    for (const [i, sample] of spec[`${scene}_paused_samples`].entries()) {
      result.paused.push(i === 0 && sample === 0 ? await read() : await seek(sample));
      if (scene === "demo" && spec.screenshot_samples.includes(sample)) {
        const name = `mouth-${viewport.width}-${sample}.png`;
        await page.locator(".duet-heads figure").first().screenshot({ path: join(out, name) });
        result.screenshots[sample] = name;
      }
    }
    if (scene === "demo" && viewport.width === spec.viewports[0][0]) {
      result.beforeResize = await seek(24000);
      await page.setViewportSize({ width: spec.viewports[1][0], height: viewport.height });
      await page.waitForFunction(() => window.readMouth()?.heads[0].overlay.below);
      result.afterResize = await read();
    }
    if (scene === "diagnostic") {
      const { start, seek_samples: seeks } = spec.diagnostic_live;
      await seek(start);
      await page.evaluate((watch) => { window.liveMouthWatch = watch; }, { ...spec.diagnostic_live, epoch });
      await page.getByRole("button", { name: "再生", exact: true }).click();
      const keys = ["melisma", "rest", "restFaded", "repeat", "following"];
      // 判定がまだ揃わなくても、診断譜の終端までに得た観測を残す。
      await page.waitForFunction((required) => required.every((key) => window.liveMouthMatches[key])
        || document.querySelector("button")?.textContent === "最初から再生", keys);
      const observed = await page.evaluate(() => ({ matches: window.liveMouthMatches, frames: window.liveMouthFrames }));
      if (!keys.every((key) => observed.matches[key])) {
        writeFileSync(join(out, `mouth-${viewport.width}-incomplete.json`), JSON.stringify(observed) + "\n");
        throw new Error("診断譜で指定した表示の一部を採取できません");
      }
      result.live = { ...observed.matches, seeks: [] };
      for (const sample of seeks) result.live.seeks.push(await seek(sample));
    }
  } finally {
    await page.close();
  }
  return result;
}

const server = await preview({ root, preview: { host, port: 0 } });
let browser;
try {
  browser = await chromium.launch({ headless: true, executablePath: process.env.CHIMERA_CHROMIUM,
    args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
  run.browser = browser.version();
  const endpoint = `http://${host}:${server.httpServer.address().port}`;
  for (const [width, height] of spec.viewports) {
    const viewport = { width, height };
    run.viewports.push({ width, demo: await capture(browser, endpoint, viewport, "demo"),
      diagnostic: await capture(browser, endpoint, viewport, "diagnostic") });
  }
} finally {
  if (browser) await browser.close();
  await new Promise((resolve) => server.httpServer.close(resolve));
  writeFileSync(join(out, "browser-mouth.json"), JSON.stringify(run) + "\n");
}

const upstreamFile = (path) => import(pathToFileURL(join(upstream, path)));
const { advanceTrail, mouthWords } = await upstreamFile("src/ui/mouthWords.ts");
const { sungWords, wordAt } = await upstreamFile("src/show/words.ts");
const trial = { entries: [] }, candidate = new DuetMouthTrail(), isolated = new DuetMouthTrail();
const control = spec.controlled_trail.map(({ time_ms, word, seek }) => {
  const seconds = time_ms / 1000;
  advanceTrail(trial, word, seconds);
  candidate.update(word, seconds);
  isolated.update(word, seconds, seek);
  return structuredClone({ upper: trial.entries, candidate: candidate.entries, isolated: isolated.entries });
});

// 固定上流の文字描画に、ブラウザで採取した口唇座標と同じ文字幅を与える。
globalThis.Path2D = class {
  moveTo() {}
  lineTo() {}
};
const songInputs = JSON.parse(readFileSync(join(reference, "word-inputs.json"), "utf8"));
const placements = [];
for (const viewport of run.viewports) {
  for (const scene of ["demo", "diagnostic"]) {
    const { voices, spell } = songInputs[scene];
    const notes = voices.map(({ melody, syllables }) => sungWords(melody, syllables, spell));
    for (const row of viewport[scene].paused) {
      const heads = row.heads.map((head, i) => {
        const word = wordAt(notes[i], row.time), calls = [];
        const ctx = {
          save() {}, restore() {}, setLineDash() {}, stroke() {},
          measureText: () => ({ width: head.labels[0]?.baseWidth ?? 50 }),
          fillText(text, x, y) {
            calls.push({ text, x, y, size: Number(this.font.match(/([\d.]+)px/)[1]),
              alpha: this.globalAlpha, align: this.textAlign });
          },
        };
        const { x, y, pxPerCm, width: w, height: h } = head.overlay.view;
        const r = { handles: () => [{ id: "lips", pos: {} }], X: () => x, Y: () => y, pxPerCm };
        mouthWords(() => word, "#174c3b", head.facing)(ctx, r, null, null, null, { w, h, dt: 0 });
        return { word, calls };
      });
      placements.push({ scene, width: viewport.width, sample: row.sample, epoch: row.epoch, heads });
    }
  }
}
writeFileSync(join(out, "upper-mouth.json"), JSON.stringify({ control, placements }) + "\n");
