// 鍵盤から低音を出し、通常の画面でハムのセルを編集する。
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";
import { createServer, preview } from "vite";
import { installMidi } from "./fake-midi.mjs";

const [out, casePath, upstream] = process.argv.slice(2);
const { input, measurement } = JSON.parse(readFileSync(casePath, "utf8"));
const host = "127.0.0.1";
const root = fileURLToPath(new URL("../", import.meta.url));
const candidate = await preview({ root, preview: { host, port: 0 } });
const upper = await createServer({ root: upstream, server: { host, port: 0, hmr: false, watch: null } });
const browser = await chromium.launch({ headless: true, executablePath: process.env.CHIMERA_CHROMIUM });

const timeline = [...input.events, { ...input.toggle_hum, type: "toggle-hum" }]
  .sort((left, right) => left.seconds - right.seconds);

async function sendEvents(page, toggleLabel) {
  return page.evaluate(async ({ timeline, captureSeconds, toggleLabel }) => {
    const begin = performance.now();
    const waitUntil = (seconds) => new Promise((resolve) =>
      setTimeout(resolve, Math.max(0, begin + seconds * 1000 - performance.now())));
    const evidence = [];
    for (const event of timeline) {
      await waitUntil(event.seconds);
      const clock = window.beatReference?.clock();
      if (event.type === "toggle-hum") {
        const button = [...document.querySelectorAll("button")].find((element) =>
          (element.getAttribute("aria-label") ?? element.textContent.trim()) === toggleLabel);
        if (!button || button.disabled) throw new Error("ハムを編集できません");
        button.click();
      } else {
        const bytes = event.type === "note-on" ? [144, event.note, event.velocity] : [128, event.note, 0];
        window.chimeraTestMidi.apply({ port: "A", bytes });
      }
      evidence.push({ ...event, wallSeconds: (performance.now() - begin) / 1000, clock,
        ...(window.beatReference?.snapshot() ?? {}) });
    }
    await waitUntil(captureSeconds);
    return evidence;
  }, { timeline, captureSeconds: input.capture_seconds, toggleLabel });
}

async function visit(server, run) {
  const page = await browser.newPage({ acceptDownloads: true });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  try {
    await page.addInitScript(installMidi, ["A"]);
    await page.goto(`http://${host}:${server.httpServer.address().port}/`);
    return { ...await run(page), errors };
  } finally {
    await page.close();
  }
}

const report = { chromium: browser.version() };
try {
  report.candidate = await visit(candidate, async (page) => {
    const panel = page.getByRole("region", { name: "ビートボックス", exact: true });
    await panel.getByLabel("ビートパターン").fill(input.pattern);
    await panel.getByLabel("テンポ（BPM）").fill(String(input.bpm));
    await panel.getByLabel("スウィング").fill(String(input.swing));
    await panel.getByLabel("観測間隔（フレーム）").selectOption(String(measurement.observation_stride_frames));
    await panel.getByLabel("実時間の採取時間（秒）").fill(String(input.capture_seconds));
    await panel.getByRole("button", { name: "ビートのMIDIを接続" }).click();
    await panel.getByText("ビートのMIDI入力 A", { exact: true }).waitFor();
    await panel.getByRole("button", { name: "実時間でビートを再生" }).click();
    const error = panel.getByRole("alert");
    await panel.getByText("ビートを採取中", { exact: true }).or(error).waitFor();
    if (await error.isVisible()) throw new Error(await error.textContent());
    const events = await sendEvents(page, "ハムを切り替え");
    await panel.getByText("実時間のビート採取完了", { exact: true }).or(error).waitFor();
    if (await error.isVisible()) throw new Error(await error.textContent());
    for (const [label, suffix] of [["WAVを保存", ".wav"], ["観測JSONを保存", ".json"], ["再実行ケースを保存", "-case.json"]]) {
      const [download] = await Promise.all([page.waitForEvent("download"),
        panel.getByRole("link", { name: label, exact: true }).click()]);
      await download.saveAs(join(out, "midi-beatbox" + suffix));
    }
    await panel.getByRole("button", { name: "ビートのMIDIを切断" }).click();
    return { events, ...await page.evaluate(() => ({
      requests: window.chimeraTestMidi.requests, listenersAfterDisconnect: window.chimeraTestMidi.listenerCount(),
    })) };
  });
  await upper.listen();
  report.upstream = await visit(upper, async (page) => {
    await page.getByRole("radio", { name: "Beatbox", exact: true }).click();
    await page.getByLabel("Beat as text").fill(input.pattern);
    await page.getByRole("button", { name: "Mic FX", exact: true }).click();
    await page.getByRole("button", { name: "MIDI", exact: true }).click();
    await page.getByRole("button", { name: "MIDI: A", exact: true }).waitFor();
    await page.evaluate(async ({ bpm, swing }) => {
      const [{ engine }, { useStore }] = await Promise.all([
        import("/src/audio/AudioEngine.ts"), import("/src/ui/store.ts"),
      ]);
      useStore.getState().setBeatTempo({ bpm, swing });
      const telemetry = [];
      engine.onTelemetry(({ t }) => telemetry.push({
        clock: t.clock, f0: t.f0, voicing: t.voicing, rms: t.outRms,
        lipArea: t.orAreas.at(-1), lipAperture: t.artic[7], velum: t.velumPort, gate: t.gate,
      }));
      window.beatReference = { clock: () => engine.voiceClock(), snapshot: () => {
        const state = useStore.getState();
        return { held: state.heldNotes, bassNote: state.bassNote, basePitch: state.source.f0,
          lipTarget: state.artic.lipAp, velumTarget: state.artic.velum,
          firstStep: state.beat.steps[0] };
      }, report: () => ({ rate: engine.sampleRate, telemetry }) };
    }, input);
    await page.getByRole("gridcell", { name: "Hum, step 1", exact: true }).waitFor();
    await page.getByRole("button", { name: "Play beat", exact: true }).click();
    await page.waitForFunction(() => window.beatReference.clock() !== null);
    const events = await sendEvents(page, "Hum, step 1");
    return { events, ...await page.evaluate(() => ({
      ...window.beatReference.report(), requests: window.chimeraTestMidi.requests,
    })) };
  });
} catch (error) {
  report.error = String(error);
  throw error;
} finally {
  writeFileSync(join(out, "midi-beatbox-browser.json"), JSON.stringify(report) + "\n");
  await browser.close();
  await upper.close();
  await new Promise((done) => candidate.httpServer.close(done));
}
