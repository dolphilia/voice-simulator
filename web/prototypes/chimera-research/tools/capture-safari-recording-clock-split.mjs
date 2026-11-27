// Safariの録画に壁時計とAudioContextの時計を埋め込み、停止する対象だけを変える。
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { withSafari } from "./safari-webdriver.mjs";

const [casePath, output] = process.argv.slice(2);
const study = JSON.parse(readFileSync(casePath, "utf8"));

function install(mode, spec, includeAudio) {
  const button = document.querySelector("button");
  const status = document.querySelector("output");
  const canvas = document.querySelector("canvas");
  const paint = canvas.getContext("2d");
  const result = { mode, stage: "ready", events: [], draws: [], chunks: [], trackEvents: [] };
  window.clockSplitResult = result;
  const stage = (value) => {
    result.stage = value;
    status.value = value;
  };
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  button.addEventListener("click", async (event) => {
    button.disabled = true;
    result.trusted = event.isTrusted;
    let context, recorder, animation;
    const ownedTracks = [];
    try {
      stage("capturing");
      context = new AudioContext({ sampleRate: spec.sample_rate_hz, latencyHint: "interactive" });
      const rate = result.sampleRate = context.sampleRate;
      const tap = context.createMediaStreamDestination();
      const silent = new ConstantSourceNode(context, { offset: 0 });
      silent.connect(tap);
      const output = new GainNode(context, { gain: 0 });
      output.connect(context.destination);
      const source = context.createBufferSource();
      source.buffer = context.createBuffer(1, Math.round(spec.signal_seconds * rate), rate);
      const signal = source.buffer.getChannelData(0);
      for (let i = 0; i < signal.length; i++) {
        const t = i / rate;
        signal[i] = spec.signal_gain * Math.sin(2 * Math.PI *
          (spec.signal_initial_hz * t + spec.signal_sweep_hz_per_second * t * t / 2));
      }
      window.clockSplitSignal = new Blob([signal]);
      source.connect(tap);
      source.connect(output);
      silent.start();
      await context.resume();

      const wallStart = performance.now();
      const frame = () => Math.round(context.currentTime * rate);
      const scheduled = result.signalStartFrame = frame() + Math.round(spec.start_lead_seconds * rate);
      const wall = () => performance.now() - wallStart;
      const mark = (phase) => result.events.push({ phase, wallMs: wall(), frame: frame(),
        context: context.state, recorder: recorder?.state });
      const waitForFrame = async (target) => {
        while (frame() < target) {
          if (wall() > spec.timeout_ms) throw new Error("指定した音声フレームまで進みませんでした");
          await wait(2);
        }
      };
      const draw = () => {
        const wallMs = wall();
        const contextFrame = frame();
        const wallCode = Math.round(wallMs);
        const contextCode = Math.max(0, Math.round((contextFrame - scheduled) * 1000 / rate));
        paint.fillStyle = "#000";
        paint.fillRect(0, 0, canvas.width, canvas.height);
        paint.fillStyle = "#fff";
        for (const [row, code] of [wallCode, contextCode].entries()) {
          for (let bit = 0; bit < 12; bit++) {
            if (code & (1 << bit)) paint.fillRect(16 + 16 * bit, 16 + 32 * row, 16, 16);
          }
        }
        result.draws.push({ wallMs, contextFrame, wallCode, contextCode });
        animation = requestAnimationFrame(draw);
      };
      draw();
      const videoTracks = canvas.captureStream(30).getVideoTracks();
      ownedTracks.push(...videoTracks, ...tap.stream.getAudioTracks());
      const tracks = includeAudio ? ownedTracks : videoTracks;
      for (const track of tracks) {
        for (const type of ["mute", "unmute", "ended"]) {
          track.addEventListener(type, () => result.trackEvents.push({ type, kind: track.kind, wallMs: wall() }));
        }
      }
      const stream = new MediaStream(tracks);
      const startRecorder = (mimeType) => new MediaRecorder(stream, { mimeType, videoBitsPerSecond: 5_000_000 });
      if (!MediaRecorder.isTypeSupported(spec.mime_type)) throw new Error("指定した録画形式に対応していません");
      try {
        recorder = startRecorder(spec.mime_type);
      } catch (error) {
        if (includeAudio || error.name !== "NotSupportedError" || !spec.video_only_mime_type) throw error;
        result.mimeFallback = String(error);
        recorder = startRecorder(spec.video_only_mime_type);
      }
      const chunks = [];
      recorder.addEventListener("dataavailable", ({ data, timecode }) => {
        result.chunks.push({ bytes: data.size, timecode, wallMs: wall() });
        if (data.size) chunks.push(data);
      });
      const stopped = new Promise((resolve, reject) => {
        recorder.addEventListener("error", ({ error }) => reject(error), { once: true });
        recorder.addEventListener("stop", resolve, { once: true });
      });
      stopped.catch(() => {});
      const recorderEvent = async (type) => {
        const done = new Promise((resolve) => recorder.addEventListener(type, resolve, { once: true }));
        recorder[type]();
        await done;
      };
      recorder.start(500);
      mark("started");
      source.start(scheduled / rate);
      await waitForFrame(scheduled + Math.round(spec.hold_at_signal_seconds * rate));
      mark("hold_requested");
      if (mode === "context") await context.suspend();
      if (mode === "recorder") await recorderEvent("pause");
      mark("held");
      await wait(spec.hold_ms);
      mark("resume_requested");
      if (mode === "context") await context.resume();
      if (mode === "recorder") await recorderEvent("resume");
      mark("resumed");
      await waitForFrame(scheduled + signal.length + Math.round(spec.drain_seconds * rate));
      mark("stop_requested");
      recorder.stop();
      await stopped;
      mark("stopped");
      result.mimeType = recorder.mimeType;
      window.clockSplitMedia = new Blob(chunks, { type: result.mimeType.split(";")[0] });
      cancelAnimationFrame(animation);
      ownedTracks.forEach((track) => track.stop());
      result.trackStates = tracks.map(({ kind, readyState }) => ({ kind, readyState }));
      await context.close();
      stage("complete");
    } catch (error) {
      result.error = String(error);
      stage("failed");
    } finally {
      cancelAnimationFrame(animation);
      if (recorder && recorder.state !== "inactive") recorder.stop();
      ownedTracks.forEach((track) => track.stop());
      if (context && context.state !== "closed") await context.close().catch(() => {});
    }
  });
}

const html = `<!doctype html><html lang="ja"><meta charset="utf-8"><title>録画の時計比較</title>
<button>録画</button> <output>準備完了</output><canvas width="224" height="80"></canvas></html>`;
const server = createServer((request, response) => {
  if (request.url !== "/") {
    response.writeHead(404).end();
    return;
  }
  response.writeHead(200, { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" }).end(html);
});

await new Promise((resolve, reject) => server.once("error", reject).listen(0, "127.0.0.1", resolve));
const url = `http://127.0.0.1:${server.address().port}/`;
try {
  for (const [index, order] of study.condition_order.entries()) {
    for (const condition of order) {
      const mode = study.audio_track_comparison ? "context" : condition;
      const includeAudio = !study.audio_track_comparison || condition === "audiovisual";
      const folder = join(output, `${index + 1}-${condition}`);
      mkdirSync(folder);
      const observation = { mode, sessionStartErrors: [] };
      try {
        const capture = async (command, capabilities) => {
          observation.capabilities = capabilities;
          await command("/url", { url });
          const execute = (script, args = []) => command("/execute/sync", { script, args });
          await execute(`(${install})(...arguments)`, [mode, study.measurement, includeAudio]);
          const element = await command("/element", { using: "css selector", value: "button" });
          await command(`/element/${element["element-6066-11e4-a52e-4f735466cecf"]}/click`, {});
          const deadline = performance.now() + study.measurement.timeout_ms;
          do {
            Object.assign(observation, await execute("return window.clockSplitResult"));
            if (["complete", "failed"].includes(observation.stage)) break;
            await delay(50);
          } while (performance.now() < deadline);
          if (observation.error) return;
          if (observation.stage !== "complete") throw new Error("録画完了の待機が時間切れです");
          for (const [key, filename] of [["clockSplitMedia", "recording.mp4"], ["clockSplitSignal", "signal.f32le"]]) {
            const saved = await command("/execute/async", { args: [key], script: `
              const read = new FileReader();
              const done = arguments[1];
              const blob = window[arguments[0]];
              read.onload = () => done({ base64: read.result.slice(read.result.indexOf(";base64,") + 8), bytes: blob.size });
              read.onerror = () => done({ error: String(read.error) });
              read.readAsDataURL(blob);
            ` });
            if (!saved.base64) throw new Error(saved.error ?? "録画の内容を取得できません");
            const bytes = Buffer.from(saved.base64, "base64");
            if (bytes.length !== saved.bytes) throw new Error(`転送した長さが一致しません (${filename})`);
            writeFileSync(join(folder, filename), bytes);
          }
        };
        for (let attempt = 0;; attempt++) {
          try {
            await withSafari(capture);
            break;
          } catch (error) {
            if (attempt >= 1 || !String(error).startsWith("Error: Safari WebDriver /session:")) throw error;
            observation.sessionStartErrors.push(String(error));
            await delay(250);
          }
        }
      } catch (error) {
        observation.error = String(error);
      }
      writeFileSync(join(folder, "browser.json"), JSON.stringify(observation, null, 2) + "\n");
    }
  }
} finally {
  server.closeAllConnections();
  await new Promise((resolve) => server.close(resolve));
}
