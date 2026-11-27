// 固定姿勢の通常Wasmホストから、出力フレーム順の放射とPCMを保存する。
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { FixedVoiceEngine, RADIATION_COLUMNS } from "../crates/vocal-wasm/host/fixed-voice.ts";

const [wasmPath, casePath, out, name, ...blocks] = process.argv.slice(2);
if (!wasmPath || !casePath || !out || !name || !blocks.length) {
  throw new Error("Wasm、ケース、保存先、条件名、ホストのブロック長を指定してください");
}
const module = new WebAssembly.Module(readFileSync(wasmPath));
const input = JSON.parse(readFileSync(casePath, "utf8"));
const frames = input.fixed_airway.sample_count * input.voice.output_sample_rate_hz / input.fixed_airway.sample_rate_hz;
const results = [];
for (const block of blocks.map(Number)) {
  const engine = new FixedVoiceEngine(module, input);
  const pcm = new Float32Array(frames);
  const radiation = new Float64Array(frames * RADIATION_COLUMNS.length);
  try {
    let stable = engine.buffersAreStable();
    for (let start = 0; start < frames; start += block) {
      engine.renderInto(pcm.subarray(start, start + block));
      engine.copyRadiationTraceTo(radiation, start);
      stable = stable && engine.buffersAreStable();
    }
    const [end] = engine.readObservation();
    results.push({ block, stable, outputFrames: end });
    writeFileSync(join(out, `${name}-wasm-${block}.f32`), Buffer.from(pcm.buffer), { flag: "wx" });
    writeFileSync(join(out, `${name}-wasm-${block}.f64`), Buffer.from(radiation.buffer), { flag: "wx" });
  } finally {
    engine.close();
  }
}
writeFileSync(join(out, `${name}-wasm.json`), JSON.stringify({ fields: RADIATION_COLUMNS, results }) + "\n", { flag: "wx" });
