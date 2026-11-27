import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { chromium } from "playwright-core";

const html = path.resolve(process.argv[2]);
const exportedCsv = process.argv[3];
const executablePath = process.env.CHIMERA_CHROMIUM ??
  (process.platform === "darwin" ? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" : undefined);
const browser = await chromium.launch({
  headless: true,
  executablePath,
  args: ["--autoplay-policy=no-user-gesture-required", "--mute-audio"],
});

async function waveDuration(wav) {
  const bytes = await readFile(wav);
  if (bytes.toString("ascii", 0, 4) !== "RIFF" || bytes.toString("ascii", 8, 12) !== "WAVE" ||
      bytes.toString("ascii", 36, 40) !== "data") {
    throw new Error("試聴用のWAVヘッダーが生成条件と一致しません");
  }
  return bytes.readUInt32LE(40) / bytes.readUInt32LE(28);
}

try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 850 }, acceptDownloads: true });
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.goto(pathToFileURL(html).href);
  const media = page.locator("audio");
  const sourceNames = await media.evaluateAll((items) => items.map((item) => item.getAttribute("src")));
  const seconds = await Promise.all(sourceNames.map((name) => waveDuration(path.join(path.dirname(html), name))));
  const controls = [];
  const switchStates = [];
  for (const [index, name] of sourceNames.entries()) {
    await media.nth(index).evaluate((item) => item.play());
    await page.waitForFunction((name) => {
      const item = [...document.querySelectorAll("audio")].find((audio) => audio.getAttribute("src") === name);
      return item.readyState >= 2 && item.currentTime > 0.02;
    }, name, { timeout: 3000 });
    const observed = await media.nth(index).evaluate((item) => ({
      duration: item.duration, currentTime: item.currentTime, error: item.error,
    }));
    switchStates.push(await media.evaluateAll((items, i) =>
      items.every((item, index) => index === i || item.paused), index));
    controls.push({ file: name, expected_seconds: seconds[index], decoded_seconds: observed.duration,
      advanced: observed.currentTime > 0.02 && observed.error === null });
  }
  await media.last().evaluate((item) => item.pause());

  const widths = [];
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 850 });
    widths.push(await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      documentWidth: document.documentElement.scrollWidth,
    })));
  }
  const first = page.locator("[data-trial='01']");
  await first.locator("[data-field='a_periodic_pitch']").selectOption("2");
  await first.locator("[data-field='b_periodic_pitch']").selectOption("判定不能");
  await first.locator("[data-field='naturalness_preference']").selectOption("C");
  await first.locator("[data-field='observations']").fill('音の入り, "比較"\n余韻');
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "試聴結果をCSVで保存" }).click(),
  ]);
  const csv = await readFile(await download.path(), "utf8");
  if (exportedCsv) await writeFile(exportedCsv, csv, { flag: "wx" });
  const packetId = await page.locator("#observations").getAttribute("data-packet-id");
  const prefix = packetId === null ? "" : `"${packetId}",`;
  const headerPrefix = packetId === null ? "" : '"packet_id",';
  const result = {
    browser_version: browser.version(),
    packet_id: packetId,
    checks: {
      eighteen_local_waves_play: controls.length === 18 && controls.every((r) =>
        r.advanced && Math.abs(r.expected_seconds - r.decoded_seconds) <= 1 / 48000),
      playing_one_clip_pauses_the_others: switchStates.every(Boolean),
      desktop_and_mobile_fit: widths.every((w) => w.viewport === w.documentWidth),
      exported_observations_csv: download.suggestedFilename() === "csd-listening-observations.csv" &&
        (packetId === null || /^[0-9a-f]{64}$/.test(packetId)) &&
        csv.startsWith(`\uFEFF${headerPrefix}"trial","a_periodic_pitch","b_periodic_pitch","c_periodic_pitch","naturalness_preference","observations"\r\n`) &&
        csv.includes(`${prefix}"01","2","判定不能","","C","音の入り, ""比較""\n余韻"\r\n`) &&
        csv.includes(`${prefix}"06","","","","",""\r\n`) && csv.trimEnd().split("\r\n").length === 7,
      no_page_errors: pageErrors.length === 0,
    },
    media: controls,
    widths,
    page_errors: pageErrors,
  };
  console.log(JSON.stringify(result, null, 2));
  if (!Object.values(result.checks).every(Boolean)) process.exitCode = 1;
} finally {
  await browser.close();
}
