import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { chromium } from "playwright-core";
import { preview } from "vite";
import { DuetHeadEchoes, advanceDuetMotionTime } from "../src/duet-head-echoes.ts";
import { DuetTeleTrack } from "../src/duet-telemetry.ts";
import { createDuetHeadGeometry } from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/duet-head.ts";

const [caseFile, upstream, artifacts] = process.argv.slice(2);
const spec = JSON.parse(readFileSync(caseFile, "utf8"));
const root = fileURLToPath(new URL("../", import.meta.url));
const demo = join(root, "public", "shows", "duet-clock");
const rate = spec.sample_rate_hz;
const options = spec.browser;

function installProbe({ minShift, range, rate }) {
  const read = (canvas) => {
    let value;
    canvas.dispatchEvent(new CustomEvent("chimera:read-duet-echoes", { detail: (frame) => { value = frame; } }));
    return value;
  };
  const distance = (next, old) => Math.max(...next.map((value, j) => Math.abs(value - old[j])));
  window.echoTrace = [];
  window.echoPhotos = {};
  new MutationObserver(() => {
    const node = document.querySelector('output[aria-label="音源フレーム"]');
    const canvases = [...document.querySelectorAll(".duet-heads canvas")];
    if (!node || canvases.length !== 2) return;
    const heads = canvases.map(read);
    if (heads.some((head) => !head)) return;
    const clock = heads[0].clock;
    const sample = +node.textContent;
    if (heads[1].clock.motionTime !== clock.motionTime || heads[1].clock.epoch !== clock.epoch || clock.epoch !== +node.dataset.epoch) return;
    const prior = window.echoTrace.at(-1);
    if (!prior || prior.clock.motionTime !== clock.motionTime || prior.clock.epoch !== clock.epoch
        || prior.clock.playing !== clock.playing) {
      const entry = { clock, sample, heads };
      window.echoTrace.push(entry);
      const [first] = heads;
      if (clock.playing && !window.echoPhotos.playing && sample >= range[0] && sample <= range[1]
          && Math.floor(sample / 768) === Math.floor(clock.time * rate / 768)
          && first.slots.every(Boolean)
          && first.slots.some((slot) => distance(first.base[3], slot.contours[3]) >= minShift)) {
        window.echoPhotos.playing = { epoch: clock.epoch, sample, data: canvases[0].toDataURL() };
      }
      if (!clock.playing && sample === window.echoPhotos.expectPaused && clock.epoch === window.echoPhotos.expectEpoch) {
        window.echoPhotos.paused = { epoch: clock.epoch, sample, data: canvases[0].toDataURL() };
      }
    }
  }).observe(document, { attributes: true, attributeFilter: ["data-head-epoch"], subtree: true });
}

async function capture(browser, endpoint, width, height, errors) {
  const page = await browser.newPage({ viewport: { width, height } });
  page.on("pageerror", (error) => errors.push(error.message));
  const markers = {};
  try {
    await page.addInitScript(installProbe, { minShift: options.minimum_picture_lip_displacement_cm,
      range: options.picture_range_samples, rate });
    await page.goto(endpoint);
    await page.getByRole("link", { name: "デュエットの再生時計", exact: true }).click();
    const slider = page.getByRole("slider", { name: "音源の位置", exact: true });
    let epoch = 0;
    const seek = async (sample) => {
      await slider.evaluate((input, time) => {
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(input, String(time));
        input.dispatchEvent(new Event("input", { bubbles: true }));
      }, sample / rate);
      const target = ++epoch;
      const entry = await page.waitForFunction((value) => {
        const index = window.echoTrace.findIndex((item) => item.clock.epoch === value);
        return index >= 0 && { index };
      }, target);
      try { return (await entry.jsonValue()).index; }
      finally { await entry.dispose(); }
    };
    const waitAt = async (value, playing) => {
      const match = await page.waitForFunction(({ value, playing }) => {
        const index = window.echoTrace.findIndex((row) => row.clock.epoch === value && row.clock.playing === playing);
        return index >= 0 && { index };
      }, { value, playing });
      try { return (await match.jsonValue()).index; }
      finally { await match.dispose(); }
    };
    await waitAt(0, false);
    // 同じ調音行の画素から残像の寄与だけを測る。
    await page.getByRole("checkbox", { name: "表情と頭部の動き", exact: true }).uncheck();
    await seek(options.start_sample);
    const play = () => page.getByRole("button", { name: "再生", exact: true }).click();
    const pause = () => page.getByRole("button", { name: "一時停止", exact: true }).click();
    await play();
    markers.firstPlay = await waitAt(epoch, true);
    const advance = async (at) => {
      await page.waitForFunction(({ sample, epoch }) => {
        const row = window.echoTrace.at(-1);
        return row?.clock.epoch === epoch && row.sample >= sample;
      }, { sample: at + options.seek_advance_samples, epoch });
    };
    await page.waitForFunction(() => !!window.echoPhotos.playing);
    const photo = await page.evaluate(() => window.echoPhotos.playing);
    markers.liveSeeks = [];
    for (const at of options.live_seek_samples) {
      markers.liveSeeks.push(await seek(at));
      await advance(at);
    }
    await pause();
    markers.pause = await waitAt(epoch, false);
    await page.waitForTimeout(options.pause_ms);
    markers.hold = await page.evaluate(() => window.echoTrace.length - 1);
    markers.pausedSeek = await seek(options.paused_seek_sample);
    await play();
    markers.resume = await waitAt(epoch, true);
    await advance(options.paused_seek_sample);
    await pause();

    await page.evaluate(({ sample, epoch }) => {
      window.echoPhotos.expectPaused = sample;
      window.echoPhotos.expectEpoch = epoch;
    }, { sample: photo.sample, epoch: epoch + 1 });
    markers.picturePaused = await seek(photo.sample);
    const measured = await page.evaluate(() => ({ trace: window.echoTrace, photos: window.echoPhotos }));
    for (const phase of ["playing", "paused"]) {
      const shot = measured.photos[phase];
      if (!shot?.data.startsWith("data:image/png;base64,")) throw new Error(`${width}pxの${phase}で画素を採取できません`);
      const path = `echo-${width}-${phase}.png`;
      writeFileSync(join(artifacts, path), Buffer.from(shot.data.split(",")[1], "base64"));
      measured.photos[phase] = { ...shot, data: undefined, path };
    }
    return { width, markers, ...measured };
  } finally {
    await page.close();
  }
}

// 固定上流の描画を実行し、Beamsに渡った同じ配列を採取する。
const upperImport = (path) => import(pathToFileURL(join(upstream, path)));
const { initChimera } = await upperImport("src/wasm/chimera.ts");
await initChimera(readFileSync(join(upstream, "target/wasm32-unknown-unknown/release/chimera_wasm.wasm")));
const { VoiceModel } = await upperImport("src/ui/analysis.ts");
const { TeleTrack } = await upperImport("src/show/tele.ts");
const { Anatomy3D } = await upperImport("src/ui/render/anatomy3d.ts");
const { airwayFrame, airwayModel, dropAirwayModel } = await upperImport("src/wasm/engine.ts");
const candidateWasm = new WebAssembly.Module(readFileSync(join(root,
  "../../../research/experiments/chimera-rebuild/target/wasm32-unknown-unknown/release/vocal_wasm.wasm")));
const control = [1, 2].map((voice) => {
  const bytes = Uint8Array.from(readFileSync(join(demo, `voice-${voice}.tele`)));
  const upper = new TeleTrack(bytes.buffer), candidateTrack = new DuetTeleTrack(bytes.buffer);
  const flag = { pressure: true, particles: true, grid: false, calipers: false };
  const model = new VoiceModel(upper.body, rate);
  const direct = airwayModel(upper.body, rate);
  const renderer = new Anatomy3D();
  renderer.camera.position.set(0, 9, 100);
  renderer.camera.lookAt(0, 9, 0);
  const makeShape = createDuetHeadGeometry(candidateWasm, candidateTrack.body);
  const candidate = new DuetHeadEchoes();
  let rowForTime = new Map(), current;
  const nearest = renderer.nearestEcho.bind(renderer);
  renderer.nearestEcho = (time) => {
    const echo = nearest(time);
    current = echo && { time: echo.t, ...rowForTime.get(echo.t), lines: [], expected: echo.lines.map((line) => line.a) };
    picked.push(current);
    return echo;
  };
  const line = renderer.beams.line.bind(renderer.beams);
  renderer.beams.line = (points, count, color, width, config) => {
    if (current && current.expected[current.lines.length] === points) {
      current.lines.push({ alpha: config.alpha, vertices: Array.from(points) });
    }
    return line(points, count, color, width, config);
  };
  let picked = [], epoch = -1, visualTime = 0;
  try {
    return spec.controlled_clock.map(([elapsed, sample, playing, nextEpoch]) => {
      const reset = epoch !== nextEpoch;
      if (reset) {
        renderer.resetMotion();
        rowForTime = new Map();
      }
      epoch = nextEpoch;
      const index = upper.indexAt(sample / rate);
      const message = upper.message(index);
      const pose = VoiceModel.articFromArray(message.t.artic);
      const directShape = airwayFrame(direct, pose);
      visualTime = advanceDuetMotionTime(visualTime, elapsed);
      rowForTime.set(visualTime, { sample, epoch, index });
      picked = [];
      current = null;
      renderer.update(model, model.frame(pose), pose, playing ? message : null, flag, Math.min(0.05, elapsed / 1000));
      const expectedOpening = directShape.upperLip[6].y - directShape.lowerLip[6].y > 0.02 * model.tract.scale;
      const directTongue = directShape.tongue.flatMap(({ x, y }) => [x, y]);
      const result = candidate.update(visualTime, playing, reset, () => {
        const shape = makeShape(candidateTrack.frame(candidateTrack.indexAt(sample / rate)).artic);
        return { sample, epoch, index, tongue: Array.from(shape.paths.tongue) };
      });
      return { sample, index, epoch, playing, upperTime: renderer.clock, candidateTime: visualTime, expectedOpening,
        directTongue, upper: picked.map((item) => item && { ...item, expected: undefined }),
        candidate: result };
    });
  } finally {
    dropAirwayModel(direct);
    renderer.dispose();
    model.dispose();
  }
});
writeFileSync(join(artifacts, "controlled-echoes.json"), JSON.stringify(control) + "\n");

const host = "127.0.0.1";
const server = await preview({ root, preview: { host, port: 0 } });
const result = { viewports: [], errors: [] };
let browser;
try {
  browser = await chromium.launch({ headless: true, executablePath: process.env.CHIMERA_CHROMIUM,
    args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
  result.browser = browser.version();
  const endpoint = `http://${host}:${server.httpServer.address().port}`;
  for (const [width, height] of options.viewports) {
    result.viewports.push(await capture(browser, endpoint, width, height, result.errors));
  }
} finally {
  if (browser) await browser.close();
  await new Promise((resolve) => server.httpServer.close(resolve));
  writeFileSync(join(artifacts, "browser-echoes.json"), JSON.stringify(result) + "\n");
}
