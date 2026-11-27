// ビルド済みの画面を操作し、実際に保存できるPCMと観測を取得する。
import { createHash } from "node:crypto";
import { closeSync, existsSync, mkdirSync, openSync, readFileSync, writeFileSync, writeSync } from "node:fs";
import { join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath } from "node:url";
import { chromium, firefox } from "playwright-core";
import { createServer, preview } from "vite";
import { installMidi } from "./fake-midi.mjs";
import { observeLiveTract } from "./observe-live-tract.mjs";
import { installSharedContextMarker, readSharedContextMarker, smoothMarkerPCM } from "./shared-context-marker.mjs";
import { installSongOutputProbe, readSongOutputProbe } from "./song-output-probe.mjs";

const [outDir, testPath] = process.argv.slice(2);
if (!outDir || !testPath) throw new Error("出力先と比較ケースを指定してください");
const { id, input, measurement } = JSON.parse(readFileSync(testPath, "utf8"));
const speechMarkerPath = id === "worklet-live-tsp-source-defaults"
  ? process.argv.slice(7).find((arg) => arg.startsWith("--speech-marker="))?.slice("--speech-marker=".length) : undefined;
const speechMarker = speechMarkerPath && JSON.parse(readFileSync(speechMarkerPath, "utf8"));
const webRoot = fileURLToPath(new URL("../", import.meta.url));
const songVoiceCapture = id === "worklet-song-voice" || id === "worklet-song-voice-fast";
const songLivePath = songVoiceCapture
  ? process.argv.slice(5).find((arg) => arg.startsWith("--live="))?.slice("--live=".length) : undefined;
const songLive = songLivePath ? JSON.parse(readFileSync(songLivePath, "utf8")).measurement : undefined;
const workletRequests = [];
const workletRequestClock = {
  name: "chimera-worklet-request-clock",
  configurePreviewServer(server) {
    server.middlewares.use((request, response, next) => {
      const path = new URL(request.url, "http://localhost").pathname;
      if (request.method === "GET" && /\/fixed-processor-(measured-)?entry-[^/]+\.js$/.test(path)) {
        const observation = { path, startedAtEpochMs: Date.now() };
        workletRequests.push(observation);
        response.once("finish", () => {
          observation.finishedAtEpochMs = Date.now();
          observation.status = response.statusCode;
        });
      }
      next();
    });
  },
};
const markerModule = {
  name: "chimera-shared-context-marker",
  configurePreviewServer(server) {
    const source = readFileSync(new URL("./shared-context-marker-worklet.js", import.meta.url));
    server.middlewares.use("/research-shared-context-marker.js", (_request, response) => {
      response.setHeader("Content-Type", "text/javascript");
      response.end(source);
    });
  },
};
const songOutputProbeModule = {
  name: "chimera-song-output-probe",
  configurePreviewServer(server) {
    const source = readFileSync(new URL("./song-output-probe-worklet.js", import.meta.url));
    server.middlewares.use("/research-song-output-probe.js", (_request, response) => {
      response.setHeader("Content-Type", "text/javascript");
      response.end(source);
    });
  },
};
const server = await preview({ root: webRoot, preview: { host: "127.0.0.1", port: 0 },
  plugins: [...(measurement?.marker || songLive?.shared_context_marker || speechMarker ? [markerModule] : []),
    ...(songLive?.output_probe ? [songOutputProbeModule] : []),
    ...(songLive?.observe_worklet_evaluation ? [workletRequestClock] : [])] });
const address = server.httpServer.address();
const url = `http://127.0.0.1:${address.port}/`;

async function dispatchTimedMidi(page, timeline) {
  return page.evaluate(async ({ events, port, stop_request_seconds: end }) => {
    const start = performance.now();
    const until = (seconds) => new Promise((resolve) =>
      setTimeout(resolve, Math.max(0, start + seconds * 1000 - performance.now())));
    const states = [];
    for (const event of events) {
      await until(event.seconds);
      const seconds = (performance.now() - start) / 1000;
      const bytes = event.type === "note-on" ? [144, event.note, event.velocity] : [128, event.note, 0];
      globalThis.chimeraTestMidi.apply({ port, bytes });
      await new Promise(requestAnimationFrame);
      const text = document.querySelector('output[aria-label="保持中のMIDI音"]')?.textContent;
      states.push({ seconds, ...(globalThis.pitchSnapshot?.() ?? { note: text === "なし" ? null : Number(text) }) });
    }
    await until(end);
    return states;
  }, timeline);
}

async function captureUpstreamMidiPitch(browser, timeline, upstream) {
  const server = await createServer({ root: upstream, server: { host: "127.0.0.1", port: 0, hmr: false, watch: null } });
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  try {
    await server.listen();
    await page.addInitScript(installMidi, [timeline.port]);
    await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/`);
    await page.getByRole("radio", { name: "Play", exact: true }).click();
    await page.getByRole("button", { name: "MIDI", exact: true }).click();
    const disconnect = page.getByRole("button", { name: `MIDI: ${timeline.port}`, exact: true });
    await disconnect.waitFor();
    await page.evaluate(async () => {
      const [{ useStore }, { engine }] = await Promise.all([
        import("/src/ui/store.ts"), import("/src/audio/AudioEngine.ts"),
      ]);
      await useStore.getState().start();
      if (!useStore.getState().started) throw new Error("固定上流の音声を開始できません");
      let gate = 0;
      const setGate = engine.gate.bind(engine);
      engine.gate = (level) => {
        gate = level;
        setGate(level);
      };
      globalThis.pitchSnapshot = () => {
        const { heldNotes, mode, source } = useStore.getState();
        return { mode, held: heldNotes, note: heldNotes.at(-1) ?? null, targetHz: source.f0, gate };
      };
    });
    const states = await dispatchTimedMidi(page, timeline);
    await disconnect.click();
    return { states, errors, ...await page.evaluate(() => ({
      requests: globalThis.chimeraTestMidi.requests,
      remainingListeners: globalThis.chimeraTestMidi.listenerCount(),
    })) };
  } finally {
    await page.close();
    await server.close();
  }
}

async function captureMidi(browser, timeline) {
  const page = await browser.newPage({ acceptDownloads: true });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  try {
    await page.addInitScript(installMidi, timeline ? [timeline.port] : measurement.ports);
    await page.goto(url);
    const panel = page.getByRole("region", { name: "MIDI鍵盤の発声", exact: true });
    await panel.getByRole("button", { name: "MIDIを接続" }).click();
    const start = panel.getByRole("button", { name: "MIDI計測を開始" });
    const response = page.waitForResponse((r) => r.ok() && new URL(r.url()).pathname.endsWith(".wasm"));
    await start.click();
    const hash = createHash("sha256").update(await (await response).body()).digest("hex");
    await panel.getByText("MIDI計測中", { exact: true }).waitFor();
    const states = timeline ? await dispatchTimedMidi(page, timeline) : [];
    for (const action of timeline ? [] : measurement.actions) {
      await page.evaluate((event) => globalThis.chimeraTestMidi.apply(event), action);
      await page.waitForTimeout(measurement.wait_ms);
      const note = await panel.getByLabel("保持中のMIDI音").textContent();
      states.push({ note: note === "なし" ? null : Number(note),
        inputs: (await panel.locator("[data-midi-inputs]").textContent()).split("、") });
    }
    await panel.getByRole("button", { name: "MIDI計測を停止" }).click();
    await panel.getByText("実時間計測完了", { exact: true }).waitFor();
    for (const [label, ext] of [
      ["WAVを保存", ".wav"], ["観測JSONを保存", ".json"], ["再実行ケースを保存", "-case.json"],
    ]) {
      const download = page.waitForEvent("download");
      await panel.getByRole("link", { name: label, exact: true }).click();
      await (await download).saveAs(join(outDir, "midi" + ext));
    }
    const readyAgain = await start.isEnabled();
    await panel.getByRole("button", { name: "MIDIを切断" }).click();
    const midi = await page.evaluate(() => ({ requests: globalThis.chimeraTestMidi.requests,
      remainingListeners: globalThis.chimeraTestMidi.listenerCount() }));
    return { version: browser.version(), servedWasmSha256: hash, errors, states, readyAgain, ...midi };
  } finally {
    await page.close();
  }
}

async function captureTract3D(browser) {
  const runs = [];
  for (const width of measurement.viewport_widths_css_px) {
    const page = await browser.newPage({ acceptDownloads: true, viewport: { width, height: 910 } });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    let wasmResponse;
    page.on("response", (response) => {
      if (response.ok() && new URL(response.url()).pathname.endsWith(".wasm")) wasmResponse = response;
    });
    try {
      await page.goto(url);
      const panel = page.getByRole("region", { name: "声道の三次元断面", exact: true });
      const image = panel.getByRole("img", { name: "正中矢状面に沿った声道の楕円断面" });
      for (const [index, variant] of measurement.variants.entries()) {
        await panel.getByLabel("姿勢", { exact: true }).selectOption(variant.id);
        if (index === 0) await panel.getByRole("button", { name: "三次元表示を開く" }).click();
        const link = panel.getByRole("link", { name: "三次元観測JSONを保存" });
        const alert = panel.getByRole("alert");
        await link.or(alert).waitFor({ timeout: 10000 });
        if (await alert.isVisible()) throw new Error(await alert.textContent());
        const section = panel.getByLabel("測定線", { exact: true });
        const selected = [];
        for (const i of measurement.selected_section_indices) {
          await section.selectOption(String(i));
          selected.push(await panel.locator("[data-section-distance]").evaluate((el) => {
            const list = el.closest("dl");
            return [Number(el.dataset.sectionDistance), Number(list.querySelector("[data-section-gap]").dataset.sectionGap),
              Number(list.querySelector("[data-section-area]").dataset.sectionArea)];
          }));
        }
        const renderer = await image.evaluate((canvas) => {
          const gl = canvas.getContext("webgl2");
          const debug = gl?.getExtension("WEBGL_debug_renderer_info");
          return { ready: Boolean(gl && !gl.isContextLost()), width: canvas.clientWidth, height: canvas.clientHeight,
            backingWidth: canvas.width, backingHeight: canvas.height,
            name: debug ? gl.getParameter(debug.UNMASKED_RENDERER_WEBGL) : null };
        });
        const name = `${width}-${variant.id}`;
        for (const [view, label] of [["angled", "斜め"], ["side", "側面"]]) {
          await panel.getByRole("button", { name: label, exact: true }).click();
          await image.screenshot({ path: join(outDir, `${name}-${view}.png`) });
          const download = page.waitForEvent("download");
          await link.click();
          await (await download).saveAs(join(outDir, `${name}-${view}.json`));
          if (width === 960 && index === 0 && view === "angled") {
            await panel.screenshot({ path: join(outDir, "browser-tract-3d.png") });
          }
        }
        runs.push({ width, variant: variant.id, renderer, selected });
      }
      await panel.getByRole("button", { name: "表示を閉じる" }).click();
      await image.waitFor({ state: "detached" });
      const closes = await panel.getByRole("button", { name: "三次元表示を開く" }).isEnabled();
      if (!wasmResponse) throw new Error("三次元表示用WASMの応答を記録できませんでした");
      const hash = createHash("sha256").update(await wasmResponse.body()).digest("hex");
      for (const result of runs.filter((entry) => entry.width === width)) {
        Object.assign(result, { servedWasmSha256: hash, errors, closes });
      }
    } catch (error) {
      writeFileSync(join(outDir, `tract-3d-${width}-browser-error.json`),
        JSON.stringify({ message: String(error), errors }, null, 2) + "\n");
      throw error;
    } finally {
      await page.close();
    }
  }
  return { version: browser.version(), runs };
}

async function capture(browser, retry) {
  const page = await browser.newPage({ viewport: { width: 960, height: 680 }, acceptDownloads: true });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  try {
    if (retry) {
      await page.addInitScript(() => {
        const addModule = AudioWorklet.prototype.addModule;
        let calls = 0;
        AudioWorklet.prototype.addModule = function (url, options) {
          if (++calls === 1) return Promise.reject(new Error("計測用のWorklet読み込み失敗"));
          return addModule.call(this, url, options);
        };
      });
    }
    await page.goto(url);
    const button = page.getByRole("button", { name: "固定母音 /i/ をレンダー", exact: true });
    let failure = null;
    if (retry) {
      await button.click();
      const alert = page.getByRole("alert");
      await alert.waitFor({ state: "visible" });
      failure = await alert.textContent();
    }
    const response = page.waitForResponse((r) => r.ok() && new URL(r.url()).pathname.endsWith(".wasm"));
    await button.click();
    const hash = createHash("sha256").update(await (await response).body()).digest("hex");
    const completed = page.getByRole("status").filter({ hasText: /^レンダー完了$/ });
    await completed.waitFor({ state: "visible" });
    const status = await completed.textContent();
    for (const [label, ext] of [["WAVを保存", "wav"], ["観測JSONを保存", "json"]]) {
      const download = page.waitForEvent("download");
      await page.getByRole("link", { name: label, exact: true }).click();
      await (await download).saveAs(join(outDir, `${retry ? "retry" : "browser"}.${ext}`));
    }
    await page.waitForFunction(() => Number.isFinite(document.querySelector("audio")?.duration));
    const audioDuration = await page.locator("audio").evaluate((audio) => audio.duration);
    if (!retry) await page.screenshot({ path: join(outDir, "browser.png") });
    return { failure, status, servedWasmSha256: hash, audioDuration, errors };
  } finally {
    await page.close();
  }
}

async function saveSharedContextMarker(page, directory) {
  await page.waitForFunction(() => globalThis.chimeraSharedContextMarker !== undefined);
  const { pcm, ...timeline } = await page.evaluate(readSharedContextMarker);
  writeFileSync(join(directory, "marker.f32le"), Buffer.from(pcm, "base64"));
  writeFileSync(join(directory, "marker.json"), JSON.stringify(timeline));
}

async function captureRealtime(browser, manual = false, trial) {
  const page = await browser.newPage({ viewport: { width: 960, height: 760 }, acceptDownloads: true });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  try {
    if (trial?.marker) {
      await page.addInitScript(installSharedContextMarker, trial.marker);
    }
    if (trial) {
      await page.addInitScript((schedule) => {
        const Original = globalThis.AudioWorkletNode;
        globalThis.AudioWorkletNode = class extends Original {
          constructor(context, name, options) {
            if (name === "chimera-fixed-live") {
              const originalSettings = options.processorOptions.settings;
              const settings = {
                ...originalSettings,
                maximumVoiced: schedule.stopFrame - originalSettings.preRoll,
                release: schedule.totalFrames - schedule.stopFrame,
              };
              const processorOptions = { ...options.processorOptions, settings };
              if (schedule.warmupCalls !== undefined) processorOptions.wasmRenderWarmupCalls = schedule.warmupCalls;
              if (schedule.dspWarmupFrames != null) processorOptions.wasmDspWarmupFrames = schedule.dspWarmupFrames;
              if (schedule.finalizationProbe) processorOptions.finalizationProbe = schedule.finalizationProbe;
              options = { ...options, processorOptions };
              globalThis.chimeraReleaseSchedule = { originalSettings, settings };
            }
            super(context, name, options);
          }
        };
      }, { stopFrame: trial.stopFrame, totalFrames: trial.totalFrames, warmupCalls: trial.warmupCalls,
        dspWarmupFrames: trial.dspWarmupFrames, finalizationProbe: trial.finalizationProbe });
    }
    await page.goto(url);
    const panel = page.getByRole("region", { name: manual ? "舌と唇の操作" : "実時間の発声", exact: true });
    const start = panel.getByRole("button", { name: "発声を開始", exact: true });
    const stop = panel.getByRole("button", { name: "発声を停止", exact: true });
    if (measurement.automatic_stop) {
      await panel.getByLabel("出力サンプルレート", { exact: true }).selectOption(String(measurement.output_rate_hz));
    }
    const response = page.waitForResponse((r) => r.ok() && new URL(r.url()).pathname.endsWith(".wasm"));
    await start.click();
    const hash = createHash("sha256").update(await (await response).body()).digest("hex");
    await panel.getByText("発声中", { exact: true }).waitFor();
    // ユーザーの停止操作を再現する。再入力にはブラウザが実際に適用したフレームを使う。
    const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
    if (manual) {
      const axisLabels = {
        tongue_body_x_cm: "舌体 X（cm）",
        tongue_body_y_cm: "舌体 Y（cm）",
        lip_aperture_cm: "口唇開度（cm）",
      };
      for (const { axis, value_cm } of measurement.gestures) {
        await wait(measurement.wait_before_each_action_ms);
        const slider = panel.getByRole("slider", { name: axisLabels[axis], exact: true });
        if (!await slider.isEnabled()) throw new Error("発声中の操作が無効です");
        // 小数値を画素幅で丸めず、入力欄の通常イベントに通す。
        await slider.evaluate((input, value) => {
          Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(input, String(value));
          input.dispatchEvent(new Event("input", { bubbles: true }));
          input.dispatchEvent(new Event("change", { bubbles: true }));
        }, value_cm);
      }
      if (measurement.body_switch) {
        await wait(measurement.body_switch.wait_after_gestures_ms);
        await selectVoiceBody(panel, measurement.body_switch.body);
      }
      await wait(measurement.wait_before_stop_ms);
    } else if (!measurement.automatic_stop) {
      await wait(measurement.manual_stop_after_ms);
    }
    if (!measurement.automatic_stop) await stop.click();
    await panel.getByText("実時間計測完了", { exact: true }).waitFor();
    for (const [label, ext] of [["WAVを保存", "wav"], ["観測JSONを保存", "json"]]) {
      const download = page.waitForEvent("download");
      await panel.getByRole("link", { name: label, exact: true }).click();
      await (await download).saveAs(join(trial?.dir ?? outDir, `browser.${ext}`));
    }
    let caseFilename;
    if (manual) {
      const pending = page.waitForEvent("download");
      await panel.getByRole("link", { name: "再実行ケースを保存", exact: true }).click();
      const downloaded = await pending;
      caseFilename = downloaded.suggestedFilename();
      await downloaded.saveAs(join(outDir, "browser-case.json"));
    }
    if (!trial && !measurement.browser_engine) await panel.screenshot({ path: join(outDir, "browser.png") });
    const schedule = trial ? await page.evaluate(() => globalThis.chimeraReleaseSchedule) : undefined;
    if (trial?.marker) await saveSharedContextMarker(page, trial.dir);
    return { version: browser.version(), engine: browser.browserType().name(), servedWasmSha256: hash, errors,
      controlsReset: await start.isEnabled() && await stop.isDisabled(), caseFilename, schedule };
  } catch (error) {
    if (!trial?.marker && !measurement.browser_engine) throw error;
    const alerts = await page.getByRole("alert").allTextContents();
    throw new Error([String(error), ...alerts, ...errors].join("\n"));
  } finally {
    await page.close();
  }
}

async function saveRealtimeTrace(session, path) {
  const complete = new Promise((resolve) => session.once("Tracing.tracingComplete", resolve));
  await session.send("Tracing.end");
  const { stream, dataLossOccurred } = await complete;
  const file = openSync(path, "w");
  try {
    for (;;) {
      const { data, base64Encoded, eof } = await session.send("IO.read", { handle: stream, size: 65536 });
      writeSync(file, Buffer.from(data, base64Encoded ? "base64" : "utf8"));
      if (eof) break;
    }
  } finally {
    closeSync(file);
    await session.send("IO.close", { handle: stream });
  }
  return dataLossOccurred;
}

async function captureWithChromiumTrace(browser, path, categories, capture) {
  const session = await browser.newBrowserCDPSession();
  try {
    const browserEngine = await session.send("Browser.getVersion");
    await session.send("Tracing.start", {
      transferMode: "ReturnAsStream", traceConfig: { includedCategories: categories },
    });
    let result;
    let traceDataLoss;
    try {
      result = await capture();
    } finally {
      traceDataLoss = await saveRealtimeTrace(session, path);
    }
    return { ...result, browserEngine, traceDataLoss };
  } finally {
    await session.detach();
  }
}

async function captureReleaseAlignment(browser) {
  const { quantum_frames: quantum, profiles, capture_order: rounds } = measurement;
  const trials = [];
  for (const [index, order] of rounds.entries()) {
    const round = index + 1;
    for (const profile of order) {
      const { stop_quantum_index: stop, capture_quanta: count } = profiles[profile];
      const artifactId = `${round}-${profile}`;
      const dir = join(outDir, artifactId);
      mkdirSync(dir);
      try {
        const trial = {
          dir, stopFrame: stop * quantum, totalFrames: count * quantum,
          warmupCalls: measurement.wasm_render_warmup_calls,
          dspWarmupFrames: measurement.wasm_dsp_warmup_frames,
          finalizationProbe: measurement.finalization_probe,
          marker: measurement.marker && { ...measurement.marker, quantum },
        };
        const categories = measurement.trace_categories;
        const result = categories
          ? await captureWithChromiumTrace(browser, join(trial.dir, "trace.json"), categories,
            () => captureRealtime(browser, false, trial))
          : await captureRealtime(browser, false, trial);
        trials.push({ round, profile, artifactId, ...result });
      } catch (error) {
        trials.push({ round, profile, artifactId, error: String(error) });
      }
    }
  }
  return { version: browser.version(), trials };
}

const creatureActions = {
  "worklet-songbird-sustain": "持続音と停止を再生",
  "worklet-songbird-flute": "flute の途中停止を再生",
  "worklet-songbird-trill": "trillを再生",
  "worklet-songbird-trill-observation": "trillを再生",
  "worklet-songbird-chirps": "chirpsを再生",
  "worklet-songbird-buzz": "buzzを再生",
  "worklet-songbird-switch": "buzz → trillを再生",
  "worklet-seal-sustain": "持続音と停止を再生",
  "worklet-seal-trill": "trillを再生",
  "worklet-seal-zap": "zapを再生",
  "worklet-seal-whistle": "whistleを再生",
  "worklet-seal-chug": "chugを再生",
  "worklet-alligator-fixed-voice": "固定発声を再生",
  "worklet-alligator-bellow": "bellowを再生",
  "worklet-alligator-growl": "growlを再生",
  "worklet-alligator-hiss": "hissを再生",
  "worklet-alligator-dance": "danceを再生",
  "worklet-elephant-fixed-voice": "固定発声を再生",
  "worklet-elephant-rumble": "rumbleを再生",
  "worklet-elephant-trumpet": "trumpetを再生",
  "worklet-elephant-squeak": "squeakを再生",
};

async function captureCreature(browser, variant, experiment, artifactId = variant) {
  const page = await browser.newPage({ viewport: { width: 960, height: 760 }, acceptDownloads: true });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") {
      const url = message.location().url;
      errors.push(url ? `${url} ${message.text()}` : message.text());
    }
  });
  try {
    await page.goto(url);
    const ratePanels = {
      "worklet-seal-sustain": "ウェッデルアザラシの持続音",
      "worklet-seal-trill": "ウェッデルアザラシの trill",
      "worklet-seal-zap": "ウェッデルアザラシの zap",
      "worklet-seal-whistle": "ウェッデルアザラシの whistle",
      "worklet-seal-chug": "ウェッデルアザラシの chug",
      "worklet-songbird-sustain": "鳴禽の持続音",
    };
    const casePanels = {
      "worklet-alligator-fixed-voice": "アメリカアリゲーターの固定発声",
      "worklet-alligator-bellow": "アメリカアリゲーターの bellow",
      "worklet-alligator-growl": "アメリカアリゲーターの growl",
      "worklet-alligator-hiss": "アメリカアリゲーターの hiss",
      "worklet-alligator-dance": "アメリカアリゲーターの dance",
      "worklet-elephant-fixed-voice": "アフリカゾウの固定発声",
      "worklet-elephant-rumble": "アフリカゾウの rumble",
      "worklet-elephant-trumpet": "アフリカゾウの trumpet",
      "worklet-elephant-squeak": "アフリカゾウの squeak",
    };
    const name = ratePanels[experiment] ?? casePanels[experiment] ?? "鳴禽のコール";
    const panel = page.getByRole("region", { name, exact: true });
    const button = panel.getByRole("button", { name: creatureActions[experiment], exact: true });
    await panel.getByLabel(ratePanels[experiment] ? "出力サンプルレート" : "再生ケース").selectOption(variant);
    const response = page.waitForResponse((r) => r.ok() && new URL(r.url()).pathname.endsWith(".wasm"));
    await button.click();
    const hash = createHash("sha256").update(await (await response).body()).digest("hex");
    const complete = panel.getByText("実時間計測完了", { exact: true });
    const alert = panel.getByRole("alert");
    await complete.or(alert).waitFor({ timeout: 18000 });
    if (await alert.isVisible()) throw new Error(await alert.textContent());
    for (const [label, ext] of [
      ["WAVを保存", ".wav"], ["観測JSONを保存", ".json"], ["再実行ケースを保存", "-case.json"],
    ]) {
      const download = page.waitForEvent("download");
      await panel.getByRole("link", { name: label, exact: true }).click();
      await (await download).saveAs(join(outDir, artifactId + ext));
    }
    const audio = panel.getByLabel("レンダー音声の試聴");
    await page.waitForFunction((element) => Number.isFinite(element.duration), await audio.elementHandle());
    const audioDuration = await audio.evaluate((element) => element.duration);
    await panel.screenshot({ path: join(outDir, artifactId + ".png") });
    return { servedWasmSha256: hash, audioDuration, errors, controlsReset: await button.isEnabled() };
  } catch (error) {
    writeFileSync(join(outDir, artifactId + "-browser-error.json"),
      JSON.stringify({ message: String(error), errors }, null, 2) + "\n");
    throw error;
  } finally {
    await page.close();
  }
}

async function captureIpaTimeline(page, panel, options) {
  const timeline = panel.getByRole("region", { name: "発話の時系列", exact: true });
  const graph = timeline.getByRole("img", { name: "音素区間・口唇断面積・PCM波形", exact: true });
  const slider = timeline.getByRole("slider", { name: "出力フレーム", exact: true });
  const read = () => timeline.evaluate((section) => {
    const item = (name) => section.querySelector(`[data-timeline-${name}]`);
    return {
      frame: item("frame").textContent,
      time: item("time").textContent,
      phoneme: item("phone").textContent,
      observation: item("observation").textContent,
      area: item("area").textContent,
      cursorX: Number(item("cursor").getAttribute("x1")),
      slider: section.querySelector("input").valueAsNumber,
    };
  });
  const views = [];
  for (const viewportWidth of options.viewport_widths_css_px) {
    await page.setViewportSize({ width: viewportWidth, height: 950 });
    await graph.scrollIntoViewIfNeeded();
    await page.waitForFunction((element) => Math.abs(element.viewBox.baseVal.width - element.clientWidth) <= 1,
      await graph.elementHandle());
    const plot = await graph.evaluate((svg) => {
      const attr = (selector, name) => svg.querySelector(selector).getAttribute(name);
      const range = (rect) => [Number(rect.getAttribute("x")), Number(rect.getAttribute("width"))];
      return {
        width: svg.viewBox.baseVal.width,
        cssWidth: svg.getBoundingClientRect().width,
        left: Number(attr("[data-timeline-axis]", "x1")),
        right: Number(attr("[data-timeline-axis]", "x2")),
        phonemes: [...svg.querySelectorAll("[data-phone]")].map((rect) => [rect.dataset.phone, ...range(rect)]),
        closures: [...svg.querySelectorAll("[data-lip-closed]")].map(range),
        lipPoints: attr("[data-lip-series]", "points"),
        pcmPath: attr("[data-pcm-envelope]", "d"),
      };
    });
    const keyboard = [];
    for (const key of ["Home", "End", "ArrowLeft"]) {
      await slider.press(key);
      keyboard.push({ key, ...await read() });
    }
    await graph.scrollIntoViewIfNeeded();
    const bounding = await graph.boundingBox();
    const pointer = [];
    for (const fraction of options.cursor_fractions) {
      const x = plot.left + fraction * (plot.right - plot.left);
      await page.mouse.click(bounding.x + x * bounding.width / plot.width, bounding.y + bounding.height / 2);
      pointer.push({ fraction, ...await read() });
    }
    views.push({ viewportWidth, plot, keyboard, pointer });
    await timeline.screenshot({ path: join(outDir, `timeline-${viewportWidth}.png`) });
  }
  writeFileSync(join(outDir, "timeline.json"), JSON.stringify(views, null, 2) + "\n");
}

async function captureTractProfile(page, panel, options, acoustics) {
  const slider = panel.getByRole("slider", { name: "出力フレーム", exact: true });
  const section = panel.getByRole("region", { name: "声道断面", exact: true });
  const views = [];
  for (const viewportWidth of options.viewport_widths_css_px) {
    await page.setViewportSize({ width: viewportWidth, height: 950 });
    const selections = [];
    for (const frame of options.selected_output_frames) {
      await selectFrame(slider, frame);
      const result = await section.evaluate((element) => {
        const observed = element.querySelector("[data-tract-frame]");
        const svg = element.querySelector("svg");
        if (!observed || !svg) {
          return { observedFrame: null, missing: Boolean(element.querySelector("[data-tract-missing]")), plot: null };
        }
        const attrs = (node, keys) => keys.map((key) => Number(node.getAttribute(key)));
        const rectangles = (selector) => [...svg.querySelectorAll(selector)].map((node) =>
          attrs(node, ["x", "width", "y", "height"]));
        return {
          observedFrame: Number(observed.textContent), missing: false,
          plot: {
            cssWidth: svg.getBoundingClientRect().width,
            xAxis: attrs(svg.querySelector("[data-tract-x-axis]"), ["x1", "x2"]),
            yAxis: attrs(svg.querySelector("[data-tract-y-axis]"), ["y1", "y2"]),
            average: rectangles("[data-tract-average]"),
            minimum: rectangles("[data-tract-minimum]"),
          },
        };
      });
      const selected = await panel.locator("[data-timeline-frame]").textContent();
      if (acoustics && result.plot) {
        result.acoustics = await section.evaluate((element) => {
          return Object.fromEntries(["pressure", "flow"].map((name) => {
            const numbers = (node, keys) => keys.map((key) => Number(node.getAttribute(key)));
            const zero = element.querySelector(`[data-acoustic-zero="${name}"]`);
            const range = element.querySelector(`[data-acoustic-range="${name}"]`);
            const points = [...element.querySelectorAll(`[data-acoustic-point="${name}"]`)];
            return [name, { zero: numbers(zero, ["y1"])[0], range: numbers(range, ["y1", "y2"]),
              points: points.map((point) => numbers(point, ["cx", "cy"])) }];
          }));
        });
        const menu = section.getByRole("combobox", { name: "観測セル", exact: true });
        const [pharynx, oral] = options.expected_tube_cell_counts;
        result.cellReadouts = [];
        for (const index of [pharynx - 1, pharynx, pharynx + oral - 1]) {
          await menu.selectOption(String(index));
          result.cellReadouts.push({
            index,
            pressure: await section.locator('[data-acoustic-value="pressure"]').textContent(),
            flow: await section.locator('[data-acoustic-value="flow"]').textContent(),
          });
        }
      }
      selections.push({ selected: Number(selected), ...result });
      if (result.observedFrame === options.closed_profile_frame) {
        await section.screenshot({ path: join(outDir, `profile-${viewportWidth}-closed.png`) });
      } else if (result.observedFrame === options.open_profile_frame) {
        await section.screenshot({ path: join(outDir, `profile-${viewportWidth}-open.png`) });
      }
    }
    views.push({ viewportWidth, selections });
  }
  writeFileSync(join(outDir, "tract-display.json"), JSON.stringify(views, null, 2) + "\n");
}

async function selectFrame(slider, frame) {
  // 入力欄の通常のイベントを通して、指定した出力フレームへ移動する。
  await slider.evaluate((input, value) => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(input, String(value));
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }, frame);
}

async function captureSpeechTract3D(page, panel, options) {
  const slider = panel.getByRole("slider", { name: "出力フレーム", exact: true });
  const section = panel.getByRole("region", { name: "発話の三次元断面", exact: true });
  const profile = panel.getByRole("region", { name: "声道断面", exact: true });
  const image = section.getByRole("img", { name: "観測時刻の声道の楕円断面", exact: true });
  const link = section.getByRole("link", { name: "発話の三次元観測JSONを保存", exact: true });
  const views = [];
  for (const width of options.viewport_widths_css_px) {
    await page.setViewportSize({ width, height: 950 });
    await selectFrame(slider, options.unobserved_output_frame);
    await section.locator("[data-speech-grid-missing]").waitFor();
    const absent = await link.count() === 0 && !await image.isVisible();
    const frames = [];
    for (const trial of options.frames) {
      await selectFrame(slider, trial.selected_output_frame);
      const expected = section.locator(`[data-speech-grid-frame="${trial.expected_observed_frame}"]`);
      const error = section.getByRole("alert");
      await expected.or(error).waitFor({ timeout: 10000 });
      if (await error.isVisible()) throw new Error(await error.textContent());
      const renderer = await image.evaluate((canvas) => {
        const gl = canvas.getContext("webgl2");
        window.chimeraTractContext ??= gl;
        return { ready: Boolean(gl && !gl.isContextLost()), sameContext: gl === window.chimeraTractContext,
          width: canvas.clientWidth, height: canvas.clientHeight };
      });
      const selectedFrame = Number(await panel.locator("[data-timeline-frame]").textContent());
      const acousticFrame = Number(await profile.locator("[data-tract-frame]").textContent());
      const basename = `tract-3d-${width}-${trial.id}`;
      for (const [view, label] of [["angled", "斜め"], ["side", "側面"]]) {
        await section.getByRole("button", { name: label, exact: true }).click();
        await image.screenshot({ path: join(outDir, `${basename}-${view}.png`) });
        const [download] = await Promise.all([page.waitForEvent("download"), link.click()]);
        await download.saveAs(join(outDir, `${basename}-${view}.json`));
      }
      if (width === options.viewport_widths_css_px[0] && trial.id === "closed") {
        await section.screenshot({ path: join(outDir, "tract-3d-closed-section.png") });
      }
      frames.push({ ...trial, selectedFrame, acousticFrame, renderer });
    }
    views.push({ width, absent, frames });
  }
  writeFileSync(join(outDir, "tract-3d-dynamic-display.json"), JSON.stringify(views, null, 2) + "\n");
}

async function captureGlottalScope(page, panel, options) {
  const slider = panel.getByRole("slider", { name: "出力フレーム", exact: true });
  const section = panel.getByRole("region", { name: "声門波形", exact: true });
  const views = [];
  for (const viewportWidth of options.viewport_widths_css_px) {
    await page.setViewportSize({ width: viewportWidth, height: 950 });
    const selections = [];
    for (const frame of options.selected_frames) {
      await selectFrame(slider, frame);
      const actual = await section.evaluate((element) => {
        const attr = (selector, names) => names.map((name) => Number(element.querySelector(selector).getAttribute(name)));
        const tracks = Object.fromEntries(["area", "flow"].map((name) => [
          name,
          {
            x: attr(`[data-scope-axis="${name}"]`, ["x1", "x2"]),
            zero: attr(`[data-scope-axis="${name}"]`, ["y1"])[0],
            range: attr(`[data-scope-range="${name}"]`, ["y1", "y2"]),
            points: element.querySelector(`[data-scope-wave="${name}"]`).getAttribute("points"),
            readout: element.querySelector(`[data-scope-value="${name}"]`).textContent,
          },
        ]));
        return {
          frame: Number(element.dataset.glottalFrame),
          first: Number(element.dataset.glottalFirst),
          last: Number(element.dataset.glottalLast),
          cursor: attr("[data-scope-cursor]", ["x1"])[0],
          width: element.querySelector("svg").getBoundingClientRect().width,
          tracks,
        };
      });
      selections.push({ requested: frame, ...actual });
      if (frame === options.voiced_frame || frame === options.closure_frame) {
        const label = frame === options.voiced_frame ? "voiced" : "closure";
        await section.screenshot({ path: join(outDir, `scope-${viewportWidth}-${label}.png`) });
      }
    }
    views.push({ viewportWidth, selections });
  }
  writeFileSync(join(outDir, "glottal-scope.json"), JSON.stringify(views, null, 2) + "\n");
}

async function capturePcmSpectrum(page, panel, options, viewportWidth) {
  const slider = panel.getByRole("slider", { name: "出力フレーム", exact: true });
  const section = panel.getByRole("region", { name: "PCMスペクトル", exact: true });
  const save = section.getByRole("link", { name: "スペクトルJSONを保存", exact: true });
  const selections = [];
  for (const frame of options.selected_frames) {
    await selectFrame(slider, frame);
    const actual = await section.evaluate((element) => {
      const axis = element.querySelector("[data-spectrum-axis]");
      return {
        frame: Number(element.dataset.spectrumFrame),
        width: element.querySelector("svg").getBoundingClientRect().width,
        axis: ["x", "y", "width", "height"].map((key) => Number(axis.getAttribute(key))),
        source: element.querySelector("[data-spectrum-source]").textContent,
        samples: element.querySelector("[data-spectrum-samples]").textContent,
        peak: element.querySelector("[data-spectrum-peak]").textContent.trim(),
        points: element.querySelector("[data-spectrum-line]").getAttribute("points"),
      };
    });
    const [download] = await Promise.all([page.waitForEvent("download"), save.click()]);
    const filename = `spectrum-${viewportWidth}-${frame}.json`;
    await download.saveAs(join(outDir, filename));
    selections.push({ requested: frame, ...actual, filename, browserFilename: download.suggestedFilename() });
    if (frame === options.voiced_frame || frame === options.closure_frame) {
      const label = frame === options.voiced_frame ? "voiced" : "closure";
      await section.screenshot({ path: join(outDir, `spectrum-${viewportWidth}-${label}.png`) });
    }
  }
  return { viewportWidth, selections };
}

async function selectVoiceBody(panel, body) {
  await panel.getByRole("combobox", { name: "体型", exact: true })
    .selectOption(typeof body === "string" ? body : "mix");
  if (typeof body === "object") {
    await panel.getByRole("spinbutton", { name: "成人内の女性比", exact: true }).fill(String(body.female));
    await panel.getByRole("spinbutton", { name: "子ども比", exact: true }).fill(String(body.child));
  }
}

async function captureLiveTractBodies(browser, spec) {
  const results = [];
  for (const [viewportIndex, width] of spec.measurement.viewport_widths_css_px.entries()) {
    const page = await browser.newPage({ viewport: { width, height: 950 }, acceptDownloads: true });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("console", (entry) => { if (entry.type() === "error") errors.push(entry.text()); });
    const result = { width, trials: [], errors };
    try {
      await page.addInitScript(observeLiveTract, {
        geometry: { ...spec.measurement, before_frame: 8 * spec.measurement.profile_stride_output_frames - 1 },
      });
      await page.goto(url);
      const panel = page.getByRole("region", { name: "IPA発話", exact: true });
      await panel.getByRole("textbox", { name: "IPA", exact: true }).fill(spec.input.ipa);
      await panel.getByRole("checkbox", { name: "三次元断面を観測する" }).check();
      const start = panel.getByRole("button", { name: "IPAを実時間で発声", exact: true });
      const done = panel.getByText("実時間のIPA発話完了", { exact: true });
      const livePanel = panel.getByRole("region", { name: "実時間の三次元断面", exact: true, includeHidden: true });
      const variants = viewportIndex % 2 === 0 ? spec.input.bodies : spec.input.bodies.toReversed();
      for (const [run, variant] of variants.entries()) {
        await selectVoiceBody(panel, variant.body);
        const wasm = page.waitForResponse((r) => r.ok() && new URL(r.url()).pathname.endsWith(".wasm"));
        await start.click();
        const servedWasmSha256 = createHash("sha256").update(await (await wasm).body()).digest("hex");
        await done.waitFor();
        await page.waitForFunction((run) => window.liveTractEvidence.runs[run]?.contextClosedAtMs != null, run);
        const stem = `${width}-${variant.id}`;
        for (const [name, suffix] of [["WAVを保存", ".wav"], ["観測JSONを保存", ".json"], ["再実行ケースを保存", "-case.json"]]) {
          const [download] = await Promise.all([page.waitForEvent("download"), panel.getByRole("link", { name, exact: true }).click()]);
          await download.saveAs(join(outDir, stem + suffix));
        }
        const released = await livePanel.locator("canvas").evaluate((canvas) => {
          let response;
          canvas.dispatchEvent(new CustomEvent("chimera:read-live-tract", { detail: (value) => { response = value; } }));
          return response === undefined && !canvas.closest("section").querySelector("[data-live-context-frame]");
        });
        result.trials.push({ run, label: variant.id, stem, servedWasmSha256, released });
      }
      results.push(result);
    } finally {
      const evidence = await page.evaluate(() => window.liveTractEvidence).catch(() => null);
      writeFileSync(join(outDir, `${width}-bodies-live.json`), JSON.stringify({ ...result, evidence }) + "\n");
      await page.close();
    }
  }
  return { version: browser.version(), viewports: results };
}

async function captureSpeech(browser, {
  timeline, english, ipa, profile, acoustics, scope, spectrum, live = false, viewportWidth = 960, saveOutput = true,
  artifactPrefix = "browser", voiceSelection, dynamic3d, live3d, exerciseStop = true, englishCase, traceSpeechPhases = false,
  traceSpeechWasmCore = false, speechWasm, speechPreparation, delaySpeechOneQuantum = false, saveOfflineBeforeLive = false,
} = {}) {
  const page = await browser.newPage({ viewport: { width: viewportWidth, height: 950 }, acceptDownloads: true });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  try {
    if (live3d) await page.addInitScript(observeLiveTract, live3d);
    if (live && speechMarker) {
      await installMeasuredMarker(page, speechMarker, speechMarker.waitForSystemTrace);
    }
    if (live && englishCase) {
      await page.addInitScript(() => {
        const compile = WebAssembly.compile;
        window.englishSpeechWasm = [];
        window.englishPagePlannerInstances = 0;
        WebAssembly.Instance = class extends WebAssembly.Instance {
          constructor(...args) {
            super(...args);
            if ("vocal_english_plan_with_body" in this.exports) window.englishPagePlannerInstances += 1;
          }
        };
        WebAssembly.compile = function (bytes, ...options) {
          // キャッシュされた取得も、計画器に渡るWASMバイト列から照合する。
          window.englishSpeechWasm.push(crypto.subtle.digest("SHA-256", bytes).then(
            (hash) => Array.from(new Uint8Array(hash), (byte) => byte.toString(16).padStart(2, "0")).join(""),
          ));
          return compile.call(this, bytes, ...options);
        };
        const connect = AudioWorkletNode.prototype.connect;
        AudioWorkletNode.prototype.connect = function (...args) {
          const result = connect.apply(this, args);
          if (this.context instanceof AudioContext) {
            window.englishSpeechConnection = { context: this.context, connectedAt: this.context.currentTime };
          }
          return result;
        };
      });
    }
    const speechUrl = new URL(url);
    if (traceSpeechPhases) speechUrl.searchParams.set("speechRenderPhases", "1");
    if (traceSpeechWasmCore) speechUrl.searchParams.set("speechWasmCore", "1");
    if (speechPreparation) speechUrl.searchParams.set("speechRenderPreparation", speechPreparation);
    if (delaySpeechOneQuantum) speechUrl.searchParams.set("speechDelayOneQuantum", "1");
    if (speechWasm) {
      await page.route((asset) => asset.pathname.endsWith(".wasm"), (route) =>
        route.fulfill({ path: speechWasm, contentType: "application/wasm" }));
    }
    await page.goto(speechUrl.href);
    const panel = page.getByRole("region", { name: english ? "英語発話" : "IPA発話", exact: true });
    const input = panel.getByRole("textbox", { name: english ? "英語テキスト" : "IPA", exact: true });
    const render = panel.getByRole("button", {
      name: live ? (english ? "読み込んだケースを実時間で発声" : "IPAを実時間で発声") :
        english ? "英語をレンダー" : "IPAをレンダー", exact: true,
    });
    if (voiceSelection) {
      const { body, f0_hz: pitch } = voiceSelection;
      await selectVoiceBody(panel, body);
      await panel.getByRole("spinbutton", { name: "基準F0（Hz）", exact: true }).fill(pitch === undefined ? "" : String(pitch));
    }
    const dictionary = english && page.waitForResponse((r) => r.ok() && isDictionary(r.url()));
    const offlineComplete = panel.getByText("発話レンダー完了", { exact: true });
    const complete = live ? panel.getByText(english ? "実時間の英語発話完了" : "実時間のIPA発話完了",
      { exact: true }) : offlineComplete;
    const alert = panel.getByRole("alert");
    const unrenderable = english ? measurement.unrenderable_text : measurement.check_unrenderable_ipa_then_recover && "ʘ";
    const response = page.waitForResponse((r) => r.ok() && new URL(r.url()).pathname.endsWith(".wasm"));
    let rejected = null;
    if (unrenderable) {
      await input.fill(unrenderable);
      await render.click();
      await alert.or(complete).first().waitFor();
      if (await complete.isVisible()) throw new Error(`拒否を期待した入力がレンダーされました (${unrenderable})`);
      rejected = await alert.textContent();
    }
    let offlineWasmSha256;
    if (englishCase) {
      await panel.getByLabel("英語発話ケースをレンダー", { exact: true }).setInputFiles(englishCase);
      await alert.or(offlineComplete).first().waitFor();
      if (await alert.isVisible()) throw new Error(await alert.textContent());
      if (live) {
        if (saveOfflineBeforeLive) {
          for (const [name, ext] of [["WAVを保存", "wav"], ["観測JSONを保存", "json"]]) {
            const download = page.waitForEvent("download");
            await panel.getByRole("link", { name, exact: true }).click();
            await (await download).saveAs(join(outDir, `offline.${ext}`));
          }
        }
        offlineWasmSha256 = createHash("sha256").update(await (await response).body()).digest("hex");
        if (speechMarker?.trace_before_playback) await prepareSpeechTrace(page, speechMarker);
        await render.click();
      }
    } else {
      await input.fill(english ?? ipa ?? measurement.expected_ipa);
      if (dynamic3d || live3d) {
        await panel.getByRole("checkbox", { name: "三次元断面を観測する" }).check();
      }
      await render.click();
    }
    const hash = createHash("sha256").update(await (await response).body()).digest("hex");
    if (!live3d) await panel.getByRole("status").waitFor();
    await complete.waitFor();
    if (live && speechMarker) await saveSharedContextMarker(page, outDir);
    const compiledWasm = live && englishCase
      ? await page.evaluate(() => Promise.all(window.englishSpeechWasm)) : undefined;
    const pagePlannerInstances = live && englishCase
      ? await page.evaluate(() => window.englishPagePlannerInstances) : undefined;
    let replayFilename;
    if (saveOutput) {
      for (const [name, ext] of [["WAVを保存", "wav"], ["観測JSONを保存", "json"]]) {
        const download = page.waitForEvent("download");
        await panel.getByRole("link", { name, exact: true }).click();
        await (await download).saveAs(join(outDir, `${artifactPrefix}.${ext}`));
      }
      if (voiceSelection || englishCase) {
        const link = panel.getByRole("link", { name: "再実行ケースを保存", exact: true });
        const [download] = await Promise.all([page.waitForEvent("download"), link.click()]);
        replayFilename = download.suggestedFilename();
        await download.saveAs(join(outDir, `${artifactPrefix}-case.json`));
      }
    }
    if (timeline) await captureIpaTimeline(page, panel, timeline);
    if (profile) await captureTractProfile(page, panel, profile, acoustics);
    if (dynamic3d) await captureSpeechTract3D(page, panel, dynamic3d);
    if (scope) await captureGlottalScope(page, panel, scope);
    const spectrumView = spectrum && await capturePcmSpectrum(page, panel, spectrum, viewportWidth);
    const englishDetails = dictionary ? {
      ...await dictionaryEvidence(await dictionary),
      shown: await panel.locator("[data-speech-transcript]").textContent(),
    } : {};
    if (saveOutput) {
      if (english) await panel.screenshot({ path: join(outDir, `${artifactPrefix}.png`) });
      else await page.screenshot({ path: join(outDir, `${artifactPrefix}.png`) });
    }
    const recovered = await panel.getByRole("alert").count() === 0;
    let stopped;
    let stopAudioClockSeconds;
    if (live && exerciseStop) {
      if (englishCase) await page.evaluate(() => { window.englishSpeechConnection = undefined; });
      await render.click();
      if (live3d) await page.waitForFunction(() => window.liveTractEvidence.packets.some((packet) => packet.run === 1));
      if (englishCase) {
        await page.waitForFunction(() => {
          const c = window.englishSpeechConnection;
          return c && c.context.state === "running" && c.context.currentTime - c.connectedAt >= 0.2;
        });
        stopAudioClockSeconds = await page.evaluate(() => window.englishSpeechConnection.context.currentTime);
      }
      await panel.getByRole("button", { name: english ? "英語を停止" : "IPAを停止", exact: true }).click();
      await panel.getByRole("status").waitFor({ state: "hidden" });
      if (englishCase) await page.waitForFunction(() => window.englishSpeechConnection.context.state === "closed");
      stopped = await render.isEnabled() && await input.isEnabled() && await panel.getByRole("alert").count() === 0;
    }
    if (live3d) {
      await page.waitForFunction(() => window.liveTractEvidence.runs[1]?.contextClosedAtMs != null);
      const evidence = await page.evaluate(() => window.liveTractEvidence);
      evidence.previewCleared = await panel.locator("[data-live-context-frame]").count() === 0;
      writeFileSync(join(outDir, `${artifactPrefix}-live-tract.json`), JSON.stringify(evidence) + "\n");
    }
    return { version: browser.version(), engine: browser.browserType().name(), servedWasmSha256: hash, errors, rejected,
      recovered, ...(live && { stopped }), ...englishDetails,
      ...(offlineWasmSha256 && { offlineWasmSha256, compiledWasm, pagePlannerInstances, stopAudioClockSeconds }),
      ...(replayFilename && { replayFilename }),
      ...(spectrumView && { spectrumView }) };
  } catch (error) {
    if (live) {
      const alerts = await page.getByRole("alert").allTextContents();
      writeFileSync(join(outDir, `${artifactPrefix}-error.json`), JSON.stringify({ message: String(error), alerts, errors }) + "\n");
    }
    if (live3d) {
      const evidence = await page.evaluate(() => window.liveTractEvidence).catch(() => null);
      writeFileSync(join(outDir, `${artifactPrefix}-live-tract-error.json`),
        JSON.stringify({ message: String(error), errors, evidence }) + "\n");
    }
    throw error;
  } finally {
    await page.close();
  }
}

async function captureSpectrumViews(browser, options) {
  let evidence;
  const views = [];
  for (const viewportWidth of options.viewport_widths_css_px) {
    // 各幅の画面を独立した発話レンダーから検査する。
    const { spectrumView, ...result } = await captureSpeech(browser, {
      spectrum: options, viewportWidth, saveOutput: views.length === 0,
    });
    views.push(spectrumView);
    evidence ??= result;
    if (result.servedWasmSha256 !== evidence.servedWasmSha256 || !result.recovered || result.errors.length) {
      throw new Error("幅ごとのWASMまたはレンダー結果が一致しません");
    }
  }
  writeFileSync(join(outDir, "pcm-spectrum.json"), JSON.stringify(views, null, 2) + "\n");
  return evidence;
}

const isDictionary = (url) => /\/cmudict[^/]*\.gz$/.test(new URL(url).pathname);

async function dictionaryEvidence(response) {
  const bytes = await response.body();
  return {
    dictionaryResponseSha256: createHash("sha256").update(bytes).digest("hex"),
    dictionaryContentEncoding: await response.headerValue("content-encoding"),
    dictionaryResponseIsGzip: bytes[0] === 0x1f && bytes[1] === 0x8b,
  };
}

function holdSongRegistration() {
  const resume = AudioContext.prototype.resume;
  AudioContext.prototype.resume = function (...args) {
    const result = resume.apply(this, args);
    if (window.holdNextSongRegistration) {
      window.holdNextSongRegistration = false;
      const context = this;
      Object.defineProperty(context.audioWorklet, "addModule", { value: () => new Promise((_resolve, reject) => {
        window.heldSongRegistration = { context, reject };
      }) });
    }
    return result;
  };
  window.songRegistrationRejections = [];
  window.addEventListener("unhandledrejection", (event) => window.songRegistrationRejections.push(String(event.reason)));
}

async function waitForSystemTrace(ready) {
  writeFileSync(join(outDir, "trace-ready.json"), JSON.stringify({ ...ready, nodeEpochMs: Date.now() }), { flag: "wx" });
  const deadline = performance.now() + 15_000;
  while (!existsSync(join(outDir, "trace-release.json"))) {
    if (performance.now() >= deadline) throw new Error("収録の開始通知を受け取れません");
    await delay(5);
  }
}

async function prepareSpeechTrace(page, marker) {
  const rate = marker.tap_prime_sample_rate_hz;
  if (!rate) return waitForSystemTrace({ beforePlayback: true });
  try {
    await page.evaluate((sampleRate) => {
      // 再生前に親プロセスをCore Audioへ登録するための無音Context。
      const context = new AudioContext({ sampleRate });
      const source = context.createConstantSource();
      source.offset.value = 0;
      source.connect(context.destination);
      source.start();
      window.chimeraTapPrimingContext = context;
      void context.resume().catch(() => {});
    }, rate);
    await page.waitForFunction(() => {
      const context = window.chimeraTapPrimingContext;
      return context.state === "running" && context.currentTime > 0;
    }, undefined, { timeout: 3000 });
    const tapPrimingFrame = await page.evaluate(() => {
      const context = window.chimeraTapPrimingContext;
      return Math.round(context.currentTime * context.sampleRate);
    });
    await waitForSystemTrace({ beforePlayback: true, tapPrimingFrame, tapPrimingSampleRate: rate });
  } finally {
    await page.evaluate(async () => {
      const context = window.chimeraTapPrimingContext;
      delete window.chimeraTapPrimingContext;
      if (context) await context.close();
    });
  }
}

async function installMeasuredMarker(page, marker, trace, beforeMarker = "") {
  if (trace) await page.exposeFunction("chimeraWaitForSystemTrace", waitForSystemTrace);
  const settings = { ...marker, moduleName: "fixed-processor-entry", waitForSystemTrace: trace };
  if (beforeMarker || settings.smooth_marker) {
    await page.addInitScript({ content: `${beforeMarker}\n(${installSharedContextMarker})(${JSON.stringify(settings)}, (${smoothMarkerPCM}));` });
  } else {
    await page.addInitScript(installSharedContextMarker, settings);
  }
}

async function captureSong(browser, score, { rawDictionary, live, artifactPrefix = "browser", body, preset,
  turbulence, warmUpFrames, unrenderableLyrics = "..." } = {}) {
  const page = await browser.newPage({ viewport: { width: 960, height: 980 }, acceptDownloads: true });
  const firstWorkletRequest = workletRequests.length;
  const stopTest = live && !live.profiler_capture_only && !live.single_song_capture;
  const errors = [];
  let dictionaryRequests = 0;
  page.on("request", (request) => {
    if (isDictionary(request.url())) dictionaryRequests++;
  });
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  try {
    if (live?.record_click_epoch) {
      await page.addInitScript(() => {
        document.addEventListener("click", (event) => {
          if (event.isTrusted && event.target.closest?.("button")?.textContent === "実時間で歌唱") {
            window.chimeraSongClickEpochMs = Date.now();
          }
        }, { capture: true });
      });
    }
    const marker = live?.shared_context_marker;
    if (marker) {
      // 同じスクリプトで初期化し、歌唱の読取ノードを用意してから先行信号を流す。
      const output = live.output_probe ? `(${installSongOutputProbe})(${JSON.stringify(live.output_probe)});` : "";
      await installMeasuredMarker(page, marker, live.trace_shared_context, output);
    } else if (live?.output_probe) {
      await page.addInitScript(installSongOutputProbe, live.output_probe);
    }
    if (stopTest) {
      await page.addInitScript(() => {
        const connect = AudioWorkletNode.prototype.connect;
        AudioWorkletNode.prototype.connect = function (...args) {
          const result = connect.apply(this, args);
          if (this.context instanceof AudioContext) {
            window.songConnection = { context: this.context, time: this.context.currentTime };
          }
          return result;
        };
      });
    }
    if (live?.stop_during_registration) await page.addInitScript(holdSongRegistration);
    if (rawDictionary) {
      await page.route((url) => isDictionary(url), (route) =>
        route.fulfill({ contentType: "application/gzip", body: readFileSync(rawDictionary) }));
    }
    const songUrl = new URL(url);
    if (live?.trace_startup) songUrl.searchParams.set("songStartupTrace", "1");
    if (live?.register_before_resume) songUrl.searchParams.set("songRegisterBeforeResume", "1");
    if (live?.silent_lead_quanta !== undefined) songUrl.searchParams.set("songSilentLead", String(live.silent_lead_quanta));
    if (live?.trace_silent_lead_input) songUrl.searchParams.set("songSilentLeadTrace", "1");
    if (live?.native_silent_lead_trace_categories) songUrl.searchParams.set("songSilentLeadNativeTrace", "1");
    if (live?.parallel_silent_lead_registration) songUrl.searchParams.set("songSilentLeadRegistration", "parallel");
    await page.goto(songUrl.href);
    const panel = page.getByRole("region", { name: "歌唱", exact: true });
    if (preset) await panel.getByRole("combobox", { name: "歌唱プリセット", exact: true }).selectOption(preset);
    if (warmUpFrames !== undefined) {
      await panel.getByRole("spinbutton", { name: "予約前の描画フレーム数", exact: true }).fill(String(warmUpFrames));
    }
    const structured = Array.isArray(score.syllables);
    if (structured) {
      await panel.getByRole("combobox", { name: "音節の入力形式", exact: true }).selectOption("syllables");
    }
    const syllables = panel.getByRole("textbox", { name: structured ? "IPA音節 JSON" : "歌詞（英語・韓国語・ロシア語・中国語）", exact: true });
    if (body) await selectVoiceBody(panel, body);
    const render = panel.getByRole("button", { name: live ? "実時間で歌唱" : "歌唱をレンダー", exact: true });
    await panel.getByRole("spinbutton", { name: "テンポ（BPM）" }).fill(String(score.bpm));
    await panel.getByRole("spinbutton", { name: "ビブラート（セント）" }).fill(String(score.vibrato_cents));
    if (turbulence) {
      await panel.getByRole("spinbutton", { name: "乱流係数", exact: true }).fill(String(turbulence.scale));
      const sourceControls = [
        ["声門の乱流ゲイン倍率", turbulence.glottis_gain_multiplier],
        ["狭窄の乱流ゲイン倍率", turbulence.constriction_gain_multiplier],
        ["歯の乱流の低域通過周波数の下限（Hz）", turbulence.teeth_lowpass_floor_hz],
      ].filter(([, value]) => value !== undefined);
      if (sourceControls.length) {
        await panel.getByText("乱流源の設定", { exact: true }).click();
        for (const [name, value] of sourceControls) {
          await panel.getByRole("spinbutton", { name, exact: true }).fill(String(value));
        }
      }
    }
    await panel.getByRole("spinbutton", { name: "最初の拍（秒）" }).fill(String(score.start_seconds));
    await panel.getByRole("textbox", { name: "MIDI番号と拍数" }).fill(
      score.notes.map((note) => note.midi + " " + note.beats).join("\n"),
    );
    const complete = panel.getByText(live ? "実時間の歌唱完了" : "歌唱レンダー完了", { exact: true });
    const alert = panel.getByRole("alert");
    const response = page.waitForResponse((r) => r.ok() && new URL(r.url()).pathname.endsWith(".wasm"));
    const dictionary = structured ? undefined : page.waitForResponse((r) => r.ok() && isDictionary(r.url()));
    let rejected = null;
    if (!structured && measurement.check_unrenderable_lyric_then_recover && !live?.skip_invalid_lyrics) {
      await syllables.fill(unrenderableLyrics);
      await render.click();
      await alert.or(complete).first().waitFor();
      if (await complete.isVisible()) throw new Error(`拒否を期待した歌詞がレンダーされました (${unrenderableLyrics})`);
      rejected = await alert.textContent();
    }
    if (live?.parallel_registration || live?.trace_evaluation || live?.trace_native_registration
        || live?.trace_render_phases || live?.render_preparation) {
      await page.evaluate(({ parallel, evaluation, nativeRegistration, renderPhases, renderPreparation }) => {
        const address = new URL(location.href);
        if (parallel) address.searchParams.set("songParallelRegistration", "1");
        if (evaluation) address.searchParams.set("songModuleEvaluation", "1");
        if (nativeRegistration) address.searchParams.set("songNativeRegistrationTrace", "1");
        if (renderPhases) address.searchParams.set("songRenderPhaseTrace", "1");
        if (renderPreparation) address.searchParams.set("songRenderPreparation", renderPreparation);
        history.replaceState(history.state, "", address);
      }, { parallel: live.parallel_registration, evaluation: live.trace_evaluation,
        nativeRegistration: live.trace_native_registration, renderPhases: live.trace_render_phases,
        renderPreparation: live.render_preparation });
    }
    await syllables.fill(structured ? JSON.stringify(score.syllables) : score.lyrics);
    let beforeRegistrationStop;
    if (live?.stop_during_registration) {
      await page.evaluate(() => { window.holdNextSongRegistration = true; });
      await render.click();
      await page.waitForFunction(() => Boolean(window.heldSongRegistration));
      await panel.getByRole("button", { name: "歌唱を停止", exact: true }).click();
      await panel.getByRole("status").waitFor({ state: "hidden" });
      beforeRegistrationStop = await page.evaluate(() => {
        const { context, reject } = window.heldSongRegistration;
        const evidence = { contextState: context.state, connected: window.songConnection?.context === context };
        reject(new Error("停止後にWorkletの登録を拒否する対照"));
        window.heldSongRegistration = null;
        return evidence;
      });
      beforeRegistrationStop.ready = await render.isEnabled() && await syllables.isEnabled() && await alert.count() === 0;
    }
    await render.click();
    const hash = (bytes) => createHash("sha256").update(bytes).digest("hex");
    const [wasmResponse, dictionaryResponse] = await Promise.all([response, dictionary]);
    // Playwrightの応答本文の展開を実時間歌唱の計測区間から外す。
    const deferAssetEvidence = Boolean(live && live.defer_asset_evidence !== false);
    if (deferAssetEvidence) await complete.waitFor();
    const assetEvidenceStartedAt = live?.record_asset_evidence_timing ? Date.now() : undefined;
    const [wasmBytes, dictionaryDetails] = await Promise.all([
      wasmResponse.body(), dictionaryResponse && dictionaryEvidence(dictionaryResponse),
    ]);
    const assetEvidenceFinishedAt = assetEvidenceStartedAt === undefined ? undefined : Date.now();
    if (!deferAssetEvidence) await complete.waitFor();
    if (live?.shared_context_marker) await saveSharedContextMarker(page, outDir);
    for (const [name, ext] of [["WAVを保存", "wav"], ["観測JSONを保存", "json"]]) {
      const download = page.waitForEvent("download");
      await panel.getByRole("link", { name, exact: true }).click();
      await (await download).saveAs(join(outDir, `${artifactPrefix}.${ext}`));
    }
    let replayFilename;
    if (body || turbulence) {
      const link = panel.getByRole("link", { name: "再実行ケースを保存", exact: true });
      const [download] = await Promise.all([page.waitForEvent("download"), link.click()]);
      replayFilename = download.suggestedFilename();
      await download.saveAs(join(outDir, `${artifactPrefix}-case.json`));
    }
    await panel.screenshot({ path: join(outDir, `${artifactPrefix}.png`) });
    if (live?.output_probe) {
      const { pcm, ...timeline } = await page.evaluate(readSongOutputProbe);
      writeFileSync(join(outDir, "output-probe.f32le"), Buffer.from(pcm, "base64"));
      writeFileSync(join(outDir, "output-probe.json"), JSON.stringify(timeline, null, 2) + "\n");
    }
    const recovered = await panel.getByRole("alert").count() === 0;
    const clickEpochMs = live?.record_click_epoch ? await page.evaluate(() => window.chimeraSongClickEpochMs) : undefined;
    let stop;
    if (stopTest) {
      await page.evaluate(() => { window.songConnection = null; });
      await render.click();
      await page.waitForFunction((seconds) => {
        const connection = window.songConnection;
        return connection?.context.state === "running" &&
          connection.context.currentTime - connection.time >= seconds;
      }, live.stop_after_connected_seconds);
      const connectedSeconds = await page.evaluate(() => window.songConnection.context.currentTime - window.songConnection.time);
      await panel.getByRole("button", { name: "歌唱を停止", exact: true }).click();
      await panel.getByRole("status").waitFor({ state: "hidden" });
      const contextState = await page.evaluate(() => window.songConnection.context.state);
      stop = { connectedSeconds, contextState,
        ready: await render.isEnabled() && await syllables.isEnabled() && await panel.getByRole("alert").count() === 0 };
      await render.click();
      await complete.waitFor();
      stop.replayed = await panel.getByRole("alert").count() === 0;
    }
    if (beforeRegistrationStop) {
      beforeRegistrationStop.unhandled = await page.evaluate(() => window.songRegistrationRejections);
    }
    return { version: browser.version(), engine: browser.browserType().name(), servedWasmSha256: hash(wasmBytes), dictionaryRequests,
      ...dictionaryDetails, errors, rejected, recovered, ...(stop && { stop }),
      ...(clickEpochMs !== undefined && { clickEpochMs }),
      ...(assetEvidenceStartedAt !== undefined && { assetEvidenceTiming: { deferred: deferAssetEvidence,
        startedAtEpochMs: assetEvidenceStartedAt, finishedAtEpochMs: assetEvidenceFinishedAt } }),
      ...(live?.observe_worklet_evaluation && { workletRequests: workletRequests.slice(firstWorkletRequest) }),
      ...(beforeRegistrationStop && { beforeRegistrationStop }), ...(replayFilename && { replayFilename }) };
  } catch (error) {
    const alerts = await page.getByRole("alert").allTextContents();
    writeFileSync(join(outDir, `${artifactPrefix}-error.json`), JSON.stringify({ message: String(error), alerts, errors }) + "\n");
    throw error;
  } finally {
    await page.close();
  }
}

async function captureBeat(browser, source) {
  const page = await browser.newPage({ viewport: { width: 960, height: 980 }, acceptDownloads: true });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  try {
    await page.goto(url);
    const panel = page.getByRole("region", { name: "ビートボックス", exact: true });
    const pattern = panel.getByRole("textbox", { name: "ビートパターン", exact: true });
    const render = panel.getByRole("button", { name: "ビートをレンダー", exact: true });
    const alert = panel.getByRole("alert");
    await pattern.fill(measurement.check_invalid_pattern_then_recover);
    await render.click();
    await alert.waitFor();
    const rejected = await alert.textContent();
    await pattern.fill(source.pattern);
    await panel.getByRole("spinbutton", { name: "テンポ（BPM）", exact: true }).fill(String(source.bpm));
    await panel.getByRole("spinbutton", { name: "スウィング", exact: true }).fill(String(source.swing));
    const captures = [];
    for (const stride of measurement.observation_stride_frames) {
      await panel.getByRole("combobox", { name: "観測間隔（フレーム）", exact: true }).selectOption(String(stride));
      const response = page.waitForResponse((r) => r.ok() && new URL(r.url()).pathname.endsWith(".wasm"));
      await render.click();
      const hash = createHash("sha256").update(await (await response).body()).digest("hex");
      await panel.getByText("ビートのレンダー完了", { exact: true }).waitFor();
      for (const [label, ext] of [["WAVを保存", "wav"], ["観測JSONを保存", "json"]]) {
        const download = page.waitForEvent("download");
        await panel.getByRole("link", { name: label, exact: true }).click();
        await (await download).saveAs(join(outDir, `browser-${stride}.${ext}`));
      }
      const playheadTable = await panel.getByRole("table").locator("tbody > tr").evaluateAll(
        (rows) => rows.map((row) => [...row.cells].map((cell) => cell.textContent)),
      );
      captures.push({ stride, servedWasmSha256: hash, playheadTable, recovered: await alert.count() === 0 });
      if (captures.length === 1) {
        await panel.screenshot({ path: join(outDir, "browser-beat.png") });
      }
    }
    return { version: browser.version(), errors, rejected, captures };
  } finally {
    await page.close();
  }
}

async function captureLiveBeat(browser, source) {
  const page = await browser.newPage({ viewport: { width: 960, height: 980 }, acceptDownloads: true });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
  try {
    await page.goto(url);
    const panel = page.getByRole("region", { name: "ビートボックス", exact: true });
    const byName = (role, name) => panel.getByRole(role, { name, exact: true });
    const tempo = byName("spinbutton", "テンポ（BPM）");
    const swing = byName("spinbutton", "スウィング");
    await byName("textbox", "ビートパターン").fill(source.pattern);
    await tempo.fill(String(source.bpm));
    await swing.fill(String(source.swing));
    await byName("combobox", "観測間隔（フレーム）").selectOption(String(measurement.observation_stride_frames));
    const rate = measurement.output_rate_hz;
    await byName("spinbutton", "実時間の採取時間（秒）").fill(String(measurement.output_frames / rate));
    const response = page.waitForResponse((r) => r.ok() && new URL(r.url()).pathname.endsWith(".wasm"));
    const start = byName("button", "実時間でビートを再生");
    await start.click();
    const hash = createHash("sha256").update(await (await response).body()).digest("hex");
    for (const { request_after_seconds: seconds, operation } of measurement.commands) {
      await page.waitForFunction((frame) =>
        Number(document.querySelector("[data-beat-rendered]")?.dataset.beatRendered) >= frame,
      Math.ceil(seconds * rate));
      if (operation.type === "playing") {
        await byName("button", operation.playing ? "ビートを再開" : "ビートを停止").click();
      } else if (operation.bpm !== undefined) {
        await tempo.fill(String(operation.bpm));
        await byName("button", "テンポを適用").click();
      } else {
        await swing.fill(String(operation.swing));
        await byName("button", "スウィングを適用").click();
      }
    }
    await panel.getByText("実時間のビート採取完了", { exact: true }).waitFor();
    for (const [name, filename] of [["WAVを保存", "browser.wav"], ["観測JSONを保存", "browser.json"],
      ["再実行ケースを保存", "browser-case.json"]]) {
      const found = page.waitForEvent("download");
      await byName("link", name).click();
      await (await found).saveAs(join(outDir, filename));
    }
    await panel.screenshot({ path: join(outDir, "browser-beat-live.png") });
    return { version: browser.version(), servedWasmSha256: hash, errors,
      readyAgain: await start.isEnabled() && await panel.getByRole("alert").count() === 0 };
  } finally {
    await page.close();
  }
}

try {
  const executablePath = process.env.CHIMERA_CHROMIUM;
  const ipaExtra = id === "worklet-ipa-voice" && process.argv[4]
    ? JSON.parse(readFileSync(process.argv[4], "utf8")) : undefined;
  const webgl = id === "worklet-tract-3d"
    || ["worklet-tract-3d-dynamic", "worklet-tract-3d-live", "worklet-tract-3d-body"].includes(ipaExtra?.id);
  const args = webgl ? ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] : [];
  if (id === "worklet-realtime-release-alignment" && Number.isInteger(measurement.wrapper_tiering_budget)) {
    args.push(`--js-flags=--wasm-wrapper-tiering-budget=${measurement.wrapper_tiering_budget}`);
  }
  const fixedRealtime = /^worklet-realtime-voice(?:-\d+)?$/.test(id);
  const firefoxCase = (fixedRealtime && measurement.browser_engine === "firefox")
    || (ipaExtra?.id === "worklet-live-ipa" && ipaExtra.measurement.browser_engine === "firefox")
    || (id === "worklet-live-tsp-source-defaults" && process.argv[5] === "firefox")
    || songLive?.browser_engine === "firefox";
  const browser = firefoxCase
    ? await firefox.launch({ headless: true, executablePath: process.env.CHIMERA_FIREFOX })
    : await chromium.launch({ headless: true, executablePath, args });
  try {
    let details;
    if (id === "worklet-tract-3d") {
      details = await captureTract3D(browser);
    } else if (id === "worklet-midi-voice") {
      details = await captureMidi(browser);
    } else if (id === "worklet-midi-voice-pitch") {
      details = { candidate: await captureMidi(browser, input),
        upstream: await captureUpstreamMidiPitch(browser, input, process.argv[4]) };
    } else if (fixedRealtime || id === "worklet-manual-articulation" || id === "worklet-manual-body-switch") {
      details = await captureRealtime(browser, id.startsWith("worklet-manual-"));
    } else if (id === "worklet-realtime-release-alignment") {
      details = await captureReleaseAlignment(browser);
    } else if (id === "worklet-songbird-trill-observation") {
      details = { version: browser.version(), trials: [] };
      for (const [index, order] of measurement.capture_order.entries()) {
        const round = index + 1;
        for (const profile of order) {
          const artifactId = `${round}-${profile}`;
          const result = await captureCreature(browser, profile, id, artifactId);
          details.trials.push({ artifactId, round, profile, ...result });
        }
      }
    } else if (Object.hasOwn(creatureActions, id)) {
      details = { version: browser.version(), variants: {} };
      for (const variant of measurement.variants) {
        details.variants[variant] = await captureCreature(browser, variant, id);
      }
    } else if (id === "worklet-ipa-voice") {
      const extra = ipaExtra;
      let options = { timeline: extra?.measurement };
      if (extra?.id === "worklet-tract-3d-body") {
        details = await captureLiveTractBodies(browser, extra);
        options = undefined;
      } else if (extra?.id === "worklet-tract-3d-live") {
        const profileCase = JSON.parse(readFileSync(process.argv[5], "utf8"));
        const archived = JSON.parse(readFileSync(process.argv[6], "utf8")).measurement;
        const [desktop, mobile] = extra.measurement.viewport_widths_css_px;
        const common = { ipa: archived.input_ipa, live: true };
        details = await captureSpeech(browser, {
          ...common, viewportWidth: desktop, profile: profileCase.measurement, dynamic3d: archived, live3d: {},
        });
        details.mobile = await captureSpeech(browser, {
          ...common, viewportWidth: mobile, artifactPrefix: "mobile", live3d: {},
        });
        details.stalled = await captureSpeech(browser, {
          ...common, viewportWidth: desktop, artifactPrefix: "stalled",
          live3d: { stallFrame: extra.measurement.stall_trigger_frame, stallMilliseconds: extra.measurement.stall_milliseconds },
        });
        options = undefined;
      } else if (extra?.id === "worklet-tract-profile") {
        options = { profile: extra.measurement, acoustics: process.argv[5] === "--acoustics" };
      } else if (extra?.id === "worklet-tract-3d-dynamic") {
        const profileCase = JSON.parse(readFileSync(process.argv[5], "utf8"));
        options = { ipa: extra.measurement.input_ipa, profile: profileCase.measurement, dynamic3d: extra.measurement };
      } else if (extra?.id === "worklet-glottal-scope") {
        options = { scope: extra.measurement };
      } else if (extra?.id === "worklet-live-ipa") {
        options = { live: true, exerciseStop: !extra.measurement.profiler_capture_only };
      }
      if (options) {
        details = extra?.id === "worklet-pcm-spectrum"
          ? await captureSpectrumViews(browser, extra.measurement)
          : await captureSpeech(browser, options);
        if (options.live && options.exerciseStop !== false) {
          details.offline = await captureSpeech(browser, { artifactPrefix: "offline" });
        }
      }
    } else if (id === "worklet-tsp-source-defaults" || id === "worklet-live-tsp-source-defaults") {
      const englishCase = process.argv[4];
      const source = JSON.parse(readFileSync(englishCase, "utf8")).speech_voice;
      const diagnostic = process.argv.slice(7);
      details = await captureSpeech(browser, { english: source.input.text, englishCase,
        live: id === "worklet-live-tsp-source-defaults", exerciseStop: process.argv[6] !== "--native-clock",
        saveOfflineBeforeLive: diagnostic.includes("--save-offline-before-live"),
        traceSpeechPhases: diagnostic.includes("--trace-phases"),
        traceSpeechWasmCore: diagnostic.includes("--trace-wasm-core"),
        delaySpeechOneQuantum: diagnostic.includes("--speech-delay-one-quantum"),
        speechPreparation: diagnostic.find((arg) => arg.startsWith("--speech-preparation="))?.slice("--speech-preparation=".length),
        speechWasm: diagnostic.find((arg) => arg.startsWith("--wasm-probe="))?.slice("--wasm-probe=".length) });
    } else if (id === "worklet-english-voice") {
      const source = JSON.parse(readFileSync(process.argv[4], "utf8")).speech_voice;
      details = await captureSpeech(browser, { english: source.input.text });
    } else if (id === "worklet-english-body") {
      const source = JSON.parse(readFileSync(process.argv[4], "utf8"));
      details = {};
      for (const variant of source.variants) {
        details[variant.id] = await captureSpeech(browser, {
          english: source.input.text, artifactPrefix: variant.id, voiceSelection: variant,
        });
      }
    } else if (id === "worklet-ipa-body") {
      const source = JSON.parse(readFileSync(process.argv[4], "utf8"));
      details = {};
      for (const { id: label, body } of source.variants) {
        const options = { ipa: source.input.text, voiceSelection: { body } };
        details[label] = {
          offline: await captureSpeech(browser, { ...options, artifactPrefix: `${label}-offline` }),
          live: await captureSpeech(browser, { ...options, live: true, artifactPrefix: `${label}-live` }),
        };
      }
    } else if (id === "worklet-beatbox-pattern" || id === "worklet-live-beatbox") {
      const source = JSON.parse(readFileSync(process.argv[4], "utf8")).beatbox_pattern;
      details = id === "worklet-live-beatbox" ? await captureLiveBeat(browser, source) : await captureBeat(browser, source);
    } else if (["korean-lyrics", "velar-stops", "lingual-nasals", "tongue-glides", "alveolopalatal-fricatives", "alveolopalatal-affricates", "alveolar-tap", "russian-lyrics", "labiodental-fricatives", "velar-fricative", "postalveolar-affricate", "mandarin-lyrics", "mandarin-nasal-rhymes", "alveolar-affricate", "retroflex-fricative", "retroflex-affricate", "retroflex-approximant", "glottal-stop"].includes(id)) {
      const { scores, live } = JSON.parse(readFileSync(process.argv[4], "utf8"));
      details = {};
      for (const { id: label, score } of scores) {
        details[label] = await captureSong(browser, score, {
          body: "male", artifactPrefix: label,
          live: id !== "korean-lyrics" || label === "jamo-live" ? live : undefined,
        });
      }
    } else if (id === "worklet-song-body") {
      const source = JSON.parse(readFileSync(process.argv[4], "utf8"));
      const score = { ...source.score, vibrato_cents: source.vibrato_cents };
      const live = JSON.parse(readFileSync(process.argv[5], "utf8")).measurement;
      details = {};
      for (const { id: label, body } of source.variants) {
        details[label] = {
          offline: await captureSong(browser, score, { body, artifactPrefix: `${label}-offline` }),
          live: await captureSong(browser, score, { body, live, artifactPrefix: `${label}-live` }),
        };
      }
    } else if (id === "worklet-song-prepared-source") {
      const { song_voice: source } = JSON.parse(readFileSync(testPath, "utf8"));
      const score = { ...source.score, vibrato_cents: source.vibrato_cents };
      details = {};
      for (const warmUpFrames of measurement.warm_up_frames) {
        for (const scale of measurement.noise_scales) {
          for (const path of measurement.paths) {
            const artifactPrefix = `frame-${warmUpFrames}-noise-${scale}-${path}`;
            details[artifactPrefix] = await captureSong(browser, score, {
              artifactPrefix, preset: "prepared", warmUpFrames, turbulence: { scale },
              live: path === "realtime" ? { single_song_capture: true } : undefined,
            });
          }
        }
      }
    } else if (songVoiceCapture) {
      const sourceCase = JSON.parse(readFileSync(process.argv[4], "utf8"));
      const source = sourceCase.song_voice;
      const score = { ...source.score, vibrato_cents: source.vibrato_cents };
      const preset = sourceCase.id === "song-voice-fast" ? "fast" : undefined;
      const turbulence = source.turbulence;
      const rawDictionary = process.argv.slice(5).find((arg) => !arg.startsWith("--live="));
      const unrenderableLyrics = songLive?.unrenderable_lyrics;
      const captureLive = () => captureSong(browser, score, { rawDictionary, live: songLive, unrenderableLyrics, preset, turbulence });
      details = songLive?.native_silent_lead_trace_categories
        ? await captureWithChromiumTrace(browser, join(outDir, "trace.json"), songLive.native_silent_lead_trace_categories, captureLive)
        : await captureLive();
      if (songLive && !songLive.profiler_capture_only && !songLive.single_song_capture) {
        details.offline = await captureSong(browser, score, { rawDictionary, unrenderableLyrics, preset, turbulence, artifactPrefix: "offline" });
      }
    } else {
      const normal = await capture(browser, false);
      const retry = measurement.check_retry_after_worklet_load_failure ? await capture(browser, true) : null;
      details = { version: browser.version(), normal, retry };
    }
    writeFileSync(join(outDir, "browser-run.json"), JSON.stringify(details, null, 2) + "\n");
  } finally {
    await browser.close();
  }
} finally {
  await new Promise((resolve) => server.httpServer.close(resolve));
}
