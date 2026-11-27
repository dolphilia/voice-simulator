// WASM取得の応答を保留し、英語の実時間発話とオフライン発話を重ねる。
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium, errors, firefox } from "playwright-core";
import { createServer } from "vite";

const [out, casePath, fixturePath] = process.argv.slice(2);
if (!out || !casePath || !fixturePath) throw new Error("出力先、比較ケース、発話ケースを指定してください");
const { measurement } = JSON.parse(readFileSync(casePath, "utf8"));
const fixture = JSON.parse(readFileSync(fixturePath, "utf8"));
const timeout = measurement.phase_timeout_ms;
const root = fileURLToPath(new URL("../", import.meta.url));
const server = await createServer({ root, server: { host: "127.0.0.1", port: 0, hmr: false, watch: null } });

function instrumentPage({ fixture, stride }) {
  return Promise.all([import("/src/render-fixed-voice.ts"), import("/src/english-speech-case.ts")]).then(
    ([{ renderEnglishVoice, renderRealtimeEnglishVoice, floatWave }, { readEnglishSpeechCase }]) => {
      const { config, text, rate, start, inputId } = readEnglishSpeechCase(fixture);
      const controller = new AbortController();
      const events = [];
      const contexts = [];
      const offlineNodes = [];
      const compileHashes = [];
      const calls = {};
      const captures = {};
      let fetches = 0;
      let planners = 0;
      const event = (name) => events.push({ name, ms: performance.now() });

      const fetch = window.fetch;
      window.fetch = function (url, ...options) {
        if (new URL(url instanceof Request ? url.url : url, location.href).pathname.endsWith(".wasm")) {
          fetches += 1;
          event("wasm_fetch");
        }
        return fetch.call(this, url, ...options);
      };
      const compile = WebAssembly.compile;
      WebAssembly.compile = function (bytes, ...options) {
        event("wasm_compile");
        compileHashes.push(crypto.subtle.digest("SHA-256", bytes).then(
          (hash) => Array.from(new Uint8Array(hash), (byte) => byte.toString(16).padStart(2, "0")).join(""),
        ));
        return compile.call(this, bytes, ...options);
      };
      WebAssembly.Instance = class extends WebAssembly.Instance {
        constructor(...args) {
          super(...args);
          if ("vocal_english_plan_with_body" in this.exports) {
            planners += 1;
            event("planner_created");
          }
        }
      };
      window.AudioContext = class extends window.AudioContext {
        constructor(...args) {
          super(...args);
          const index = contexts.push({ context: this, nodes: 0 }) - 1;
          event(`context_${index}_created`);
          this.addEventListener("statechange", () => event(`context_${index}_${this.state}`));
        }
      };
      window.AudioWorkletNode = class extends window.AudioWorkletNode {
        constructor(context, ...args) {
          super(context, ...args);
          const realtime = contexts.find((entry) => entry.context === context);
          if (realtime) realtime.nodes += 1;
          else offlineNodes.push(context.sampleRate);
        }
      };

      const run = (name, render) => {
        calls[name] = { outcome: "pending" };
        event(`${name}_start`);
        void render().then((result) => {
          captures[name] = result;
          calls[name] = { outcome: "fulfilled" };
          event(`${name}_fulfilled`);
        }, (error) => {
          calls[name] = { outcome: "rejected", error: error.name, message: error.message };
          event(`${name}_rejected`);
        });
      };
      const button = (label, action) => {
        const element = document.createElement("button");
        element.textContent = label;
        element.addEventListener("click", action, { once: true });
        document.body.append(element);
      };
      button("比較を開始", () => {
        run("stopped", () => renderRealtimeEnglishVoice(config, text, rate, stride, controller.signal, start, inputId));
        run("offline", () => renderEnglishVoice(config, text, rate, stride, start, inputId));
      });
      button("実時間を再開", () => run("restarted", () => renderRealtimeEnglishVoice(
        config, text, rate, stride, new AbortController().signal, start, inputId,
      )));
      window.englishAbortProbe = {
        calls,
        stop: () => { event("stop_requested"); controller.abort(); },
        allowResponse: () => event("response_allowed"),
        snapshot: () => ({
          calls, fetches, compilations: compileHashes.length, planners, offlineNodes,
          contexts: contexts.map(({ context, nodes }) => ({ state: context.state, rate: context.sampleRate, nodes })),
        }),
        evidence: async () => ({ events, compiledSha256: await Promise.all(compileHashes) }),
        download: (name, extension) => {
          const { pcm, audio, report } = captures[name];
          const blob = extension === "wav"
            ? floatWave(pcm ?? audio.getChannelData(0), report.sampleRate)
            : new Blob([JSON.stringify(report)], { type: "application/json" });
          const link = document.createElement("a");
          link.href = URL.createObjectURL(blob);
          link.download = `${name}.${extension}`;
          link.click();
        },
      };
    },
  );
}

const isWasm = (request) => request.resourceType() === "fetch" && new URL(request.url()).pathname.endsWith(".wasm");

async function capture(browser, url, folder) {
  const page = await browser.newPage({ acceptDownloads: true });
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  let routeRequests = 0;
  const { promise: hold, resolve: release } = Promise.withResolvers();
  try {
    await page.route("**/research-abort-probe", (route) => route.fulfill({
      contentType: "text/html", body: "<!doctype html><html lang=ja><title>英語発話の比較</title><body></body></html>",
    }));
    await page.route(/\.wasm(?:\?|$)/, async (route) => {
      if (isWasm(route.request())) {
        routeRequests += 1;
        await hold;
      }
      await route.continue();
    });
    await page.goto(url + "research-abort-probe");
    await page.evaluate(instrumentPage, { fixture, stride: measurement.observation_stride_frames });
    const snapshot = () => page.evaluate(() => window.englishAbortProbe.snapshot());
    const settled = async (name) => {
      try {
        await page.waitForFunction((id) => window.englishAbortProbe.calls[id]?.outcome !== "pending"
          && Boolean(window.englishAbortProbe.calls[id]), name, { timeout });
        return true;
      } catch (error) {
        if (!(error instanceof errors.TimeoutError)) throw error;
        return false;
      }
    };
    await Promise.all([
      page.waitForRequest(isWasm, { timeout }),
      page.getByRole("button", { name: "比較を開始", exact: true }).click(),
    ]);
    const beforeStop = await snapshot();
    await page.evaluate(() => window.englishAbortProbe.stop());
    const stoppedWhileHeld = await settled("stopped");
    const whileHeld = await snapshot();
    await page.evaluate(() => window.englishAbortProbe.allowResponse());
    release();
    const offlineSettled = await settled("offline");
    const afterOffline = await snapshot();

    await page.getByRole("button", { name: "実時間を再開", exact: true }).click();
    const restartedSettled = await settled("restarted");
    const afterRestart = await snapshot();
    for (const name of ["offline", "restarted"]) {
      if (afterRestart.calls[name]?.outcome !== "fulfilled") continue;
      for (const extension of ["wav", "json"]) {
        const [download] = await Promise.all([
          page.waitForEvent("download", { timeout }),
          page.evaluate(({ name, extension }) => window.englishAbortProbe.download(name, extension), { name, extension }),
        ]);
        await download.saveAs(join(folder, `${name}.${extension}`));
      }
    }
    const evidence = await page.evaluate(() => window.englishAbortProbe.evidence());
    writeFileSync(join(folder, "abort-evidence.json"), JSON.stringify({
      browser: browser.version(), engine: browser.browserType().name(), ...evidence, pageErrors, routeRequests,
      stoppedWhileHeld, offlineSettled, restartedSettled, beforeStop, whileHeld, afterOffline, afterRestart,
    }, null, 2) + "\n");
  } finally {
    release();
    await page.close();
  }
}

try {
  await server.listen();
  const url = `http://127.0.0.1:${server.httpServer.address().port}/`;
  for (const engine of measurement.browsers) {
    const browser = engine === "firefox"
      ? await firefox.launch({ headless: true, executablePath: process.env.CHIMERA_FIREFOX })
      : await chromium.launch({ headless: true, executablePath: process.env.CHIMERA_CHROMIUM });
    const folder = join(out, engine);
    mkdirSync(folder);
    try {
      await capture(browser, url, folder);
    } finally {
      await browser.close();
    }
  }
} finally {
  await server.close();
}
