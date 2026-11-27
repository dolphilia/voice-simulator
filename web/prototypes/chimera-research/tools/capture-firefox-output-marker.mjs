// Firefoxで既知の逆相信号と、指定に応じて別Contextの同相信号を再生する。
import { once } from "node:events";
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync, renameSync } from "node:fs";
import { createServer } from "node:http";
import { join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { firefox } from "playwright-core";
import { smoothMarkerPCM } from "./shared-context-marker.mjs";

const [path, folder, deviceProbe, fixture] = process.argv.slice(2);
const spec = JSON.parse(readFileSync(path, "utf8"));
const fixtureBytes = fixture ? readFileSync(fixture) : null;
function probeSamples() {
  const samples = smoothMarkerPCM(spec.marker);
  const tone = spec.tone_probe;
  if (!tone) return samples;
  for (let i = tone.first; i < tone.last_exclusive; i++) {
    const blend = Math.min(1, (i - tone.first) / tone.blend_frames,
      (tone.last_exclusive - 1 - i) / tone.blend_frames);
    let value = 0;
    for (const [j, hz] of tone.frequencies_hz.entries()) {
      value += tone.amplitude * Math.sin(2 * Math.PI * (i - tone.first) * hz / spec.sample_rate_hz
        + tone.phases_radians[j]);
    }
    samples[i] = (1 - blend) * samples[i] + blend * value;
  }
  return samples;
}

const save = (name, value) => {
  const target = join(folder, name + ".json");
  writeFileSync(target + ".tmp", JSON.stringify(value, null, 2));
  renameSync(target + ".tmp", target);
};
const module = readFileSync(new URL("./shared-context-marker-worklet.js", import.meta.url));
const server = createServer(({ url }, response) => {
  if (url === "/marker.js") response.writeHead(200, { "Content-Type": "text/javascript" }).end(module);
  else if (url === "/fixture.f32le" && fixtureBytes) {
    response.writeHead(200, { "Content-Type": "application/octet-stream" }).end(fixtureBytes);
  }
  else response.writeHead(200, { "Content-Type": "text/html; charset=utf-8" })
    .end("<!doctype html><html lang=ja><button>試験音を準備</button></html>");
});
const status = {};
let browser;
try {
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  browser = await firefox.launch({ headless: true, executablePath: process.env.CHIMERA_FIREFOX });
  const page = await browser.newPage();
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  await page.evaluate(({ sample_rate_hz, quantum_frames, anchor, keep_output }) => {
    document.querySelector("button").addEventListener("click", async (event) => {
      const context = new AudioContext({ sampleRate: sample_rate_hz, latencyHint: "interactive" });
      let prime;
      let keeperWaveform;
      if (keep_output) {
        const { period_frames: period, amplitude } = keep_output;
        const buffer = context.createBuffer(2, period, context.sampleRate);
        keeperWaveform = Float32Array.from({ length: period },
          (_, frame) => amplitude === 0 ? 0 : amplitude * Math.sin(2 * Math.PI * frame / period));
        buffer.copyToChannel(keeperWaveform, 0);
        buffer.copyToChannel(keeperWaveform, 1);
        prime = context.createBufferSource();
        prime.buffer = buffer;
        prime.loop = true;
      } else {
        prime = context.createConstantSource();
        prime.offset.value = 0;
      }
      prime.connect(context.destination);
      prime.start();
      await context.resume();
      await context.audioWorklet.addModule("/marker.js");
      window.chimeraMarkerProbe = { context, prime, trustedClick: event.isTrusted, quantum_frames, anchor, keeperWaveform };
    }, { once: true });
  }, spec);
  await page.getByRole("button").click();
  await page.waitForFunction(() => window.chimeraMarkerProbe?.context.currentTime > 0);
  save("trace-ready", await page.evaluate(() => ({
    sampleRate: window.chimeraMarkerProbe.context.sampleRate,
    trustedClick: window.chimeraMarkerProbe.trustedClick,
  })));
  const deadline = performance.now() + 15000;
  while (true) {
    try {
      if (JSON.parse(readFileSync(join(folder, "trace-release.json"), "utf8")).tap_ready) break;
    } catch (error) {
      if (error.code !== "ENOENT" && !(error instanceof SyntaxError)) throw error;
    }
    if (performance.now() >= deadline) throw new Error("タップとトレースの開始通知がありません");
    await delay(10);
  }
  await page.evaluate(async ({ samples, seconds, separate, study }) => {
    const probe = window.chimeraMarkerProbe;
    if (separate) {
      const rate = probe.context.sampleRate;
      if (probe.keeperWaveform) probe.keeper = probe.context;
      else await probe.context.close();
      probe.context = new AudioContext({ sampleRate: rate, latencyHint: "interactive" });
      await probe.context.resume();
      await probe.context.audioWorklet.addModule("/marker.js");
    }
    const { context, quantum_frames: quantum, anchor } = probe;
    if (study) {
      const response = await fetch("/fixture.f32le");
      if (!response.ok) throw new Error("比較用PCMを取得できません");
      samples = new Float32Array(await response.arrayBuffer());
      if (samples.length !== study.graph_capture_quanta * quantum) throw new Error("比較用PCMの長さが異なります");
    }
    const buffer = context.createBuffer(1, samples.length, context.sampleRate);
    buffer.copyToChannel(Float32Array.from(samples), 0);
    const startFrame = (Math.ceil(context.currentTime * context.sampleRate / quantum) + 8) * quantum;
    const worklet = new AudioWorkletNode(context, "chimera-shared-context-marker", {
      channelCount: 1, channelCountMode: "explicit", outputChannelCount: [2],
      processorOptions: { startFrame, quantum, captureQuanta: study?.graph_capture_quanta ?? Math.ceil(anchor.last_exclusive / quantum),
        observeInput: true, observeTiming: true },
    });
    worklet.port.onmessage = ({ data }) => {
      if (!data?.pcm) return;
      probe.observed = { scheduledFrame: startFrame, startFrame: data.frames[0], frames: Array.from(data.frames),
        inputFrames: Array.from(data.inputFrames) };
      if (study) {
        const bytes = new Uint8Array(data.pcm.buffer);
        let binary = "";
        for (let i = 0; i < bytes.length; i += 8192) binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
        Object.assign(probe.observed, { pcmBase64: btoa(binary), callbackEpochMs: Array.from(data.callbackEpochMs),
          rate: context.sampleRate });
      } else {
        probe.observed.pcm = Array.from(data.pcm);
      }
    };
    const source = context.createBufferSource();
    source.buffer = buffer;
    source.loop = !study;
    source.connect(worklet).connect(context.destination);
    source.start(startFrame / context.sampleRate);
    if (!separate) probe.prime.stop(startFrame / context.sampleRate);
    if (!study) source.stop(startFrame / context.sampleRate + seconds);
    if (study?.suspend) {
      const position = () => ({
        atEpochMs: Date.now(), frame: Math.round(context.currentTime * context.sampleRate), state: context.state,
        ...(probe.keeper && { keeperFrame: Math.round(probe.keeper.currentTime * probe.keeper.sampleRate),
          keeperState: probe.keeper.state }),
      });
      const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
      void (async () => {
        const target = startFrame + study.target_frame;
        while (position().frame < target) {
          await wait(Math.min(80, Math.max(4, (target / context.sampleRate - context.currentTime) * 1000)));
        }
        probe.contextRestart = { suspendRequested: position() };
        await context.suspend();
        probe.contextRestart.suspendReturned = position();
        await wait(study.hold_seconds * 1000);
        probe.contextRestart.resumeRequested = position();
        await context.resume();
        probe.contextRestart.resumeReturned = position();
      })().catch((error) => { probe.contextError = String(error); });
    }
  }, { samples: fixtureBytes ? null : Array.from(probeSamples()), seconds: spec.play_seconds,
    separate: spec.capture.separate_priming_context === true, study: spec.context_study });
  await page.waitForFunction(() => window.chimeraMarkerProbe.observed || window.chimeraMarkerProbe.contextError);
  if (spec.context_study) {
    Object.assign(status, await page.evaluate(() => ({
      contextRestart: window.chimeraMarkerProbe.contextRestart ?? null,
      contextError: window.chimeraMarkerProbe.contextError ?? null,
      ...(window.chimeraMarkerProbe.keeper && {
        keeper: {
          state: window.chimeraMarkerProbe.keeper.state, rate: window.chimeraMarkerProbe.keeper.sampleRate,
          frames: Math.round(window.chimeraMarkerProbe.keeper.currentTime * window.chimeraMarkerProbe.keeper.sampleRate),
          waveform: Array.from(window.chimeraMarkerProbe.keeperWaveform),
        },
      }),
    })));
    if (status.contextError) throw new Error(status.contextError);
  }
  const observed = await page.evaluate(() => window.chimeraMarkerProbe.observed);
  const pcm = spec.context_study ? Buffer.from(observed.pcmBase64, "base64")
    : Buffer.from(Float32Array.from(observed.pcm).buffer);
  writeFileSync(join(folder, "graph.f32le"), pcm);
  delete observed.pcm;
  delete observed.pcmBase64;
  save("graph", observed);
  // PCMの窓を受け取った時点でも、出力デバイスは同じContextで動いている。
  status.output = JSON.parse(execFileSync(deviceProbe, [], { timeout: 2000, encoding: "utf-8" }));
  status.browserVersion = browser.version();
  await delay(spec.context_study ? 250 : Math.ceil(spec.play_seconds * 1000) + 250);
  await page.evaluate(async () => {
    const { context, keeper } = window.chimeraMarkerProbe;
    await context.close();
    await keeper?.close();
  });
  status.complete = true;
} catch (error) {
  status.error = String(error);
  process.exitCode = 1;
} finally {
  save("browser", status);
  await browser?.close();
  server.close();
}
