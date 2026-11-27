import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { chromium } from "playwright-core";

const html = path.resolve(process.argv[2]);
const executablePath = process.env.CHIMERA_CHROMIUM ?? (process.platform === "darwin"
  ? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" : undefined);
const browser = await chromium.launch({ headless: true, executablePath,
  args: ["--mute-audio", "--autoplay-policy=no-user-gesture-required"] });
try {
  const page = await browser.newPage({ viewport: { width: 1240, height: 990 }, acceptDownloads: true });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(pathToFileURL(html).href);
  const items = page.locator("section[data-trial]");
  const images = await page.locator("img").evaluateAll((imgs) => imgs.map((img) => img.naturalWidth));
  const audio = page.locator("audio");
  const playback = [];
  for (const clip of await audio.all()) {
    await clip.evaluate(async (element) => { await element.play(); });
    await page.waitForFunction(() => [...document.querySelectorAll("audio")].some((el) => !el.paused && el.currentTime > 0));
    playback.push(await clip.evaluate((el) => el.currentTime > 0 && el.error === null));
    await clip.evaluate((element) => element.pause());
  }
  await page.screenshot({ path: path.join(path.dirname(process.argv[3]), "review-preview.png") });
  await page.setViewportSize({ width: 390, height: 840 });
  const fits = await page.evaluate(() => document.documentElement.clientWidth === document.documentElement.scrollWidth);

  for (const [index, status, frequency, note] of [
    [0, "measured", "2000", '帯の連続, "比較"\n中央窓'], [1, "ambiguous", "", "帯が重なる"],
    [2, "unusable", "", "境界の前後が不明"], [3, "measured", "1700", "連続帯を確認"],
  ]) {
    const item = items.nth(index);
    await item.locator("select").selectOption(status);
    if (frequency) await item.locator("input").fill(frequency);
    await item.locator("textarea").fill(note);
  }
  const [download] = await Promise.all([
    page.waitForEvent("download"), page.getByRole("button", { name: "注釈をCSVで保存" }).click(),
  ]);
  const csv = await readFile(await download.path());
  await writeFile(process.argv[3], csv, { flag: "wx" });
  const checks = { seven_images: images.length === 7 && images.every((width) => width > 0),
    seven_clips: playback.length === 7 && playback.every(Boolean), mobile_width: fits,
    no_page_errors: errors.length === 0, csv_download: download.suggestedFilename() === "tsp-f2-observations.csv" };
  console.log(JSON.stringify({ version: browser.version(), checks, errors }, null, 2));
  if (!Object.values(checks).every(Boolean)) process.exitCode = 1;
} finally {
  await browser.close();
}
