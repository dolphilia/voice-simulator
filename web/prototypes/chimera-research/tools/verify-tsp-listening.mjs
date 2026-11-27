import { readFile, writeFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";
import { chromium } from "playwright-core";

const [html, csvPath] = process.argv.slice(2);
const executablePath = process.env.CHIMERA_CHROMIUM ?? (process.platform === "darwin"
  ? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" : undefined);
const browser = await chromium.launch({ headless: true, executablePath,
  args: ["--mute-audio", "--autoplay-policy=no-user-gesture-required"] });

try {
  const page = await browser.newPage({ viewport: { width: 960, height: 840 }, acceptDownloads: true });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(pathToFileURL(html).href);
  const pairs = page.locator("section[data-pair]");
  const files = await page.locator("audio").evaluateAll(async (clips) => Promise.all(clips.map((clip) =>
    new Promise((resolve) => {
      clip.addEventListener("loadedmetadata", () => resolve([clip.getAttribute("src"), clip.duration]), { once: true });
      clip.addEventListener("error", () => resolve([clip.getAttribute("src"), null]), { once: true });
      clip.preload = "metadata";
      clip.load();
    }))));
  const clips = pairs.first().locator("audio");
  await clips.first().evaluate((clip) => clip.play());
  await page.waitForFunction(() => document.querySelector("audio").currentTime > 0);
  await clips.last().evaluate((clip) => clip.play());
  const exclusive = await clips.first().evaluate((clip) => clip.paused);
  await clips.last().evaluate((clip) => clip.pause());

  await page.setViewportSize({ width: 390, height: 840 });
  const fits = await page.evaluate(() => document.documentElement.scrollWidth === document.documentElement.clientWidth);
  for (const [pair, tempo, pauses, note] of [
    ["01", "A", "B", '速さの差, "比較"\n文中の間'],
    ["02", "same", "unsure", ""],
    ["07", "B", "A", ""],
  ]) {
    const item = page.locator(`section[data-pair="${pair}"]`);
    await item.locator(".tempo").selectOption(tempo);
    await item.locator(".pauses").selectOption(pauses);
    await item.locator("textarea").fill(note);
  }
  const [download] = await Promise.all([
    page.waitForEvent("download"), page.getByRole("button", { name: "回答をCSVで保存" }).click(),
  ]);
  await writeFile(csvPath, await readFile(await download.path()), { flag: "wx" });
  const checks = { all_pairs: await pairs.count() === 18,
    readable_audio: files.length === 36 && files.every(([, duration]) => duration > 0),
    exclusive_playback: exclusive, mobile_width: fits, no_page_errors: errors.length === 0,
    csv_download: download.suggestedFilename() === "tsp-listening-observations.csv" };
  console.log(JSON.stringify({ version: browser.version(), checks, files, errors }, null, 2));
  if (!Object.values(checks).every(Boolean)) process.exitCode = 1;
} finally {
  await browser.close();
}
