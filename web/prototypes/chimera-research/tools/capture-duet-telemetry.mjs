import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { chromium } from "playwright-core";
import { preview } from "vite";
import { DuetTeleTrack, duetTelemetryScalars } from "../src/duet-telemetry.ts";

const [casePath, upstream, out, showId] = process.argv.slice(2);
const spec = JSON.parse(readFileSync(casePath, "utf8"));
const { TeleTrack } = await import(pathToFileURL(join(upstream, "src/show/tele.ts")));
const paths = ["voice-1.tele", "voice-2.tele", "upper-1.tele", "upper-2.tele"];
const settings = spec.browser;
const rate = spec.format.sample_rate_hz;
const arrays = ["artic", "phAreas", "orAreas", "pressureRms", "flow", "glottalArea", "glottalFlow"];

function payloadHash(track, frame) {
  const hash = createHash("sha256");
  for (let index = 0; index < track.frames; index++) {
    const item = frame(index);
    const values = [...duetTelemetryScalars.map((name) => item[name]), ...arrays.flatMap((name) => [...item[name]])];
    const bytes = Buffer.alloc(values.length * 4);
    values.forEach((value, i) => bytes.writeFloatLE(value, i * 4));
    hash.update(bytes);
  }
  return hash.digest("hex");
}

const raw = (filename) => new Uint8Array(readFileSync(join(out, filename))).buffer;
const compare = paths.map((name) => {
  const buffer = raw(name);
  const upper = new TeleTrack(buffer);
  const candidate = new DuetTeleTrack(buffer);
  const times = [...settings.paused_seek_samples.map((frame) => frame / rate), -1, 9, NaN];
  return { name, header: [candidate.sampleRate, candidate.hop, candidate.frames, candidate.nPh, candidate.nOr, candidate.body],
    upperHeader: [upper.sampleRate, upper.hop, upper.frames, upper.nPh, upper.nOr, upper.body],
    decodedCandidate: payloadHash(candidate, (i) => candidate.frame(i)),
    decodedUpstream: payloadHash(upper, (i) => upper.message(i).t),
    sourcePayload: createHash("sha256").update(Buffer.from(buffer).subarray(spec.format.header_bytes)).digest("hex"),
    positions: times.map((seconds) => [seconds, candidate.indexAt(seconds), upper.indexAt(seconds)]),
  };
});

const damaged = raw(paths[0]).slice(0, -4);
const rejects = (Constructor) => {
  try { new Constructor(damaged); return false; } catch { return true; }
};
writeFileSync(join(out, "decoders.json"), JSON.stringify({ compare,
  truncated: { candidate: rejects(DuetTeleTrack), upstream: rejects(TeleTrack) } }, null, 2) + "\n");

const host = "127.0.0.1";
const root = fileURLToPath(new URL("../", import.meta.url));
const server = await preview({ root, preview: { host, port: 0 } });
const endpoint = `http://${host}:${server.httpServer.address().port}`;
let browser;
const result = { errors: [], paused: [], live: [] };
try {
  browser = await chromium.launch({ headless: true, executablePath: process.env.CHIMERA_CHROMIUM });
  result.version = browser.version();
  const page = await browser.newPage();
  page.on("pageerror", (error) => result.errors.push(error.message));
  await page.goto(endpoint);
  await page.getByRole("link", { name: "デュエットの再生時計", exact: true }).click();
  await page.waitForURL(`**/?show=${showId}`);
  const play = page.getByRole("button", { name: "再生", exact: true });
  const table = page.getByRole("table", { name: "声部別のテレメトリ" });
  const slider = page.getByRole("slider", { name: "音源の位置", exact: true });
  await table.waitFor();
  const readPage = () => page.evaluate(() => {
    const output = document.querySelector('output[aria-label="音源フレーム"]');
    return {
      time: Number(output.dataset.time), frame: Number(output.textContent), epoch: Number(output.dataset.epoch),
      playing: document.querySelector("button").textContent === "一時停止",
      voices: Array.from(document.querySelectorAll("tbody tr"), (row) => {
        const [name, index, sample, f0, lip] = Array.from(row.cells, (cell) => cell.textContent);
        return { name, index: Number(index), sample: Number(sample), f0: Number(f0), lip: Number(lip) };
      }),
    };
  });
  let epoch = 0;
  const seek = async (frame) => {
    await slider.evaluate((input, seconds) => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(input, String(seconds));
      input.dispatchEvent(new Event("input", { bubbles: true }));
    }, frame / rate);
    await page.waitForFunction((expected) => Number(document.querySelector("output").dataset.epoch) === expected, ++epoch);
  };
  const waitPosition = (frame) => page.waitForFunction((expected) => Number(document.querySelector("output").textContent) >= expected, frame);
  for (const frame of settings.paused_seek_samples) {
    if (frame !== 0) await seek(frame);
    result.paused.push(await readPage());
  }
  await seek(settings.play_from_sample);
  await play.click();
  for (const [name, frame] of [["start", settings.play_from_sample], ["forward", settings.forward_seek_sample],
    ["backward", settings.backward_seek_sample]]) {
    if (name !== "start") await seek(frame);
    await waitPosition(frame + settings.wait_after_seek_samples);
    result.live.push({ name, ...await readPage() });
  }
  await page.getByRole("button", { name: "一時停止", exact: true }).click();
  await play.waitFor();
  result.held = [await readPage()];
  await page.waitForTimeout(125);
  result.held.push(await readPage());
  await page.close();
  const broken = await browser.newPage();
  await broken.route("**/voice-1.tele", (route) => route.fulfill({ contentType: "application/octet-stream", body: Buffer.from(damaged) }));
  await broken.goto(`${endpoint}/?show=${showId}`);
  result.badFile = await broken.getByRole("alert").textContent();
  result.invalidCanPlay = await broken.getByRole("button", { name: "再生", exact: true }).count() > 0;
} catch (error) {
  result.failure = String(error);
  throw error;
} finally {
  writeFileSync(join(out, "browser-telemetry.json"), JSON.stringify(result, null, 2) + "\n");
  await browser?.close();
  await new Promise((done) => server.httpServer.close(done));
}
