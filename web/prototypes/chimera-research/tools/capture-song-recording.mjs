// 実ブラウザで候補の歌唱画面と固定上流のClipを別々に実行する。
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { chromium, firefox } from "playwright-core";
import { createServer, preview } from "vite";
import { trackRecorder } from "./observe-song-recorder.mjs";

const { positionals, values } = parseArgs({ allowPositionals: true, options: { "firefox-case": { type: "string" } } });
const [out, casePath, upstream, referencePcm, tractCasePath, webmCasePath, vp8CasePath] = positionals;
if (!out || !casePath || !upstream || !referencePcm) throw new Error("録画ケースと固定上流の入力が必要です");
const { measurement: spec } = JSON.parse(readFileSync(casePath, "utf8"));
const webm = webmCasePath && JSON.parse(readFileSync(webmCasePath, "utf8")).measurement;
const vp8 = vp8CasePath && JSON.parse(readFileSync(vp8CasePath, "utf8")).measurement;
if (vp8) Object.assign(webm, vp8);
const firefoxCase = values["firefox-case"] && JSON.parse(readFileSync(values["firefox-case"], "utf8"));
const nativeFormats = firefoxCase?.measurement.format_priority;
const playbackSeconds = firefoxCase?.measurement.minimum_browser_playback_seconds ?? webm?.minimum_browser_playback_seconds;
const webRoot = fileURLToPath(new URL("../", import.meta.url));
const host = "127.0.0.1";

async function waitForTake(page, count, milliseconds) {
  await page.waitForFunction(({ count, milliseconds }) => {
    const take = window.inspectRecording().takes[count - 1];
    return take?.state === "recording" && performance.now() - take.started >= milliseconds;
  }, { count, milliseconds });
}

async function download(page, link, filename) {
  const [saved] = await Promise.all([page.waitForEvent("download"), link.click()]);
  const name = filename ?? saved.suggestedFilename();
  await saved.saveAs(join(out, name));
  return name;
}

async function candidate(browser, url) {
  const page = await browser.newPage({ acceptDownloads: true, viewport: { width: 960, height: 920 } });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.addInitScript(trackRecorder, { webm, nativeFormats });
  try {
    await page.goto(url);
    const panel = page.getByRole("region", { name: "歌唱", exact: true });
    if (tractCasePath) await panel.getByRole("checkbox", { name: "録画に声道の三次元断面を含める", exact: true }).check();
    const button = panel.getByRole("button", { name: "歌唱を録画", exact: true });
    const cancel = panel.getByRole("button", { name: "録画を中止", exact: true });
    const clip = panel.getByRole("link", { name: "歌唱の動画を保存", exact: true });
    const module = page.waitForResponse((r) => r.ok() && new URL(r.url()).pathname.endsWith(".wasm"));
    await button.click();
    if (!tractCasePath) {
      await waitForTake(page, 1, 1000);
      await panel.locator("canvas.song-recording-preview").screenshot({ path: join(out, "recording-preview.png") });
    }
    const servedWasmSha256 = createHash("sha256").update(await (await module).body()).digest("hex");
    await panel.getByText("歌唱の録画完了", { exact: true }).waitFor();
    const name = await download(page, clip);
    await download(page, panel.getByRole("link", { name: "WAVを保存", exact: true }), "recorded-input.wav");
    await download(page, panel.getByRole("link", { name: "観測JSONを保存", exact: true }), "recorded-input.json");
    const player = panel.getByLabel("録画した歌唱", { exact: true });
    const playback = await player.evaluate(async (video) => {
      if (!video.readyState && !video.error) await new Promise((done) => {
        video.addEventListener("loadedmetadata", done, { once: true });
        video.addEventListener("error", done, { once: true });
      });
      return { width: video.videoWidth, height: video.videoHeight, error: video.error?.message ?? null,
        durationAtMetadata: String(video.duration) };
    });
    if (playbackSeconds && !playback.error) {
      playback.mimeType = await player.evaluate(async (video) => {
        const response = await fetch(video.currentSrc);
        await video.play();
        return response.headers.get("Content-Type");
      });
      await page.waitForFunction((seconds) => document.querySelector("video").currentTime >= seconds,
        playbackSeconds);
      Object.assign(playback, await player.evaluate((video) => {
        video.pause();
        return { playedSeconds: video.currentTime, audioVideoError: video.error?.message ?? null };
      }));
    }
    await button.click();
    await waitForTake(page, 2, spec.cancel_after_recording_seconds * 1000);
    await cancel.click();
    await button.waitFor();
    await page.waitForFunction(() => window.inspectRecording().takes[1]?.stopped !== null
      && window.inspectRecording().contexts[1] === "closed");
    const cancelledWithoutFile = await clip.count() === 0 && await panel.getByRole("alert").count() === 0;
    await button.click();
    await clip.waitFor();
    // 取得待ちの中止後にも、止めた録画が遅れて作られないことを確認する。
    const wasmUrl = /\.wasm(?:\?|$)/;
    let allowFetch;
    const fetchGate = new Promise((resolve) => { allowFetch = resolve; });
    const pauseWasm = async (route) => {
      await fetchGate;
      await route.continue().catch(() => {});
    };
    await page.route(wasmUrl, pauseWasm);
    let cancelledWhileStarting;
    try {
      await Promise.all([page.waitForRequest(wasmUrl), button.click()]);
      await cancel.click();
      await page.waitForFunction(() => window.inspectRecording().closedContexts.length === 4, undefined, { timeout: 5000 });
      cancelledWhileStarting = await clip.count() === 0 && await panel.getByRole("alert").count() === 0;
    } finally {
      allowFetch();
      await page.unroute(wasmUrl, pauseWasm);
    }
    const state = await page.evaluate(() => window.inspectRecording());
    return { name, servedWasmSha256, errors, playback, cancelledWithoutFile, cancelledWhileStarting, ...state };
  } catch (error) {
    const state = await page.evaluate(() => ({
      alerts: [...document.querySelectorAll("[role=alert]")].map((element) => element.textContent),
      recording: window.inspectRecording?.(),
    })).catch(() => null);
    writeFileSync(join(out, "recording-candidate-failure.json"), JSON.stringify({ ...state, errors }, null, 2) + "\n");
    throw error;
  } finally {
    await page.close();
  }
}

async function reference(browser, url) {
  const page = await browser.newPage({ acceptDownloads: true });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.addInitScript(trackRecorder, { webm, nativeFormats, observeClipDraws: Boolean(webm || nativeFormats) });
  try {
    await page.goto(url + "/__clip-probe");
    await page.evaluate(async ({ rate, beat, cancelSeconds, drainMs }) => {
      const { Clip, canRecord, recording } = await import("/src/song/record.ts");
      if (!canRecord()) throw new Error("固定上流が録画形式を選べません");
      const bytes = await (await fetch("/__clip-audio")).arrayBuffer();
      const pcm = new Float32Array(bytes);
      document.querySelector("button").onclick = () => {
        window.reference = (async () => {
          const context = new AudioContext({ sampleRate: rate, latencyHint: "interactive" });
          const tap = context.createMediaStreamDestination();
          const silence = new ConstantSourceNode(context, { offset: 0 });
          silence.connect(tap);
          silence.start();
          const buffer = context.createBuffer(1, pcm.length, rate);
          buffer.copyToChannel(pcm, 0);
          const canvas = document.createElement("canvas");
          canvas.width = 360;
          canvas.height = 640;
          const paint = canvas.getContext("2d");
          try {
            await context.resume();
            const record = async (stopEarly) => {
              const source = context.createBufferSource();
              source.buffer = buffer;
              source.connect(tap);
              const start = context.currentTime + 0.12;
              let raf;
              const draw = () => {
                const elapsed = context.currentTime - start;
                paint.fillStyle = elapsed < beat[0] ? "#748b95" : elapsed < beat[1] ? "#36bf7e" : "#ef8750";
                paint.fillRect(0, 0, canvas.width, canvas.height);
                raf = requestAnimationFrame(draw);
              };
              draw();
              const clip = new Clip(() => canvas, tap.stream);
              try {
                source.start(start);
                if (stopEarly) {
                  await new Promise((done) => setTimeout(done, cancelSeconds * 1000));
                  clip.cancel();
                  source.stop();
                  await window.awaitRecordingStop(1);
                  return { ownerCleared: recording.owner === null };
                }
                await new Promise((done) => { source.onended = done; });
                await new Promise((done) => setTimeout(done, drainMs));
                const file = await clip.stop("upstream-clip");
                const link = document.createElement("a");
                link.textContent = "固定上流の動画";
                link.download = file.name;
                link.href = URL.createObjectURL(file);
                document.body.appendChild(link);
                return { name: file.name, type: file.type, ownerCleared: recording.owner === null };
              } finally {
                cancelAnimationFrame(raf);
                clip.cancel();
                source.disconnect();
              }
            };
            const saved = await record(false);
            const cancelled = await record(true);
            return { saved, cancelled, drainMs, ...window.inspectRecording() };
          } finally {
            silence.stop();
            silence.disconnect();
            await context.close();
          }
        })();
      };
    }, { rate: spec.output_rate_hz, beat: spec.beat_seconds, cancelSeconds: spec.cancel_after_recording_seconds, drainMs: 230 });
    await page.getByRole("button").click();
    const result = await page.evaluate(() => window.reference);
    await download(page, page.getByRole("link", { name: "固定上流の動画", exact: true }), result.saved.name);
    return { ...result, errors };
  } finally {
    await page.close();
  }
}

const research = await preview({ root: webRoot, preview: { host, port: 0 } });
let fixed;
let browser;
try {
  fixed = await createServer({
    root: upstream, configFile: false, server: { host, port: 0, hmr: false, watch: null },
    plugins: [{
      name: "upstream-clip-probe",
      configureServer(server) {
        server.middlewares.use("/__clip-probe", (_request, response) => {
          response.setHeader("Content-Type", "text/html; charset=utf-8");
          response.end('<!doctype html><meta charset="utf-8"><button>固定上流を収録</button>');
        });
        server.middlewares.use("/__clip-audio", (_request, response) => {
          response.setHeader("Content-Type", "application/octet-stream");
          response.end(readFileSync(referencePcm));
        });
      },
    }],
  });
  await fixed.listen();
  const nativeGraphics = process.env.CHIMERA_RECORDING_GRAPHICS === "native";
  const args = tractCasePath && !firefoxCase && !nativeGraphics ? ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] : [];
  browser = firefoxCase ? await firefox.launch({ headless: true })
    : await chromium.launch({ headless: true, executablePath: process.env.CHIMERA_CHROMIUM, args });
  const result = { engine: firefoxCase ? "firefox" : "chromium", version: browser.version(), graphicsArgs: args };
  for (const [name, capture, server] of [["candidate", candidate, research], ["upstream", reference, fixed]]) {
    try {
      result[name] = await capture(browser, `http://${host}:${server.httpServer.address().port}`);
    } catch (error) {
      result[name] = { error: String(error) };
      throw error;
    } finally {
      writeFileSync(join(out, "recording-browser.json"), JSON.stringify(result, null, 2) + "\n");
    }
  }
} finally {
  await browser?.close();
  await fixed?.close();
  await new Promise((done) => research.httpServer.close(done));
}
