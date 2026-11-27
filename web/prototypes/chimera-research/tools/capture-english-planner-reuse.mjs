// 同じモジュールと毎回コンパイルしたモジュールの英語計画をブラウザで比較する。
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { firefox } from "playwright-core";
import { createServer } from "vite";

const [outDir, casePath, fixturePath] = process.argv.slice(2);
if (!outDir || !casePath || !fixturePath) throw new Error("出力先、比較ケース、発話ケースを指定してください");
const { measurement: { probe } } = JSON.parse(readFileSync(casePath, "utf8"));
const fixture = JSON.parse(readFileSync(fixturePath, "utf8"));
const root = fileURLToPath(new URL("../", import.meta.url));
const planningPath = fileURLToPath(new URL(
  "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/planning.ts",
  import.meta.url,
));
const server = await createServer({ root, server: { host: "127.0.0.1", port: 0, hmr: false, watch: null } });
try {
  await server.listen();
  const url = `http://127.0.0.1:${server.httpServer.address().port}/`;
  const browser = await firefox.launch({ headless: true, executablePath: process.env.CHIMERA_FIREFOX });
  try {
    const page = await browser.newPage();
    await page.goto(url);
    const transitions = await page.evaluate(async ({ probe, planningPath }) => {
      const { loadFixedModule } = await import("/src/render-fixed-voice.ts");
      const { planEnglish } = await import(`/@fs${planningPath}`);
      const modules = new Map();
      WebAssembly.Instance = class extends WebAssembly.Instance {
        constructor(module, imports) {
          super(module, imports);
          if (modules.has(module)) modules.set(module, modules.get(module) + 1);
        }
      };
      const load = async () => {
        const module = await loadFixedModule();
        modules.set(module, 0);
        return module;
      };
      const encoder = new TextEncoder();
      const dictionary = encoder.encode(probe.dictionaries[0]);
      const alternate = encoder.encode(probe.dictionaries[1]);
      const snapshot = (result) => {
        const { words, ...metadata } = result.score;
        const bytes = new Uint8Array(words.buffer, words.byteOffset, words.byteLength);
        return { plan: { ...result, score: metadata }, scoreHex: Array.from(bytes, (n) =>
          n.toString(16).padStart(2, "0")).join("") };
      };
      const plan = (module, text, lexicon) =>
        planEnglish(module, text, lexicon, probe.start_seconds, probe.rate, probe.f0_hz, probe.body);
      const run = async (shared) => {
        const rows = [];
        const used = new Set();
        const original = encoder.encode(probe.dictionaries[0]);
        const steps = [
          ["long", probe.long_text, original],
          ["short", probe.short_text, original],
          ["new_dictionary", probe.short_text, alternate],
          ["invalid_dictionary", probe.short_text, Uint8Array.of(255)],
          ["restored", probe.long_text, original],
        ];
        let first;
        for (const [name, text, bytes] of steps) {
          const module = shared ?? await load();
          used.add(module);
          // 辞書差し替え時に、呼び出し側の同じ配列も再利用する。
          if (bytes.length === dictionary.length) dictionary.set(bytes);
          const lexicon = bytes.length === dictionary.length ? dictionary : bytes;
          try {
            const result = plan(module, text, lexicon);
            first ??= result;
            rows.push({ name, ...snapshot(result) });
          } catch (error) {
            rows.push({ name, error: error.message });
          }
        }
        return { rows, retainedFirst: snapshot(first), instances: [...used].map((module) => modules.get(module)) };
      };
      const shared = await run(await load());
      const fresh = await run();
      return { shared, fresh };
    }, { probe, planningPath });
    await page.close();

    const retryPage = await browser.newPage();
    let wasmRequests = 0;
    await retryPage.route(/\.wasm(?:\?|$)/, (route) => {
      if (route.request().resourceType() !== "fetch") return route.continue();
      return ++wasmRequests === 1
        ? route.fulfill({ status: 503, body: "WASMの取得に失敗" })
        : route.continue();
    });
    await retryPage.goto(url);
    const retry = await retryPage.evaluate(async (fixture) => {
      const { renderEnglishVoice } = await import("/src/render-fixed-voice.ts");
      const { readEnglishSpeechCase } = await import("/src/english-speech-case.ts");
      const { config, text, rate, start, inputId } = readEnglishSpeechCase(fixture);
      const render = () => renderEnglishVoice(config, text, rate, 32, start, inputId);
      let firstError;
      try {
        await render();
      } catch (error) {
        firstError = error.message;
      }
      const result = await render();
      return { firstError, frames: result.audio.length, speech: result.report.speech };
    }, fixture);
    writeFileSync(join(outDir, "english-planner-reuse.json"),
      JSON.stringify({ browser: browser.version(), transitions, retry: { ...retry, wasmRequests } }) + "\n");
  } finally {
    await browser.close();
  }
} finally {
  await server.close();
}
