// macOSのSafariをWebDriverで操作し、通常の歌唱画面から成果物を取得する。
import { createHash } from "node:crypto";
import { existsSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath } from "node:url";
import { preview } from "vite";
import { installSharedContextMarker, readSharedContextMarker, smoothMarkerPCM } from "./shared-context-marker.mjs";
import { installSongOutputProbe, readSongOutputProbe } from "./song-output-probe.mjs";
import { withSafari } from "./safari-webdriver.mjs";

const [outDir, sourcePath, optionsPath] = process.argv.slice(2);
const { song_voice: source } = JSON.parse(readFileSync(sourcePath, "utf8"));
const options = JSON.parse(readFileSync(optionsPath, "utf8"));
const writeJson = (name, data) => writeFileSync(join(outDir, name), JSON.stringify(data, null, 2) + "\n");
const webRoot = fileURLToPath(new URL("../", import.meta.url));

function installAudioClientGate() {
  globalThis.chimeraWaitForSystemTrace = (request) => new Promise((resolve) => {
    globalThis.chimeraSafariAudioTrace = { request };
    globalThis.chimeraReleaseSafariAudioTrace = () => {
      globalThis.chimeraSafariAudioTrace.releaseEpochMs = Date.now();
      resolve();
    };
  });
}

function fillSong(fields) {
  const panel = document.querySelector('section[aria-labelledby="song-title"]');
  const set = (label, value) => {
    const field = [...panel.querySelectorAll("label")].find((node) => node.firstChild.textContent.trim() === label).control;
    Object.getOwnPropertyDescriptor(Object.getPrototypeOf(field), "value").set.call(field, String(value));
    field.dispatchEvent(new Event(field instanceof HTMLSelectElement ? "change" : "input", { bubbles: true }));
  };
  for (const [label, value] of fields) {
    if (value != null) set(label, value);
  }
}

function installStartupObservation({ holdAfterRegistrationFrames, hasOutputProbe, pausedRegistration, midSongPause, clickName, outputClock }) {
  let context;
  let pausedFrame;
  let scheduledFrame;
  const phases = [];
  const assets = [];
  const errors = [];
  let click;
  let clockTimer;
  const observeOutputClock = (activeContext) => {
    const observation = {
      sample_rate_hz: activeContext.sampleRate,
      time_origin_epoch_ms: performance.timeOrigin,
      supported: typeof activeContext.getOutputTimestamp === "function",
      samples: [],
    };
    window.chimeraSafariOutputClock = observation;
    if (!observation.supported) return;
    const read = () => {
      if (observation.samples.length >= outputClock.max_samples) {
        clearInterval(clockTimer);
        return;
      }
      if (activeContext.state !== "running") return;
      const before = performance.now();
      const graphBefore = activeContext.currentTime;
      const stamp = activeContext.getOutputTimestamp();
      const graphAfter = activeContext.currentTime;
      observation.samples.push([before, performance.now(), graphBefore, graphAfter, stamp.contextTime, stamp.performanceTime]);
    };
    read();
    clockTimer = setInterval(read, outputClock.interval_ms);
  };
  const activation = () => navigator.userActivation?.isActive ?? null;
  const contextSnapshot = () => context && { state: context.state, frame: Math.round(context.currentTime * context.sampleRate) };
  const mark = (phase, url, error) => {
    const entry = { phase, wallMs: performance.now(), epochMs: Date.now(), activation: activation(),
      context: contextSnapshot(), url, error };
    phases.push(entry);
    return entry;
  };
  for (const name of ["suspend", "resume", "close"]) {
    const original = AudioContext.prototype[name];
    AudioContext.prototype[name] = function (...args) {
      context = this;
      if (outputClock && name === "close") clearInterval(clockTimer);
      mark(`${name}_request`);
      const promise = original.apply(this, args);
      void promise.then(() => {
        mark(`${name}_complete`);
        if (outputClock && name === "resume" && !window.chimeraSafariOutputClock) observeOutputClock(this);
      }, (error) => mark(`${name}_rejected`, undefined, String(error)));
      return promise;
    };
  }
  const waitForFrame = async (target, failure) => {
    const deadline = performance.now() + 1500;
    while (contextSnapshot().frame < target) {
      if (context.state !== "running" || performance.now() >= deadline) {
        throw new Error(failure);
      }
      await new Promise((resolve) => setTimeout(resolve, 1));
    }
  };
  if (midSongPause) {
    const OriginalNode = globalThis.AudioWorkletNode;
    const observeSong = async (startFrame) => {
      scheduledFrame = startFrame;
      mark("mid_song_reservation_received");
      await waitForFrame(startFrame + midSongPause.target_output_frame, "歌唱中の停止目標までフレームが進みませんでした");
      mark("mid_song_target_reached");
      if (!midSongPause.perform_pause) return;
      mark("mid_song_suspend_requested");
      await context.suspend();
      mark("mid_song_suspended");
      await new Promise((resolve) => setTimeout(resolve, midSongPause.hold_ms));
      mark("mid_song_resume_requested");
      await context.resume();
      mark("mid_song_resumed");
    };
    globalThis.AudioWorkletNode = class extends OriginalNode {
      constructor(nodeContext, name, options) {
        const processor = options?.processorOptions;
        const listen = nodeContext === context && processor?.realtime;
        super(nodeContext, name, listen ? { ...options, processorOptions: {
          ...processor, realtime: { ...processor.realtime, reportSchedule: true, traceFirstOutput: true },
        } } : options);
        if (listen) {
          const onMessage = ({ data }) => {
            if (data.type !== "scheduled") return;
            this.port.removeEventListener("message", onMessage);
            void observeSong(data.contextFrame).catch((error) => errors.push(String(error)));
          };
          this.port.addEventListener("message", onMessage);
          this.port.start();
        }
      }
    };
  }
  const waitAfterRegistration = async (url) => {
    const start = mark("registration_hold_start", url);
    try {
      await waitForFrame(start.context.frame + holdAfterRegistrationFrames, "登録後の待機中にContextのフレームが進みませんでした");
    } catch (error) {
      mark("registration_hold_failed", url, String(error));
      throw error;
    }
    mark("registration_hold_complete", url);
  };
  const suspendBeforeRegistration = async () => {
    const oscillator = context.createOscillator();
    const muted = context.createGain();
    muted.gain.value = 0;
    oscillator.connect(muted).connect(context.destination);
    oscillator.start();
    try {
      await waitForFrame(pausedRegistration.minimum_advance_frames, "停止前に指定のContextフレームまで進みませんでした");
      mark("paused_registration_suspend_requested");
      await context.suspend();
      pausedFrame = mark("paused_registration_suspended").context.frame;
    } finally {
      oscillator.stop();
      oscillator.disconnect();
      muted.disconnect();
    }
  };
  const restartPausedContext = async (advance) => {
    mark("paused_registration_resume_requested");
    await context.resume();
    mark("paused_registration_resumed");
    if (advance) {
      await waitForFrame(pausedFrame + advance, "再開後に指定のContextフレームまで進みませんでした");
      mark("paused_registration_advanced");
    }
  };
  if (pausedRegistration?.resume_after_connect) {
    const connect = AudioWorkletNode.prototype.connect;
    AudioWorkletNode.prototype.connect = function (target, ...indices) {
      const result = connect.call(this, target, ...indices);
      if (this.context === context && this.numberOfInputs === 0 && target === context.destination
          && context.state === "suspended") {
        mark("paused_registration_graph_connected");
        // 並列観測の接続を含む同期処理が終わってから再開する。
        queueMicrotask(() => void restartPausedContext(0).catch((error) => errors.push(String(error))));
      }
      return result;
    };
  }
  const addModule = AudioWorklet.prototype.addModule;
  AudioWorklet.prototype.addModule = function (url, ...args) {
    const path = String(url);
    const synthesisModule = path.includes("/fixed-processor-entry-");
    const lastModule = hasOutputProbe ? path.endsWith("/research-song-output-probe.js") : synthesisModule;
    const register = () => {
      mark("add_module_request", path);
      const promise = addModule.call(this, url, ...args);
      void promise.then(() => mark("add_module_complete", path),
        (error) => mark("add_module_rejected", path, String(error)));
      return promise;
    };
    const promise = pausedRegistration && synthesisModule ? suspendBeforeRegistration().then(register) : register();
    if (!lastModule) return promise;
    if (pausedRegistration && !pausedRegistration.resume_after_connect) {
      return promise.then(() => restartPausedContext(pausedRegistration.advance_after_resume_frames));
    }
    if (holdAfterRegistrationFrames) return promise.then(() => waitAfterRegistration(path));
    return promise;
  };
  const fetchResource = window.fetch;
  window.fetch = async function (...args) {
    const response = await fetchResource.apply(this, args);
    if (response.url && /\/(?:[^/]+\.wasm|cmudict[^/]*\.gz)$/.test(new URL(response.url).pathname)) {
      assets.push({ url: response.url, status: response.status });
    }
    return response;
  };
  document.addEventListener("click", (event) => {
    if (event.target.closest?.("button")?.textContent === clickName) {
      click = { trusted: event.isTrusted, activation: activation(), epochMs: Date.now() };
    }
  }, { capture: true });
  window.addEventListener("error", (event) => errors.push(event.message));
  window.addEventListener("unhandledrejection", (event) => errors.push(String(event.reason)));
  window.chimeraSafariSongStartup = () => {
    const panel = document.querySelector('section[aria-labelledby="song-title"]');
    return { phases, assets, errors, click, scheduledFrame, context: contextSnapshot(),
      videoReady: Boolean(panel.querySelector("video")),
      status: panel.querySelector('[role="status"]')?.textContent, alert: panel.querySelector('[role="alert"]')?.textContent };
  };
}

async function readSongLinks(names, done) {
  const panel = document.querySelector('section[aria-labelledby="song-title"]');
  try {
    const results = [];
    for (const name of names) {
      const link = [...panel.querySelectorAll("a[download]")].find((link) => link.textContent === name);
      const buffer = new Uint8Array(await (await fetch(link.href)).arrayBuffer());
      let contents = "";
      for (let offset = 0; offset < buffer.length; offset += 8192) {
        contents += String.fromCharCode(...buffer.subarray(offset, offset + 8192));
      }
      results.push({ filename: link.download, base64: btoa(contents) });
    }
    done({ results });
  } catch (error) {
    done({ error: String(error) });
  }
}

const server = await preview({ root: webRoot, preview: { host: "127.0.0.1", port: 0 }, plugins: [{
  name: "chimera-safari-song-output-probe",
  configurePreviewServer(server) {
    server.middlewares.use("/research-song-output-probe.js", (_request, response) => {
      response.setHeader("Content-Type", "text/javascript");
      response.end(readFileSync(new URL("./song-output-probe-worklet.js", import.meta.url)));
    });
    if (options.shared_context_marker) {
      const markerScript = readFileSync(new URL("./shared-context-marker-worklet.js", import.meta.url));
      server.middlewares.use("/research-shared-context-marker.js", (_request, response) => {
        response.setHeader("Content-Type", "text/javascript");
        response.end(markerScript);
      });
    }
  },
}] });

try {
  const url = new URL(`http://127.0.0.1:${server.httpServer.address().port}/`);
  const clickName = options.record_song ? "歌唱を録画" : "実時間で歌唱";
  const completed = options.record_song ? "歌唱の録画完了" : "実時間の歌唱完了";
  url.searchParams.set("songStartupTrace", "1");
  if (options.score_preparation_block_frames !== undefined) {
    url.searchParams.set("songScorePreparationBlock", options.score_preparation_block_frames);
  }
  if (options.score_preparation_initial_blocks?.length) {
    url.searchParams.set("songScorePreparationInitialBlocks", options.score_preparation_initial_blocks.join(","));
  }
  if (options.trace_score_preparation_blocks) url.searchParams.set("songScorePreparationTiming", "1");
  if (options.register_before_resume) url.searchParams.set("songRegisterBeforeResume", "1");
  await withSafari(async (command, capabilities) => {
    writeJson("driver.json", capabilities);
    const evaluate = (script, ...args) => command("/execute/sync", { script, args });
    const call = (fn, ...args) => evaluate(`return (${fn})(...arguments)`, ...args);
    await command("/url", { url: url.href });
    await command("/timeouts", { implicit: 5000, script: 5000 });
    let element;
    try {
      element = await command("/element", { using: "xpath",
        value: `//section[@aria-labelledby='song-title']//button[.='${clickName}']` });
    } catch (error) {
      const page = await command("/execute/async", { script: `const done = arguments[0];
        const src = document.querySelector('script[type="module"]')?.src;
        const snapshot = { readyState: document.readyState, url: location.href, src, title: document.title };
        if (src) import(src).then(() => done(snapshot), (reason) => done({ ...snapshot, error: String(reason) }));
        else done(snapshot);`, args: [] });
      writeJson("page-before-song.json", page);
      throw error;
    }
    const preset = options.song_preset ?? "fast";
    await call(fillSong, [["歌唱プリセット", preset]]);
    const { score, vibrato_cents, turbulence, warm_up_frames, render_end_seconds } = source;
    await call(fillSong, [
      ["歌詞（英語・韓国語・ロシア語・中国語）", score.lyrics],
      ["テンポ（BPM）", score.bpm], ["ビブラート（セント）", vibrato_cents],
      ["乱流係数", turbulence.scale],
      ["声門の乱流ゲイン倍率", turbulence.glottis_gain_multiplier],
      ["狭窄の乱流ゲイン倍率", turbulence.constriction_gain_multiplier],
      ["歯の乱流の低域通過周波数の下限（Hz）", turbulence.teeth_lowpass_floor_hz],
      ["最初の拍（秒）", score.start_seconds],
      ["MIDI番号と拍数", score.notes.map(({ midi, beats }) => `${midi} ${beats}`).join("\n")],
      ...(preset === "prepared" ? [["予約前の描画フレーム数", warm_up_frames], ["出力終了（秒）", render_end_seconds]] : []),
    ]);
    await call(installStartupObservation, { holdAfterRegistrationFrames: options.hold_after_registration_frames ?? 0,
      hasOutputProbe: Boolean(options.output_probe), pausedRegistration: options.paused_registration,
      midSongPause: options.mid_song_pause, clickName, outputClock: options.output_clock_observation });
    if (options.output_probe) await call(installSongOutputProbe, options.output_probe);
    if (options.audio_client_trace) await call(installAudioClientGate);
    if (options.shared_context_marker) {
      await evaluate(`return (${installSharedContextMarker})(arguments[0], (${smoothMarkerPCM}))`, options.shared_context_marker);
    }
    const id = element["element-6066-11e4-a52e-4f735466cecf"];
    await command(`/element/${id}/click`, {});
    let snapshot;
    const deadline = performance.now() + options.startup_timeout_seconds * 1000;
    const keyboardAfter = performance.now() + 800;
    let usedKeyboard = false;
    let traceRequested = false;
    let traceReleased = false;
    do {
      snapshot = await evaluate("return window.chimeraSafariSongStartup()");
      if (snapshot.alert || (snapshot.status === completed && (!options.record_song || snapshot.videoReady))) break;
      if (!snapshot.click && !usedKeyboard && performance.now() >= keyboardAfter) {
        usedKeyboard = true;
        await command(`/element/${id}/value`, { text: "\uE00D" });
      }
      if (options.audio_client_trace) {
        if (!traceRequested) {
          const request = await evaluate("return window.chimeraSafariAudioTrace?.request ?? null");
          if (request) {
            traceRequested = true;
            writeJson("trace-ready.tmp", request);
            renameSync(join(outDir, "trace-ready.tmp"), join(outDir, "trace-ready.json"));
          }
        }
        if (traceRequested && !traceReleased && existsSync(join(outDir, "trace-release.json"))) {
          traceReleased = true;
          await evaluate("window.chimeraReleaseSafariAudioTrace()");
        }
      }
      await delay(50);
    } while (performance.now() < deadline);
    writeJson("startup.json", snapshot);
    if (options.audio_client_trace) {
      writeJson("browser-trace-gate.json", await evaluate("return window.chimeraSafariAudioTrace ?? null"));
    }
    if (options.output_clock_observation) {
      writeJson("output-clock.json", await evaluate("return window.chimeraSafariOutputClock ?? null"));
    }
    if (snapshot.status !== completed || (options.record_song && !snapshot.videoReady)) {
      throw new Error(snapshot.alert ?? `歌唱が制限時間内に完了しませんでした (${snapshot.status ?? "状態表示なし"})`);
    }
    const linksFor = (names) => command("/execute/async", { script: `(${readSongLinks})(arguments[0], arguments[1])`, args: [names] });
    const links = await linksFor(["WAVを保存", "観測JSONを保存", "再実行ケースを保存"]);
    if (links.error) throw new Error(links.error);
    for (const [index, name] of ["browser.wav", "browser.json", "browser-case.json"].entries()) {
      writeFileSync(join(outDir, name), Buffer.from(links.results[index].base64, "base64"));
    }
    let recordingFilename;
    if (options.record_song) {
      const media = await linksFor(["歌唱の動画を保存"]);
      if (media.error) throw new Error(media.error);
      const recording = media.results[0];
      const extension = recording.filename.match(/\.(mp4|webm)$/)?.[1];
      if (!extension) throw new Error("録画のファイル形式を特定できません");
      recordingFilename = `recording.${extension}`;
      writeFileSync(join(outDir, recordingFilename), Buffer.from(recording.base64, "base64"));
    }
    const asset = async (suffix) => {
      const served = snapshot.assets.find(({ url }) => url.endsWith(suffix));
      if (!served || served.status !== 200 || new URL(served.url).origin !== url.origin) {
        throw new Error(`歌唱が取得した静的資材を確認できません (${suffix})`);
      }
      const response = await fetch(served.url);
      if (!response.ok) throw new Error(`歌唱の静的資材を照合できません (${suffix})`);
      const bytes = Buffer.from(await response.arrayBuffer());
      return { sha256: createHash("sha256").update(bytes).digest("hex"), gzip: bytes[0] === 0x1f && bytes[1] === 0x8b };
    };
    const [wasm, dictionary] = await Promise.all([asset(".wasm"), asset(".gz")]);
    writeJson("browser-run.json", { version: capabilities.browserVersion, engine: "safari",
      errors: snapshot.errors, recovered: !snapshot.alert, clickEpochMs: snapshot.click?.epochMs,
      servedWasmSha256: wasm.sha256, dictionaryResponseSha256: dictionary.sha256,
      dictionaryResponseIsGzip: dictionary.gzip, replayFilename: links.results[2].filename, recordingFilename });
    if (options.shared_context_marker) {
      try {
        const { pcm, ...timeline } = await call(readSharedContextMarker);
        writeFileSync(join(outDir, "marker.f32le"), Buffer.from(pcm, "base64"));
        writeJson("marker.json", timeline);
      } catch (error) {
        writeJson("marker-error.json", { error: String(error) });
      }
    }
    if (options.output_probe) {
      try {
        const { pcm, ...timeline } = await call(readSongOutputProbe);
        writeFileSync(join(outDir, "output-probe.f32le"), Buffer.from(pcm, "base64"));
        writeJson("output-probe.json", timeline);
      } catch (error) {
        writeJson("output-probe-error.json", { error: String(error) });
      }
    }
  });
} finally {
  server.httpServer.closeAllConnections();
  await new Promise((resolve) => server.httpServer.close(resolve));
}
