// 研究版と固定上流の画面へ仮想MIDIを入力する。
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";
import { createServer, preview } from "vite";
import { installMidi } from "./fake-midi.mjs";

const [out, casePath, upstream] = process.argv.slice(2);
const { input, measurement } = JSON.parse(readFileSync(casePath, "utf8"));
const captureSeconds = measurement.capture_seconds ?? input.capture_seconds;
const keyCall = input.key_mode === "call" ? input.call_id : "";
const creature = input.creature ?? "songbird";
const instruments = {
  songbird: { name: "鳴禽", selector: /^Songbird Hylocichla/ },
  seal: { name: "ウェッデルアザラシ", selector: /^Weddell seal Leptonychotes/ },
  alligator: { name: "アメリカアリゲーター", selector: /^American alligator Alligator/ },
  elephant: { name: "アフリカゾウ", selector: /^African elephant Loxodonta/ },
};
const { name: instrument, selector } = instruments[creature];
const prefix = `midi-${creature}`;
const host = "127.0.0.1";
const root = fileURLToPath(new URL("../", import.meta.url));
const candidate = await preview({ root, preview: { host, port: 0 } });
const upper = await createServer({ root: upstream, server: { host, port: 0, hmr: false, watch: null } });
const browser = await chromium.launch({ headless: true, executablePath: process.env.CHIMERA_CHROMIUM });

async function sendEvents(page) {
  return page.evaluate(async ({ timeline, end }) => {
    const begin = performance.now();
    const until = (seconds) => new Promise((resolve) =>
      setTimeout(resolve, Math.max(0, begin + seconds * 1000 - performance.now())));
    const evidence = [];
    for (const event of timeline) {
      await until(event.seconds);
      const bytes = event.type === "note-on" ? [144, event.note, event.velocity] : [128, event.note, 0];
      window.chimeraTestMidi.apply({ port: "A", bytes });
      evidence.push({ ...event, wallSeconds: (performance.now() - begin) / 1000,
        ...(window.birdReference?.snapshot() ?? {}) });
    }
    await until(end);
    return evidence;
  }, { timeline: input.events, end: captureSeconds });
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
    const panel = page.getByRole("region", { name: `MIDIで${instrument}を演奏` });
    await panel.getByRole("button", { name: `${instrument}のMIDIを接続` }).click();
    await panel.getByText("A", { exact: true }).waitFor();
    await panel.getByLabel("鍵盤で鳴らす音").selectOption(keyCall);
    await panel.getByLabel("採取時間（秒）").fill(String(captureSeconds));
    await panel.getByRole("button", { name: `${instrument}のMIDI計測を開始` }).click();
    const error = panel.getByRole("alert");
    await panel.getByText(`${instrument}のMIDIを計測中`, { exact: true }).or(error).waitFor();
    if (await error.isVisible()) throw new Error(await error.textContent());
    const events = await sendEvents(page);
    await panel.getByText(`${instrument}のMIDI計測完了`, { exact: true }).or(error).waitFor();
    if (await error.isVisible()) throw new Error(await error.textContent());
    for (const [name, suffix] of [["WAVを保存", ".wav"], ["観測JSONを保存", ".json"], ["再実行ケースを保存", "-case.json"]]) {
      const [download] = await Promise.all([page.waitForEvent("download"),
        panel.getByRole("link", { name, exact: true }).click()]);
      await download.saveAs(join(out, prefix + suffix));
    }
    await panel.getByRole("button", { name: `${instrument}のMIDIを切断` }).click();
    return { events, ...await page.evaluate(() => ({
      requests: window.chimeraTestMidi.requests, afterDisconnect: window.chimeraTestMidi.listenerCount(),
    })) };
  });
  await upper.listen();
  report.upstream = await visit(upper, async (page) => {
    await page.getByRole("radio", { name: "Bestiary", exact: true }).click();
    await page.getByRole("button", { name: selector }).click();
    await page.getByLabel("What the keys play").selectOption(keyCall);
    await page.getByRole("button", { name: "MIDI", exact: true }).click();
    await page.getByRole("button", { name: "MIDI: A", exact: true }).waitFor();
    await page.evaluate(async (creature) => {
      const [{ engine }, { useStore }] = await Promise.all([
        import("/src/audio/AudioEngine.ts"), import("/src/ui/store.ts"),
      ]);
      const telemetry = [];
      const calls = [];
      const playCall = engine.playCall.bind(engine);
      engine.playCall = (id, pitch, amplitude) => {
        calls.push({ id, pitch, amplitude, clock: engine.latestCreature?.t.clock });
        return playCall(id, pitch, amplitude);
      };
      let last;
      const capture = setInterval(() => {
        const t = engine.latestCreature?.t;
        if (!t || t.id !== creature || t.clock === last) return;
        last = t.clock;
        telemetry.push({ clock: t.clock, gate: t.gate, pitch: t.params.pitch, call: t.call, rms: t.outRms,
          left: t.source.left, right: t.source.right, glottis: t.source.glottis });
      }, 4);
      window.birdReference = {
        snapshot: () => {
          const s = useStore.getState();
          return { clock: engine.latestCreature?.t.clock, held: s.heldNotes, pitch: s.cparams[creature]?.pitch,
            creature: s.creature, keyCall: s.keyCall, hold: s.hold };
        },
        result: () => {
          clearInterval(capture);
          return { telemetry, calls, rate: engine.sampleRate, requests: window.chimeraTestMidi.requests };
        },
      };
      await useStore.getState().start();
    }, creature);
    await page.waitForFunction(() => window.birdReference.snapshot().clock > 0);
    const events = await sendEvents(page);
    return { events, ...await page.evaluate(() => window.birdReference.result()) };
  });
} catch (error) {
  report.error = String(error);
  throw error;
} finally {
  writeFileSync(join(out, `${prefix}-browser.json`), JSON.stringify(report) + "\n");
  await browser.close();
  await upper.close();
  await new Promise((done) => candidate.httpServer.close(done));
}
