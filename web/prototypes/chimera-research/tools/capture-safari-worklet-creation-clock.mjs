// 実時間のAudioContextをSafariで操作し、停止中と再開後のWorkletを観察する。
import { readFileSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { withSafari } from "./safari-webdriver.mjs";

const [casePath, output] = process.argv.slice(2);
const study = JSON.parse(readFileSync(casePath, "utf8"));
const writeJson = (filename, value) => writeFileSync(join(output, filename), JSON.stringify(value, null, 2) + "\n");

function installExperiment(mode, spec) {
  const prepare = document.querySelector("#prepare");
  const resume = document.querySelector("#resume");
  const status = document.querySelector("output");
  const result = { mode, stage: "ready", events: [] };
  window.chimeraClockResult = result;
  let context;
  let receivedBlocks;
  let node;
  const frame = () => Math.round(context.currentTime * context.sampleRate);
  const mark = (phase) => result.events.push({ phase, frame: frame(), time: context.currentTime,
    state: context.state, elapsedMs: performance.now() });
  const stage = (value) => {
    result.stage = value;
    status.value = value;
  };
  const fail = async (error) => {
    result.error = String(error);
    stage("failed");
    if (context && context.state !== "closed") await context.close().catch(() => {});
  };

  prepare.addEventListener("click", async (event) => {
    prepare.disabled = true;
    result.prepareTrusted = event.isTrusted;
    stage("preparing");
    try {
      context = new AudioContext({ sampleRate: spec.sample_rate_hz, latencyHint: "interactive" });
      mark("context_created");
      let oscillator, gain;
      if (mode === "advanced") {
        oscillator = context.createOscillator();
        gain = context.createGain();
        gain.gain.value = 0;
        oscillator.connect(gain).connect(context.destination);
        oscillator.start();
        mark("advance_resume_requested");
        await context.resume();
        const deadline = performance.now() + spec.timeout_ms;
        while (frame() < spec.advanced_minimum_frames) {
          if (performance.now() >= deadline) throw new Error("停止前に指定フレームまで進みませんでした");
          await new Promise((resolve) => setTimeout(resolve, 2));
        }
        mark("advanced");
      }
      await context.suspend();
      mark("suspended");
      if (oscillator) {
        oscillator.stop();
        oscillator.disconnect();
        gain.disconnect();
      }
      mark("registration_requested");
      await context.audioWorklet.addModule("/creation-clock-processor.js");
      mark("registered");
      node = new AudioWorkletNode(context, "chimera-creation-clock-probe", { channelCount: 1,
        channelCountMode: "explicit", outputChannelCount: [1], processorOptions: { blocks: spec.captured_blocks } });
      let reply;
      const created = new Promise((resolve) => { reply = resolve; });
      receivedBlocks = new Promise((resolve) => {
        node.port.onmessage = ({ data }) => {
          if (data.type === "created") reply(data);
          if (data.type === "captured") resolve(data.blocks);
        };
      });
      result.creation = await created;
      mark("constructor_received");
      const buffer = context.createBuffer(1, spec.quantum_frames * spec.captured_blocks, spec.sample_rate_hz);
      const samples = buffer.getChannelData(0);
      for (let index = 0; index < samples.length; index++) samples[index] = (index + 1) / spec.ramp_denominator;
      const source = context.createBufferSource();
      source.buffer = buffer;
      source.connect(node).connect(context.destination);
      source.start();
      mark("index_signal_scheduled");
      resume.disabled = false;
      stage("prepared");
    } catch (error) {
      await fail(error);
    }
  });

  resume.addEventListener("click", async (event) => {
    resume.disabled = true;
    result.resumeTrusted = event.isTrusted;
    stage("resuming");
    try {
      mark("resume_requested");
      await context.resume();
      mark("resumed");
      result.blocks = await receivedBlocks;
      mark("blocks_received");
      await context.close();
      mark("closed");
      stage("complete");
    } catch (error) {
      await fail(error);
    }
  });
}

const html = `<!doctype html><html lang="ja"><meta charset="utf-8"><title>Worklet作成時刻の確認</title>
  <button id="prepare">準備</button> <button id="resume" disabled>再開</button> <output>準備待ち</output></html>`;
const processor = readFileSync(new URL("./worklet-creation-clock-processor.js", import.meta.url));
const server = createServer((request, response) => {
  if (request.url === "/creation-clock-processor.js") {
    response.writeHead(200, { "Content-Type": "text/javascript", "Cache-Control": "no-store" });
    response.end(processor);
  } else if (request.url === "/") {
    response.writeHead(200, { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" });
    response.end(html);
  } else {
    response.writeHead(404).end();
  }
});

await new Promise((resolve, reject) => server.once("error", reject).listen(0, "127.0.0.1", resolve));
const url = `http://127.0.0.1:${server.address().port}/`;
try {
  for (const [index, pair] of study.condition_order.entries()) {
    for (const mode of pair) {
      const filename = `${index + 1}-${mode}.json`;
      try {
        const outcome = await withSafari(async (command, capabilities) => {
          await command("/url", { url });
          const execute = (script, args = []) => command("/execute/sync", { script, args });
          const click = async (selector) => {
            const element = await command("/element", { using: "css selector", value: selector });
            await command(`/element/${element["element-6066-11e4-a52e-4f735466cecf"]}/click`, {});
          };
          const observe = async (expected) => {
            const deadline = performance.now() + study.measurement.timeout_ms;
            let observed;
            do {
              observed = await execute("return window.chimeraClockResult");
              if (observed?.stage === expected || observed?.stage === "failed") return observed;
              await delay(30);
            } while (performance.now() < deadline);
            return { ...observed, error: `観測の待機が時間切れです (${expected})` };
          };
          await execute(`(${installExperiment})(...arguments)`, [mode, study.measurement]);
          await click("#prepare");
          const prepared = await observe("prepared");
          if (prepared.error) return { capabilities, ...prepared };
          await click("#resume");
          return { capabilities, ...await observe("complete") };
        });
        writeJson(filename, outcome);
      } catch (error) {
        writeJson(filename, { mode, error: String(error) });
      }
    }
  }
} finally {
  server.closeAllConnections();
  await new Promise((resolve) => server.close(resolve));
}
