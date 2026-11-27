// 通常の画面の操作と、固定上流のTransportを、同一の音源と実ブラウザで測る。
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { chromium } from "playwright-core";
import { createServer, preview } from "vite";
import { checkDuetClock } from "./check-duet-clock.mjs";

const [casePath, upstream, out, mixPath] = process.argv.slice(2);
if (!mixPath) throw new Error("比較ケース、固定上流、保存先、WAVが必要です");
const spec = JSON.parse(readFileSync(casePath, "utf8"));
const host = "127.0.0.1";
const root = fileURLToPath(new URL("../", import.meta.url));
const wave = readFileSync(mixPath);
const expectedWave = createHash("sha256").update(wave).digest("hex");
const { Transport } = await import(pathToFileURL(join(upstream, "src/show/transport.ts")));
const { DuetTransport } = await import("../src/duet-transport.ts");
const model = await checkDuetClock({
  candidate: { make: (clock) => new DuetTransport(clock), read: (player) => player.snapshot() },
  upstream: { make: (clock) => new Transport(clock), read: (player) => { player.time(); return player.state; } },
}, spec);
writeFileSync(join(out, "virtual-clock.json"), JSON.stringify(model, null, 2) + "\n");

function observeAudio({ rate, fftSize }) {
  let context;
  let decoded;
  let waveSha256;
  let active;
  let rejectResume;
  const sources = [];
  window.AudioContext = new Proxy(AudioContext, {
    construct(target, [options]) {
      context = Reflect.construct(target, [{ ...options, sampleRate: rate }]);
      const decode = context.decodeAudioData.bind(context);
      context.decodeAudioData = async (bytes) => {
        const hash = await crypto.subtle.digest("SHA-256", bytes);
        waveSha256 = Array.from(new Uint8Array(hash), (b) => b.toString(16).padStart(2, "0")).join("");
        const buffer = await decode(bytes);
        decoded = { length: buffer.length, rate: buffer.sampleRate, channels: buffer.numberOfChannels };
        return buffer;
      };
      const makeSource = context.createBufferSource.bind(context);
      context.createBufferSource = () => {
        const node = makeSource();
        const analyser = context.createAnalyser();
        analyser.fftSize = fftSize;
        node.connect(analyser);
        const record = { ended: false, stop_called: false, disconnected: false };
        const { start, stop, disconnect } = node;
        node.start = (when, offset) => {
          Object.assign(record, { when, offset });
          active = { record, analyser };
          sources.push(record);
          return start.call(node, when, offset);
        };
        node.stop = (...args) => { record.stop_called = true; return stop.call(node, ...args); };
        node.disconnect = (...args) => { record.disconnected = true; return disconnect.call(node, ...args); };
        node.addEventListener("ended", () => { record.ended = true; });
        return node;
      };
      return context;
    },
  });
  window.readDuetSources = () => ({ sources, decoded, wave_sha256: waveSha256 });
  window.holdDuetResume = async () => {
    await context.suspend();
    const resume = context.resume.bind(context);
    context.resume = () => {
      context.resume = resume;
      return new Promise((_resolve, reject) => { rejectResume = reject; });
    };
  };
  window.rejectDuetResume = () => rejectResume(new Error("観測用に再開を拒否しました"));
  window.readDuetPosition = (withSignal) => {
    const position = document.querySelector('output[aria-label="音源フレーム"]');
    let signal;
    let signalClock;
    if (withSignal) {
      const values = new Float32Array(fftSize);
      const before = context.currentTime;
      active.analyser.getFloatTimeDomainData(values);
      signalClock = [before, context.currentTime];
      signal = Array.from(values);
    }
    return {
      frame: Number(position.textContent), time: Number(position.dataset.time), epoch: Number(position.dataset.epoch),
      playing: document.querySelector("button").textContent === "一時停止", source: active?.record,
      context_time: context.currentTime, context_state: context.state,
      timestamp: context.getOutputTimestamp(), performance_ms: performance.now(), signal, signal_clock: signalClock,
    };
  };
}

async function initReference(page, url) {
  await page.goto(url + "/__duet");
  await page.evaluate(async (rate) => {
    const { Transport } = await import("/src/show/transport.ts");
    const player = new Transport();
    await player.load(await (await fetch("/__mix.wav")).arrayBuffer());
    const button = document.querySelector("button");
    const slider = document.querySelector("input");
    const frame = document.querySelector("output");
    const paint = () => {
      const time = player.time();
      button.textContent = player.isPlaying ? "一時停止" : time >= player.duration - 0.05 ? "最初から再生" : "再生";
      slider.value = String(time);
      frame.textContent = String(Math.round(time * rate));
      frame.dataset.time = String(time);
      frame.dataset.epoch = String(player.epoch);
    };
    slider.max = String(player.duration);
    slider.oninput = () => { player.seek(Number(slider.value)); paint(); };
    button.onclick = () => { if (player.isPlaying) player.pause(); else player.play(); paint(); };
    paint();
    const update = () => { paint(); requestAnimationFrame(update); };
    requestAnimationFrame(update);
  }, spec.source.sample_rate_hz);
}

async function capture(browser, name, url) {
  const page = await browser.newPage({ viewport: { width: 960, height: 820 } });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.addInitScript(observeAudio, { rate: spec.source.sample_rate_hz, fftSize: spec.browser.analyser_frames });
  const positions = {};
  try {
    if (name === "candidate") {
      await page.goto(url);
      await page.getByRole("link", { name: "デュエットの再生時計", exact: true }).click();
      await page.waitForURL(`**/?show=${spec.source.show_id}`);
    } else {
      await initReference(page, url);
    }
    const play = page.getByRole("button", { name: "再生", exact: true });
    const pause = page.getByRole("button", { name: "一時停止", exact: true });
    const again = page.getByRole("button", { name: "最初から再生", exact: true });
    const slider = page.getByRole("slider", { name: "音源の位置", exact: true });
    const take = async (label, signal = false) => {
      positions[label] = await page.evaluate((withSignal) => window.readDuetPosition(withSignal), signal);
    };
    const seek = (seconds) => slider.evaluate((input, value) => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(input, String(value));
      input.dispatchEvent(new Event("input", { bubbles: true }));
    }, seconds);
    const until = (seconds) => page.waitForFunction((time) =>
      Number(document.querySelector("output").dataset.time) >= time, seconds);
    await play.waitFor();
    await take("ready");
    await play.click();
    await until(spec.browser.first_audio_observation_seconds);
    await take("first_audio", true);
    await pause.click();
    await take("paused");
    await page.waitForTimeout(spec.browser.pause_check_milliseconds);
    await take("held");
    await seek(spec.browser.paused_seek_seconds);
    await until(spec.browser.paused_seek_seconds - 1e-6);
    await take("paused_seek");
    await play.click();
    await until(spec.browser.paused_seek_seconds + 0.08);
    await seek(spec.browser.playing_seek_seconds);
    await until(spec.browser.second_audio_observation_seconds);
    await take("second_audio", true);
    await seek(spec.browser.end_seek_seconds);
    await again.waitFor();
    await take("end");
    await again.click();
    await pause.waitFor();
    await take("again");
    const audio = await page.evaluate(() => window.readDuetSources());
    await pause.click();
    await play.waitFor();
    await page.evaluate(() => window.holdDuetResume());
    await play.click();
    await pause.waitFor();
    await seek(spec.browser.rejected_resume_seek_seconds);
    await until(spec.browser.rejected_resume_seek_seconds - 1e-6);
    await take("before_rejection");
    await page.evaluate(async () => {
      window.rejectDuetResume();
      await new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done)));
    });
    await take("after_rejection");
    return { positions, errors, expected_wave_sha256: expectedWave, ...audio };
  } catch (error) {
    writeFileSync(join(out, `${name}-partial.json`), JSON.stringify({ positions, errors, failure: String(error),
      ...await page.evaluate(() => window.readDuetSources?.()).catch(() => ({})) }, null, 2));
    throw error;
  } finally {
    await page.close();
  }
}

const web = await preview({ root, preview: { host, port: 0 } });
let fixed;
let browser;
try {
  fixed = await createServer({ root: upstream, configFile: false, server: { host, port: 0, hmr: false, watch: null },
    plugins: [{ name: "duet-reference",
      configureServer(server) {
        server.middlewares.use("/__duet", (_req, res) => {
          res.setHeader("Content-Type", "text/html; charset=utf-8");
          res.end('<!doctype html><meta charset="utf-8"><button>準備中</button><label>音源の位置<input type="range" min="0" step="any"></label><output aria-label="音源フレーム"></output>');
        });
        server.middlewares.use("/__mix.wav", (_req, res) => {
          res.setHeader("Content-Type", "audio/wav");
          res.end(wave);
        });
      } }],
  });
  await fixed.listen();
  browser = await chromium.launch({ headless: true, executablePath: process.env.CHIMERA_CHROMIUM });
  const result = { version: browser.version() };
  for (const [name, server] of [["candidate", web], ["upstream", fixed]]) {
    result[name] = await capture(browser, name, `http://${host}:${server.httpServer.address().port}`);
    writeFileSync(join(out, "browser.json"), JSON.stringify(result, null, 2) + "\n");
  }
} finally {
  await browser?.close();
  await fixed?.close();
  await new Promise((done) => web.httpServer.close(done));
}
