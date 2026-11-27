// 通常の固定発声ホストとOfflineAudioContextで、放射観測の有無を比較する。
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";
import { createServer } from "vite";
import {
  FixedVoiceEngine, OBSERVATION_FIELDS, RADIATION_COLUMNS,
} from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/fixed-voice.ts";

const [binary, source, testCase, out] = process.argv.slice(2);
if (!binary || !source || !testCase || !out) throw new Error("Wasm、固定発声ケース、比較ケース、保存先を指定してください");
const input = JSON.parse(readFileSync(source, "utf8"));
const { measurement: cfg } = JSON.parse(readFileSync(testCase, "utf8"));
const frames = cfg.comparison_output_frames[1];
const mod = new WebAssembly.Module(readFileSync(binary));
const { fixed_voice_probe, ...implicit } = input;
const disabled = { ...implicit, fixed_voice_probe: { radiation_components: false } };
const save = (name, value) => writeFileSync(join(out, name), value, { flag: "wx" });
const json = (name, value) => save(name, JSON.stringify(value) + "\n");
const bytes = (view) => Buffer.from(view.buffer, view.byteOffset, view.byteLength);

function rejects(action) {
  try {
    action();
    return false;
  } catch {
    return true;
  }
}

const host = {};
for (const block of cfg.host_block_frames) {
  for (const [kind, spec] of [["enabled", input], ["implicit", implicit], ["disabled", disabled]]) {
    const engine = new FixedVoiceEngine(mod, spec);
    const key = `${kind}-${block}`;
    const pcm = new Float32Array(frames);
    const radiation = new Float64Array(kind === "enabled" ? frames * RADIATION_COLUMNS.length : 0);
    const rows = [];
    const missingBefore = rejects(() => engine.copyRadiationTraceTo(radiation, 0));
    let stable = engine.buffersAreStable();
    let rejectedInvalidOffset = false;
    let missingWhileDisabled = true;
    try {
      for (let first = 0; first < frames; first += block) {
        engine.renderInto(pcm.subarray(first, first + block));
        rows.push(Array.from(engine.readObservation()));
        stable = engine.buffersAreStable() && stable;
        if (kind === "enabled") {
          engine.copyRadiationTraceTo(radiation, first);
          if (first === 0) {
            rejectedInvalidOffset = rejects(() => engine.copyRadiationTraceTo(radiation, -1))
              && rejects(() => engine.copyRadiationTraceTo(radiation, frames));
          }
        } else {
          missingWhileDisabled = rejects(() => engine.copyRadiationTraceTo(radiation, first)) && missingWhileDisabled;
        }
      }
    } finally {
      engine.close();
    }
    const missingAfter = rejects(() => engine.copyRadiationTraceTo(radiation, 0));
    host[key] = { rows, stable, missingBefore, missingAfter, missingWhileDisabled, rejectedInvalidOffset };
    save(`host-${key}.f32`, bytes(pcm));
    if (kind === "enabled") save(`host-${key}.f64`, bytes(radiation));
  }
}
const raw = new WebAssembly.Instance(mod).exports;
json("host.json", {
  imports: WebAssembly.Module.imports(mod), layout: raw.vocal_layout_version(),
  legacyFields: OBSERVATION_FIELDS, radiationFields: RADIATION_COLUMNS, host,
});

const server = await createServer({
  root: fileURLToPath(new URL("../", import.meta.url)),
  server: { host: "127.0.0.1", port: 0, hmr: false, watch: null },
});
try {
  await server.listen();
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    const errors = [];
    const servedWasm = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("response", (response) => {
      if (response.request().resourceType() === "fetch" && response.ok()
          && new URL(response.url()).pathname.endsWith("/vocal_wasm.wasm")) {
        servedWasm.push(response.body().then((body) => createHash("sha256").update(body).digest("hex")));
      }
    });
    await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/`);
    const captures = {};
    for (const [kind, spec] of [["enabled", input], ["implicit", implicit], ["disabled", disabled]]) {
      const capture = await page.evaluate(async ({ spec, stride }) => {
        const { renderFixedVoice } = await import("/src/render-fixed-voice.ts");
        const { audio, report: { radiation, ...report } } = await renderFixedVoice(spec, stride);
        const encode = (view) => {
          const data = new Uint8Array(view.buffer, view.byteOffset, view.byteLength);
          let binary = "";
          for (let i = 0; i < data.length; i += 8192) {
            binary += String.fromCharCode(...data.subarray(i, i + 8192));
          }
          return btoa(binary);
        };
        return {
          report,
          pcm: encode(audio.getChannelData(0)),
          fields: radiation?.columns ?? null,
          radiation: radiation ? encode(new Float64Array(radiation.values)) : null,
        };
      }, { spec, stride: cfg.worklet_observation_stride });
      const { pcm, radiation, ...rest } = capture;
      save(`browser-${kind}.f32`, Buffer.from(pcm, "base64"));
      if (radiation !== null) save(`browser-${kind}.f64`, Buffer.from(radiation, "base64"));
      captures[kind] = rest;
    }
    json("browser.json", { version: browser.version(), errors, servedWasm: [...new Set(await Promise.all(servedWasm))],
      captures });
  } finally {
    await browser.close();
  }
} finally {
  await server.close();
}
