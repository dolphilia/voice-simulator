// Safariの実験用の音だけを鳴らし、出力状態が対応するプロセスをタップする。
import { execFile, spawn } from "node:child_process";
import { closeSync, existsSync, openSync, readFileSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { promisify } from "node:util";
import { withSafari } from "./safari-webdriver.mjs";
import { smoothMarkerPCM } from "./shared-context-marker.mjs";

const [caseFile, output, inspector, app, recording, mode, deviceProbe, fixturePath] = process.argv.slice(2);
const study = JSON.parse(readFileSync(caseFile, "utf8"));
const writeJson = (name, value) => writeFileSync(join(output, name), JSON.stringify(value, null, 2) + "\n");
const execute = promisify(execFile);

function installStereoTest(spec, makeSmoothMarker) {
  const play = document.querySelector("#play");
  const stop = document.querySelector("#stop");
  const status = document.querySelector("output");
  let context;
  const report = { stage: "idle" };
  window.chimeraStereoTest = report;
  const stage = (name) => {
    report.stage = name;
    status.value = name;
  };
  async function contextRestart(study, startFrame) {
    const rate = context.sampleRate;
    const position = () => ({ atEpochMs: Date.now(), frame: Math.round(context.currentTime * rate), state: context.state });
    const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
    const target = startFrame + study.target_frame;
    while (Math.round(context.currentTime * rate) < target) {
      await wait(Math.min(80, Math.max(4, (target / rate - context.currentTime) * 1000)));
    }
    report.contextRestart = { suspendRequested: position() };
    await context.suspend();
    report.contextRestart.suspendReturned = position();
    await wait(study.hold_seconds * 1000);
    report.contextRestart.resumeRequested = position();
    await context.resume();
    report.contextRestart.resumeReturned = position();
  }
  function markerBuffer(context, marker) {
    if (marker.shape === "smooth-binary") {
      const samples = makeSmoothMarker(marker);
      const buffer = context.createBuffer(1, samples.length, context.sampleRate);
      buffer.copyToChannel(samples, 0);
      return buffer;
    }
    const { multiplier, offset, modulus, center, scale } = marker;
    const buffer = context.createBuffer(1, modulus, context.sampleRate);
    const channel = buffer.getChannelData(0);
    for (let i = 0; i < modulus; i++) channel[i] = ((i * multiplier + offset) % modulus - center) / scale;
    return buffer;
  }
  play.addEventListener("click", async (event) => {
    play.disabled = true;
    report.trustedPlay = event.isTrusted;
    delete report.graph;
    stage("starting");
    try {
      const trial = report.contextStudy ? spec.context_study : undefined;
      context = new AudioContext({ sampleRate: spec.sample_rate_hz, latencyHint: "interactive" });
      await context.resume();
      await context.audioWorklet.addModule("/shared-context-marker-worklet.js");
      let signal;
      if (trial) {
        const response = await fetch("/fixture.f32le");
        if (!response.ok) throw new Error("比較用PCMを取得できません");
        const samples = new Float32Array(await response.arrayBuffer());
        if (samples.length !== trial.graph_capture_quanta * spec.quantum_frames) throw new Error("比較用PCMの長さが異なります");
        signal = context.createBuffer(1, samples.length, context.sampleRate);
        signal.copyToChannel(samples, 0);
      }
      const quantum = spec.quantum_frames;
      const startFrame = Math.ceil(context.currentTime * context.sampleRate / quantum) * quantum
        + spec.graph_lead_quanta * quantum;
      const marker = new AudioWorkletNode(context, "chimera-shared-context-marker", {
        channelCount: 1, channelCountMode: "explicit", outputChannelCount: [2],
        processorOptions: { startFrame, quantum, readyQuanta: 1,
          captureQuanta: trial?.graph_capture_quanta ?? report.captureQuanta ?? spec.graph_capture_quanta,
          observeInput: true, observeTiming: true },
      });
      marker.port.onmessage = ({ data }) => {
        if (typeof data !== "object") return;
        const bytes = new Uint8Array(data.pcm.buffer);
        let binary = "";
        for (let i = 0; i < bytes.length; i += 8192) binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
        report.graph = { rate: context.sampleRate, startFrame, frames: Array.from(data.frames),
          inputFrames: Array.from(data.inputFrames), callbackEpochMs: Array.from(data.callbackEpochMs), pcm: btoa(binary) };
      };
      const source = context.createBufferSource();
      source.buffer = signal ?? markerBuffer(context, spec.marker);
      source.loop = !trial;
      source.connect(marker).connect(context.destination);
      source.start(startFrame / context.sampleRate);
      if (!trial) source.stop(startFrame / context.sampleRate + 20);
      stop.disabled = false;
      stage("playing");
      if (trial?.suspend) {
        void contextRestart(trial, startFrame).catch((error) => {
          report.error = String(error);
          stage("failed");
        });
      }
    } catch (error) {
      report.error = String(error);
      stage("failed");
      if (context && context.state !== "closed") await context.close().catch(() => {});
    }
  });
  stop.addEventListener("click", async () => {
    stop.disabled = true;
    try {
      await context.close();
      play.disabled = false;
      stage("stopped");
    } catch (error) {
      report.error = String(error);
      stage("failed");
    }
  });
}

async function observe(read, accepts, seconds) {
  const deadline = performance.now() + seconds * 1000;
  let sample;
  do {
    sample = await read();
    if (accepts(sample)) return { matched: true, sample };
    await delay(90);
  } while (performance.now() < deadline);
  return { matched: false, sample };
}

async function captureTap(target, onReady) {
  const args = ["-nW", "--stderr", join(recording, "tap-command.log"), app,
    "--args", String(target.pid), String(study.capture_duration_seconds), recording];
  writeJson("tap-command.json", ["/usr/bin/open", ...args]);
  const log = openSync(join(output, "tap-launch.log"), "w");
  let launch;
  try {
    launch = spawn("/usr/bin/open", args, { stdio: ["ignore", log, log] });
    let exited;
    launch.once("error", (error) => { exited = { error: String(error) }; });
    launch.once("exit", (code, signal) => { exited = { code, signal }; });
    const state = () => ({ ready: existsSync(join(recording, "tap-ready")), exited });
    const started = await observe(state, (v) => v.ready || v.exited, study.tap_start_timeout_seconds);
    if (!started.sample.ready) return { phase: started.sample.exited ? "start_failed" : "start_timeout", ...started.sample };
    if (onReady) await onReady();
    const device = deviceProbe ? JSON.parse((await execute(deviceProbe, [], { timeout: 2000 })).stdout) : undefined;
    const finished = await observe(state, (v) => v.exited, study.capture_duration_seconds + 4);
    const complete = finished.sample.exited?.code === 0 && existsSync(join(recording, "tap.json"));
    return { phase: complete ? "complete" : finished.matched ? "capture_failed" : "capture_timeout",
      ...finished.sample, outputDevice: device };
  } finally {
    // 許可待ちなら実験用アプリだけを終了し、その後にSafariのContextを閉じる。
    const pidFile = join(recording, "tap-pid");
    if (launch?.exitCode === null && existsSync(pidFile)) {
      const pid = Number(readFileSync(pidFile, "utf8"));
      if (Number.isSafeInteger(pid) && pid > 0) {
        try {
          const { stdout } = await execute("/bin/ps", ["-p", String(pid), "-o", "comm="], { timeout: 1000 });
          if (stdout.trim() === join(app, "Contents/MacOS/chimera-process-tap")) process.kill(pid, "SIGTERM");
        } catch {
          // すでにアプリが終了した場合は、外側の採取器が成果を確認する。
        }
      }
    }
    if (launch && launch.exitCode === null) launch.kill();
    closeSync(log);
  }
}

async function captureClientTrace(label, target, seconds) {
  const command = ["xctrace", "record", "--instrument", "Audio Client", "--attach", String(target.pid),
    "--time-limit", `${seconds}s`, "--output", join(output, `${label}.trace`)];
  const capture = { command: ["/usr/bin/xcrun", ...command], atStartEpochMs: Date.now() };
  try {
    const { stdout, stderr } = await execute("/usr/bin/xcrun", command,
      { timeout: (seconds + 12) * 1000, killSignal: "SIGINT" });
    writeFileSync(join(output, `${label}-trace.log`), stdout + stderr);
    capture.completed = true;
  } catch (error) {
    writeFileSync(join(output, `${label}-trace.log`), String(error.stdout ?? "") + String(error.stderr ?? ""));
    capture.completed = false;
    capture.error = String(error.message);
  }
  capture.atEndEpochMs = Date.now();
  return capture;
}

const html = `<!doctype html><html lang="ja"><meta charset="utf-8"><title>Safari出力PCMの較正</title>
<button id="play">試験音を再生</button> <button id="stop" disabled>停止</button> <output></output></html>`;
const processor = readFileSync(new URL("./shared-context-marker-worklet.js", import.meta.url));
const fixture = fixturePath ? readFileSync(fixturePath) : null;
const server = createServer((request, response) => {
  if (request.url === "/") {
    response.writeHead(200, { "Content-Type": "text/html; charset=utf-8" }).end(html);
  } else if (request.url === "/shared-context-marker-worklet.js") {
    response.writeHead(200, { "Content-Type": "text/javascript" }).end(processor);
  } else if (request.url === "/fixture.f32le" && fixture) {
    response.writeHead(200, { "Content-Type": "application/octet-stream" }).end(fixture);
  } else {
    response.writeHead(404).end();
  }
});

const result = { phase: "browser_start", snapshots: [], activations: [] };
try {
  await new Promise((resolve, reject) => server.once("error", reject).listen(0, "127.0.0.1", resolve));
  await withSafari(async (command, capabilities) => {
    result.capabilities = capabilities;
    await command("/url", { url: `http://127.0.0.1:${server.address().port}/` });
    const run = (script, args = []) => command("/execute/sync", { script, args });
    const activate = async (selector, via = "click") => {
      const element = await command("/element", { using: "css selector", value: selector });
      const path = `/element/${element["element-6066-11e4-a52e-4f735466cecf"]}`;
      await command(`${path}/${via === "click" ? "click" : "value"}`, via === "click" ? {} : { text: "\uE00D" });
      result.activations.push({ selector, via, atEpochMs: Date.now() });
    };
    const snapshot = async (phase) => {
      const { stdout } = await execute(inspector, study.candidate_bundle_ids, { timeout: 3000 });
      const processes = JSON.parse(stdout);
      result.snapshots.push({ phase, atEpochMs: Date.now(), processes });
      return processes;
    };
    const read = (script) => run(`return ${script}`);
    const transition = async (selector, name, initial) => {
      const current = () => read("window.chimeraStereoTest.stage");
      const completed = (v) => v === name || v === "failed";
      await activate(selector);
      let stage = await observe(current, completed, 4);
      if (stage.sample === initial) {
        await activate(selector, "space");
        stage = await observe(current, completed, 4);
      }
      if (stage.sample !== name) throw new Error(`Safariの状態が ${name} に進みません: ${stage.sample}`);
    };
    const saveGraph = async (label, timeout = 3, chunked = false) => {
      const received = await observe(() => read("Boolean(window.chimeraStereoTest.graph)"), Boolean, timeout);
      if (!received.matched) throw new Error("Safariで先行信号のPCMを取得できません");
      let graph, pcm;
      if (chunked) {
        graph = await run("const { pcm, ...meta } = window.chimeraStereoTest.graph; return meta");
        const size = await read("window.chimeraStereoTest.graph.pcm.length");
        const parts = [];
        for (let offset = 0; offset < size; offset += 131072) {
          parts.push(await run("return window.chimeraStereoTest.graph.pcm.slice(arguments[0], arguments[0] + 131072)", [offset]));
        }
        pcm = parts.join("");
      } else {
        ({ pcm, ...graph } = await read("window.chimeraStereoTest.graph"));
      }
      writeFileSync(join(output, `${label}.f32le`), Buffer.from(pcm, "base64"));
      writeJson(`${label}.json`, graph);
      return read("window.chimeraStereoTest.trustedPlay");
    };
    await run(`(${installStereoTest})(arguments[0], (${smoothMarkerPCM}))`, [study]);
    const before = await snapshot("before");
    await transition("#play", "playing", "idle");
    const fresh = (rows) => rows.filter((row) => row.runningOutput && !before.some((b) => b.pid === row.pid && b.runningOutput));
    const pilot = await observe(() => snapshot("pilot"), (rows) => fresh(rows).length > 0, study.output_switch_timeout_seconds);
    result.pilotTrusted = await saveGraph("pilot-marker");
    const candidates = fresh(pilot.sample);
    await transition("#stop", "stopped", "playing");
    if (candidates.length !== 1) {
      result.phase = candidates.length ? "target_ambiguous" : "target_not_observed";
      return;
    }
    const target = candidates[0];
    result.target = target;
    const same = (row) => row.pid === target.pid && row.bundleID === target.bundleID;
    const quiet = await observe(() => snapshot("stopped"), (rows) => !rows.some((r) => same(r) && r.runningOutput),
      study.output_switch_timeout_seconds);
    if (!quiet.matched) {
      result.phase = "target_stayed_active";
      return;
    }
    if (mode === "context-restart") {
      await run("window.chimeraStereoTest.contextStudy = true");
      result.tap = await captureTap(target, async () => {
        await transition("#play", "playing", "stopped");
        const again = await observe(() => snapshot("restarted"), (rows) => rows.some((row) => same(row) && row.runningOutput),
          study.output_switch_timeout_seconds);
        if (again.matched) result.confirmedTarget = again.sample.find((row) => same(row) && row.runningOutput);
      });
      result.phase = result.tap.phase;
      if (result.tap.phase === "complete") {
        result.restartedTrusted = await saveGraph("context-marker", 5, true);
        result.contextRestart = await read("window.chimeraStereoTest.contextRestart ?? null");
        result.contextError = await read("window.chimeraStereoTest.error ?? null");
      }
      await transition("#stop", "stopped", "playing");
      await snapshot("finished");
      return;
    }
    const trace = mode === "audio-client" ? study.client_trace : undefined;
    if (trace) {
      result.clientTrace = { idle: await captureClientTrace("idle", target, trace.idle_seconds) };
      await run("window.chimeraStereoTest.captureQuanta = arguments[0]", [trace.active_graph_quanta]);
    }
    await transition("#play", "playing", "stopped");
    const again = await observe(() => snapshot("restarted"), (rows) => fresh(rows).length > 0, study.output_switch_timeout_seconds);
    const next = fresh(again.sample);
    if (trace && next.length === 1 && same(next[0])) {
      result.clientTrace.active = await captureClientTrace("active", next[0], trace.active_seconds);
    }
    result.restartedTrusted = await saveGraph("capture-marker", trace ? 7 : 3);
    if (next.length === 1 && same(next[0])) {
      result.confirmedTarget = next[0];
      if (mode === "graph-control") {
        result.phase = "graph_control_complete";
      } else if (trace) {
        result.phase = result.clientTrace.idle.completed && result.clientTrace.active?.completed
          ? "audio_client_trace_complete" : "audio_client_trace_failed";
      } else {
        result.tap = await captureTap(next[0]);
        result.phase = result.tap.phase;
      }
    } else {
      result.phase = "target_not_reconfirmed";
    }
    await transition("#stop", "stopped", "playing");
    await snapshot("finished");
  });
} catch (error) {
  result.error = String(error);
} finally {
  writeJson("capture.json", result);
  server.close();
}
