import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { chromium } from "playwright-core";
import { preview } from "vite";
import { buildDuetWords, duetWordAt, readDuetMelody } from "../src/duet-words.ts";

const [casePath, upstream, out] = process.argv.slice(2);
const spec = JSON.parse(readFileSync(casePath, "utf8"));
const plan = JSON.parse(readFileSync(join(out, "word-inputs.json"), "utf8"));
const { sungWords, wordAt } = await import(pathToFileURL(join(upstream, "src/show/words.ts")));
const rate = spec.sample_rate_hz;

const engines = Object.fromEntries(Object.entries(plan).map(([scene, { voices, samples, spell }]) => [scene,
  voices.map(({ melody, syllables }) => {
    const candidate = buildDuetWords(readDuetMelody(melody), syllables, rate, spell);
    const upstream = sungWords(melody, syllables, spell);
    const upperEntries = upstream.times.map(([start, end], i) => ({ start, end,
      word: { key: upstream.parent[i], text: upstream.shown[i] } }));
    return { candidate, upstream: upperEntries, samples: samples.map((sample) => ({ sample,
      candidate: duetWordAt(candidate, sample / rate), upstream: wordAt(upstream, sample / rate) })) };
  })]));
const wrongCount = [];
for (const build of [buildDuetWords, sungWords]) {
  try { build(plan.diagnostic.voices[0].melody, []); wrongCount.push(false); }
  catch { wrongCount.push(true); }
}
writeFileSync(join(out, "word-selection.json"), JSON.stringify({ engines, wrongCount }, null, 2) + "\n");

async function installDiagnosticAssets(page, wrong = false) {
  const assets = new Map([
    ["show.json", "application/json"], ["melody-1.json", "application/json"],
    ["melody-2.json", "application/json"], ["mix.wav", "audio/wav"],
  ]);
  await page.route("**/shows/duet-words-test/*", (route) => {
    const asset = new URL(route.request().url()).pathname.split("/").at(-1);
    if (!assets.has(asset)) return route.abort();
    let body = readFileSync(join(out, "diagnostic", asset));
    if (wrong && asset === "melody-1.json") {
      const melody = JSON.parse(body);
      melody.syllables.pop();
      body = JSON.stringify(melody);
    }
    return route.fulfill({ contentType: assets.get(asset), body });
  });
}

function seekControls(page) {
  const slider = page.getByRole("slider", { name: "音源の位置", exact: true });
  let epoch = 0;
  return async (sample) => {
    await slider.evaluate((input, seconds) => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(input, String(seconds));
      input.dispatchEvent(new Event("input", { bubbles: true }));
    }, sample / rate);
    await page.waitForFunction((target) => Number(document.querySelector("output").dataset.epoch) === target, ++epoch);
  };
}

const readPage = (page) => page.evaluate(() => {
  const clock = document.querySelector('output[aria-label="音源フレーム"]');
  const words = [...document.querySelectorAll(".duet-lyrics dd")].map((word) => word.dataset.wordKey === undefined
    ? null : { key: Number(word.dataset.wordKey), text: word.textContent });
  return { frame: Number(clock.textContent), seconds: Number(clock.dataset.time), epoch: Number(clock.dataset.epoch),
    playing: document.querySelector("button").textContent === "一時停止", words };
});

const host = "127.0.0.1";
const root = fileURLToPath(new URL("../", import.meta.url));
const server = await preview({ root, preview: { host, port: 0 } });
const endpoint = `http://${host}:${server.httpServer.address().port}`;
const result = { errors: [] };
let browser;
try {
  browser = await chromium.launch({ headless: true, executablePath: process.env.CHIMERA_CHROMIUM });
  result.version = browser.version();
  for (const scene of ["demo", "diagnostic"]) {
    const page = await browser.newPage();
    const log = { paused: [], live: [], assets: [] };
    result[scene] = log;
    page.on("pageerror", (error) => result.errors.push(error.message));
    page.on("response", (response) => log.assets.push({ path: new URL(response.url()).pathname, status: response.status() }));
    if (scene === "diagnostic") await installDiagnosticAssets(page);
    try {
      if (scene === "demo") {
        await page.goto(endpoint);
        await page.getByRole("link", { name: "デュエットの再生時計", exact: true }).click();
        await page.waitForURL("**/?show=duet-clock");
      } else await page.goto(`${endpoint}/?show=duet-words-test`);
      await page.locator(".duet-lyrics dd").last().waitFor();
      const seek = seekControls(page);
      for (const sample of spec[scene].paused_samples) {
        if (sample !== 0) await seek(sample);
        log.paused.push(await readPage(page));
      }
      if (scene === "diagnostic") {
        for (const [index, sample] of spec.diagnostic.live_samples.entries()) {
          await seek(sample);
          if (index === 0) await page.getByRole("button", { name: "再生", exact: true }).click();
          await page.waitForFunction((target) => Number(document.querySelector("output").textContent) >= target,
            sample + spec.diagnostic.live_settle_samples);
          log.live.push(await readPage(page));
        }
        await page.getByRole("button", { name: "一時停止", exact: true }).click();
        await page.getByRole("button", { name: "再生", exact: true }).waitFor();
        log.held = [await readPage(page)];
        await page.waitForTimeout(125);
        log.held.push(await readPage(page));
      }
    } finally {
      await page.close();
    }
  }
  const bad = await browser.newPage();
  await installDiagnosticAssets(bad, true);
  await bad.goto(`${endpoint}/?show=duet-words-test`);
  await bad.getByRole("button", { name: "再生", exact: true }).waitFor();
  result.invalidMelody = await bad.locator(".duet-lyrics dd").first().textContent();
  await seekControls(bad)(42000);
  await bad.getByRole("button", { name: "再生", exact: true }).click();
  await bad.getByRole("button", { name: "一時停止", exact: true }).waitFor();
  result.invalidPlayback = await readPage(bad);
} catch (error) {
  result.failure = String(error);
  throw error;
} finally {
  writeFileSync(join(out, "browser-words.json"), JSON.stringify(result, null, 2) + "\n");
  await browser?.close();
  await new Promise((done) => server.httpServer.close(done));
}
