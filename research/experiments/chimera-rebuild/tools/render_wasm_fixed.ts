// 測定点でブロックを分割し、全PCMと同じ時刻の観測値を保存する。
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import {
  FixedVoiceEngine,
  OBSERVATION_FIELDS,
  type FixedVoiceInput,
} from "../crates/vocal-wasm/host/fixed-voice.ts";

type Measure = {
  output_frames: number;
  host_block_frames: number[];
  observation_stride_frames: number;
  additional_observation_frames: number[];
};

function main(): void {
  const [binary, fixedCase, testCase, outDir] = process.argv.slice(2);
  if (!binary || !fixedCase || !testCase || !outDir) {
    throw new Error("WASM、固定発声の入力、比較ケース、出力先を指定してください");
  }
  const module = new WebAssembly.Module(readFileSync(binary));
  const input: FixedVoiceInput = JSON.parse(readFileSync(fixedCase, "utf8"));
  const { measurement: m }: { measurement: Measure } = JSON.parse(readFileSync(testCase, "utf8"));
  const frames = m.output_frames;
  const points = new Set(m.additional_observation_frames);
  for (let frame = 0; frame < frames; frame += m.observation_stride_frames) {
    points.add(frame);
  }
  const checkpoints = [...points].sort((a, b) => a - b);
  const observations: Record<number, number[][]> = {};
  const stableBuffers: Record<number, boolean> = {};
  for (const block of m.host_block_frames) {
    const engine = new FixedVoiceEngine(module, input);
    try {
      if (block > engine.maxFrames) {
        throw new Error(`指定ブロック長 ${block} がWASMの上限を超えています`);
      }
      const audio = new Float32Array(frames);
      const values: number[][] = [];
      let checkpoint = 0;
      let stable = engine.buffersAreStable();
      let start = 0;
      while (start < frames) {
        const boundary = (Math.floor(start / block) + 1) * block;
        const observeAt = (checkpoints[checkpoint] ?? frames) + 1;
        const end = Math.min(frames, boundary, observeAt);
        engine.renderInto(audio.subarray(start, end));
        if (end === observeAt) {
          stable = engine.buffersAreStable() && stable;
          values.push(Array.from(engine.readObservation()));
          checkpoint++;
        }
        start = end;
      }
      observations[block] = values;
      stableBuffers[block] = stable && engine.buffersAreStable();
      writeFileSync(join(outDir, `wasm-${block}.f32`), Buffer.from(audio.buffer), { flag: "wx" });
    } finally {
      engine.close();
    }
  }
  const evidence = {
    imports: WebAssembly.Module.imports(module),
    fields: OBSERVATION_FIELDS,
    observations,
    stable_buffers: stableBuffers,
  };
  writeFileSync(
    join(outDir, "wasm-observations.json"), JSON.stringify(evidence) + "\n", { flag: "wx" },
  );
}

main();
