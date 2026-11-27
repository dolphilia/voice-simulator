// 固定母音の画面を操作し、実際のダウンロードとカーソルの読取値を保存する。
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium, firefox } from "playwright-core";
import { preview } from "vite";

const [dist, testCase, out, firefoxPath] = process.argv.slice(2);
if (!dist || !testCase || !out || !firefoxPath) throw new Error("ビルド、比較ケース、保存先、Firefoxを指定してください");
const { measurement: cfg } = JSON.parse(readFileSync(testCase, "utf8"));
const server = await preview({
  root: fileURLToPath(new URL("../", import.meta.url)),
  build: { outDir: dist },
  preview: { host: "127.0.0.1", port: 0 },
});

async function download(page, stem, ext, directory) {
  const file = `worklet-i${ext}`;
  const pending = page.waitForEvent("download");
  await page.locator(`a[download="${file}"]`).click();
  await (await pending).saveAs(join(directory, `${stem}${ext}`));
}

async function capture(browser, kind) {
  const directory = join(out, kind);
  mkdirSync(directory);
  const [width, height] = cfg.viewports.desktop;
  const page = await browser.newPage({ viewport: { width, height }, acceptDownloads: true });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  try {
    await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/`);
    const toggle = page.getByRole("checkbox", { name: "放射流量を観測する" });
    const run = page.getByRole("button", { name: "固定母音 /i/ をレンダー", exact: true });
    const status = page.getByRole("status").filter({ hasText: /^レンダー完了$/ });
    const scope = page.getByRole("region", { name: "PCMと放射流量" });
    const slider = scope.getByRole("slider", { name: "出力フレーム" });
    const zoom = scope.getByRole("combobox", { name: "表示範囲" });
    const servedWasm = [];
    page.on("response", (response) => {
      if (response.request().resourceType() === "fetch" && response.ok()
          && new URL(response.url()).pathname.endsWith(".wasm")) {
        servedWasm.push(response.body().then((body) => createHash("sha256").update(body).digest("hex")));
      }
    });
    const states = [];
    async function render(stem) {
      await run.click();
      await status.waitFor();
      await download(page, stem, ".wav", directory);
      await download(page, stem, ".json", directory);
      states.push({
        checked: await toggle.isChecked(),
        scope: await scope.count(),
        replay: await page.locator('a[download="worklet-i-case.json"]').count(),
      });
    }
    const checkedInitially = await toggle.isChecked();
    await render("implicit");
    await toggle.check();
    await render("observed");
    await download(page, "observed", "-case.json", directory);

    async function setFrame(frame) {
      await slider.evaluate((input, value) => {
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(input, String(value));
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.dispatchEvent(new Event("change", { bubbles: true }));
      }, frame);
      await page.waitForFunction((frame) => document.querySelector('output[for="radiation-frame"] data')?.value === String(frame),
        frame);
    }
    async function read() {
      return scope.evaluate((root) => ({
        frame: Number(root.querySelector("output data").value),
        time: root.querySelector("output span").textContent,
        accessibleTime: root.querySelector("input[type=range]").getAttribute("aria-valuetext"),
        bounds: [...root.querySelectorAll(".radiation-time-axis span")].map((span) => span.textContent),
        plots: [...root.querySelectorAll("canvas")].map((canvas) => canvas.getAttribute("aria-label")),
        cursorPercent: [...root.querySelectorAll(".radiation-cursor")].map((marker) => Number.parseFloat(marker.style.left)),
        values: [...root.querySelectorAll("dl > div")].map((item) => ({
          label: item.querySelector("dt").textContent,
          value: Number(item.querySelector("data").value),
          displayed: item.querySelector("data").textContent,
          unit: item.querySelector("dd span").textContent,
        })),
      }));
    }

    const cursors = {};
    for (const size of ["all", "zoom"]) {
      await zoom.selectOption(size);
      cursors[size] = [];
      for (const frame of cfg.cursor_frames) {
        await setFrame(frame);
        cursors[size].push(await read());
      }
    }
    await slider.press("Home");
    const home = await read();
    await slider.press("ArrowRight");
    const next = await read();
    await slider.press("End");
    const end = await read();
    const keyboard = [home.frame, next.frame, end.frame];

    const steady = cfg.cursor_frames.at(-2);
    await setFrame(steady);
    const canvas = scope.getByRole("img", { name: "放射成分の時系列" });
    await canvas.scrollIntoViewIfNeeded();
    const box = await canvas.boundingBox();
    const clientX = Math.round(box.x + box.width / 4);
    await page.mouse.click(clientX, Math.round(box.y + box.height / 2));
    const pointer = { fraction: (clientX - box.x) / box.width, ...await read() };
    await scope.screenshot({ path: join(directory, "desktop.png") });

    const [mobileWidth, mobileHeight] = cfg.viewports.mobile;
    await page.setViewportSize({ width: mobileWidth, height: mobileHeight });
    const mobile = await scope.evaluate((root) => ({
      viewport: window.innerWidth,
      sectionWidth: root.clientWidth,
      scrollWidth: root.scrollWidth,
      controlCount: root.querySelectorAll("input, select").length,
    }));
    await scope.screenshot({ path: join(directory, "mobile.png") });

    await zoom.selectOption("all");
    const overview = await scope.getByRole("img", { name: "PCMの時系列" }).evaluate((canvas) => {
      const { width, height } = canvas;
      const rgba = canvas.getContext("2d").getImageData(0, 0, width, height).data;
      const pixels = [180, 384, 576, 720, 864].map((x) => {
        const ys = [];
        for (let y = 0; y < height; y++) {
          const index = (y * width + x) * 4;
          if (rgba[index + 3] > 40 && rgba[index + 2] - rgba[index] > 35 && rgba[index + 1] - rgba[index] > 20) {
            ys.push(y);
          }
        }
        return { x, top: ys[0] ?? null, bottom: ys.at(-1) ?? null };
      });
      return { width, height, pixels };
    });
    await toggle.uncheck();
    await render("disabled");
    writeFileSync(join(directory, "screen.json"), JSON.stringify({
      kind, version: browser.version(), checkedInitially, states, cursors, keyboard, pointer, mobile, overview,
      errors, servedWasm: [...new Set(await Promise.all(servedWasm))],
    }) + "\n", { flag: "wx" });
  } finally {
    await page.close();
  }
}

try {
  for (const kind of cfg.browsers) {
    const browser = kind === "firefox"
      ? await firefox.launch({ executablePath: firefoxPath, headless: true })
      : await chromium.launch();
    try {
      await capture(browser, kind);
    } finally {
      await browser.close();
    }
  }
} finally {
  await server.close();
}
