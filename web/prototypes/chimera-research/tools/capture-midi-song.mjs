// 仮想入力を、研究版と固定上流の通常の鍵盤歌唱画面へ送る。
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

async function sendEvents(page) {
  return page.evaluate(async ({ events, end }) => {
    const begin = performance.now();
    const waitUntil = (seconds) => new Promise((resolve) =>
      setTimeout(resolve, Math.max(0, begin + seconds * 1000 - performance.now())));
    const evidence = [];
    for (const event of events) {
      await waitUntil(event.seconds);
      const clock = window.songReference?.clock();
      const bytes = event.type === "note-on" ? [144, event.note, event.velocity] : [128, event.note, 0];
      window.chimeraTestMidi.apply({ port: "A", bytes });
      evidence.push({ ...event, wallSeconds: (performance.now() - begin) / 1000, clock,
        ...(window.songReference?.snapshot() ?? {}) });
    }
    await waitUntil(end);
    return evidence;
  }, { events: input.events, end: measurement.render_end_seconds });
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
    const panel = page.getByRole("region", { name: "MIDI鍵盤の発声", exact: true });
    await panel.getByRole("checkbox", { name: "MIDIで歌唱する" }).check();
    await panel.getByLabel("鍵盤歌唱の歌詞").fill(input.lyrics);
    await panel.getByRole("button", { name: "MIDIを接続" }).click();
    await panel.getByRole("button", { name: "MIDI計測を開始" }).click();
    const error = panel.getByRole("alert");
    await panel.getByText("MIDI計測中", { exact: true }).or(error).waitFor();
    if (await error.isVisible()) throw new Error(await error.textContent());
    const events = await sendEvents(page);
    await panel.getByRole("button", { name: "MIDI計測を停止" }).click();
    const done = panel.getByText("実時間計測完了", { exact: true });
    await done.or(error).waitFor();
    if (await error.isVisible()) throw new Error(await error.textContent());
    for (const [label, suffix] of [["WAVを保存", ".wav"], ["観測JSONを保存", ".json"], ["再実行ケースを保存", "-case.json"]]) {
      const [download] = await Promise.all([page.waitForEvent("download"),
        panel.getByRole("link", { name: label, exact: true }).click()]);
      await download.saveAs(join(out, "midi-song" + suffix));
    }
    return { events, requests: await page.evaluate(() => window.chimeraTestMidi.requests) };
  });
  await upper.listen();
  report.upstream = await visit(upper, async (page) => {
    await page.getByRole("radio", { name: "Sing", exact: true }).click();
    await page.getByRole("textbox", { name: "Lyrics to sing" }).fill(input.lyrics);
    await page.getByRole("button", { name: "MIDI", exact: true }).click();
    await page.getByRole("button", { name: "MIDI: A", exact: true }).waitFor();
    await page.evaluate(async (observeSchedule) => {
      const [{ engine }, { useSing, soundingSyllable, roll }, { useStore }] = await Promise.all([
        import("/src/audio/AudioEngine.ts"), import("/src/ui/singing.ts"), import("/src/ui/store.ts"),
      ]);
      useSing.getState().setVibrato(0);
      await useStore.getState().start();
      const telemetry = [];
      const commands = [];
      if (observeSchedule) {
        const schedule = engine.scheduleGestures.bind(engine);
        const release = engine.release.bind(engine);
        engine.scheduleGestures = (gestures, lead = 0.006) => {
          commands.push({ type: "schedule", lead, gestures: structuredClone(gestures) });
          schedule(gestures, lead);
        };
        engine.release = (tag) => {
          commands.push({ type: "release", tag });
          release(tag);
        };
      }
      engine.onTelemetry(({ t }) => telemetry.push({
        clock: t.clock, f0: t.f0, voicing: t.voicing, rms: t.outRms,
        lipArea: t.orAreas.at(-1), lipAperture: t.artic[7],
      }));
      window.songReference = { clock: () => engine.voiceClock(), snapshot: () => ({
        next: useSing.getState().cursor, text: soundingSyllable(), held: useStore.getState().heldNotes,
        pitch: roll.notes.findLast((note) => note.t1 === null)?.midi ?? null,
        ...(observeSchedule ? { commands: commands.splice(0) } : {}),
      }), report: () => ({ rate: engine.sampleRate, telemetry, syllables: useSing.getState().syllables }) };
    }, Boolean(measurement.expected_p_plan));
    await page.waitForFunction(() => window.songReference.clock() !== null);
    const events = await sendEvents(page);
    return { events, ...await page.evaluate(() => ({ ...window.songReference.report(),
      requests: window.chimeraTestMidi.requests })) };
  });
} catch (error) {
  report.error = String(error);
  throw error;
} finally {
  writeFileSync(join(out, "midi-song-browser.json"), JSON.stringify(report) + "\n");
  await browser.close();
  await upper.close();
  await new Promise((done) => candidate.httpServer.close(done));
}
