// Chromeの標準権限ダイアログを、独立したプロファイルで照合する。
import { execFileSync, spawn } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { once } from "node:events";
import { join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";
import { createServer, preview } from "vite";

const [casePath, dist, upstream, scratch, artifacts, helper] = process.argv.slice(2);
const { browser: config, targets } = JSON.parse(readFileSync(casePath, "utf8"));
const root = fileURLToPath(new URL("../", import.meta.url));
const chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const profile = join(scratch, "chrome-profile");
const options = { host: config.origin_binding, port: 0 };
const buttonNames = {
  deny: /^(Block|Don.t allow|Never allow|ブロック|許可しない|許可しない（推奨）)$/,
  allow: /^(Allow while visiting (the|this) site|Allow on every visit|Allow|Allow this time|許可|許可する|今回のみ許可|サイトの閲覧中は許可|サイトへのアクセス中は許可)$/,
};

function observeMidi() {
  const original = navigator.requestMIDIAccess.bind(navigator);
  const requests = [];
  const connections = [];
  Object.defineProperty(navigator, "requestMIDIAccess", { configurable: true, value: (options) => {
    const event = { options, outcome: null };
    requests.push(event);
    return original(options).then((access) => {
      const listeners = new Set();
      const add = access.addEventListener.bind(access), remove = access.removeEventListener.bind(access);
      access.addEventListener = (type, fn, ...args) => {
        if (type === "statechange") listeners.add(fn);
        return add(type, fn, ...args);
      };
      access.removeEventListener = (type, fn, ...args) => {
        if (type === "statechange") listeners.delete(fn);
        return remove(type, fn, ...args);
      };
      connections.push({ access, listeners });
      Object.assign(event, { outcome: "granted", inputs: access.inputs.size, sysexEnabled: access.sysexEnabled });
      return access;
    }, (error) => {
      event.outcome = error.name;
      throw error;
    });
  } });
  globalThis.readMidiPromptProbe = () => ({
    requests,
    subscriptions: connections.map(({ access, listeners }) => listeners.size + Number(Boolean(access.onstatechange))),
  });
}

async function waitFor(observe, reason) {
  const end = Date.now() + config.timeout_ms;
  do {
    const result = await observe();
    if (result) return result;
    await delay(160);
  } while (Date.now() < end);
  throw new Error(reason);
}

function browserUI(pid, action, ...args) {
  const result = execFileSync(helper, [String(pid), action, ...args], { encoding: "utf8", timeout: 6000 });
  return result ? JSON.parse(result) : undefined;
}

const labels = (control) => [control.title, control.description, control.value].filter(Boolean);
function permissionControls(snapshot, origin) {
  if (!snapshot.controls.some((control) => control.role === "AXWindow" &&
      labels(control).some((value) => value.includes(origin) && /midi/i.test(value)))) return {};
  const found = {};
  for (const [kind, pattern] of Object.entries(buttonNames)) {
    for (const control of snapshot.controls) {
      if (control.role !== "AXButton" || !control.windowTitle?.includes(origin) || !/midi/i.test(control.windowTitle)) continue;
      const label = labels(control).find((value) => pattern.test(value));
      if (label) {
        found[kind] = { label };
        break;
      }
    }
  }
  return found;
}

const readProbe = (page) => page.evaluate(() => globalThis.readMidiPromptProbe());
const permission = (page) => page.evaluate(async (descriptor) => (await navigator.permissions.query(descriptor)).state,
  config.permission);

async function decide(pid, target, kind, origin, report) {
  const entry = { requested: kind };
  report.dialogs.push(entry);
  const prompt = await waitFor(() => {
    const snapshot = browserUI(pid, "snapshot");
    entry.lastSnapshot = snapshot;
    const buttons = permissionControls(snapshot, origin);
    return snapshot.frontmost && buttons.deny && buttons.allow ? { snapshot, buttons } : null;
  }, `標準ダイアログのボタンが観測できませんでした (${target}/${kind})`);
  entry.snapshot = prompt.snapshot;
  delete entry.lastSnapshot;
  entry.buttons = Object.fromEntries(Object.entries(prompt.buttons).map(([role, button]) => [role, button.label]));
  entry.chosen = prompt.buttons[kind].label;
  // Chromeの標準の入力保留時間を過ぎてから、表示中のボタンを操作する。
  await delay(config.prompt_settle_ms);
  if (prompt.snapshot.window) {
    const path = join(artifacts, `${target}-${kind}.png`);
    const { x, y, width, height } = prompt.snapshot.window;
    try {
      execFileSync("/usr/sbin/screencapture", ["-x", "-R", `${x},${y},${width},${height}`, path], { timeout: 6000 });
      entry.screenshot = `${target}-${kind}.png`;
    } catch (error) {
      entry.captureError = error.message;
    }
  }
  browserUI(pid, "press", origin, entry.chosen);
  entry.pressed = true;
}

async function appUi(page, target) {
  if (target === "upstream-play") {
    await page.getByRole("radio", { name: "Play", exact: true }).click();
    const button = page.locator(".midi-chip");
    return { click: () => button.click(), read: () => button.textContent() };
  }
  const panel = page.locator('section[aria-labelledby="midi-voice-title"]');
  const button = panel.getByRole("button", { name: /^MIDIを(接続|切断)$/ });
  return { click: () => button.click(), read: async () => ({
    button: await button.textContent(),
    status: await panel.locator("[data-midi-inputs]").textContent(),
    alert: await panel.getByRole("alert").allTextContents(),
    note: await panel.getByLabel("保持中のMIDI音").textContent(),
  }) };
}

async function observeResponse(page, ui, index) {
  await waitFor(async () => (await readProbe(page)).requests[index]?.outcome, `第${index + 1}回のMIDI応答がありません。`);
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  return { permission: await permission(page), ui: await ui.read(), probe: await readProbe(page) };
}

async function resetSitePermission(context, page, origin, report) {
  const settings = await context.newPage();
  settings.setDefaultTimeout(config.timeout_ms);
  try {
    await settings.goto("chrome://settings/content/siteDetails?site=" + encodeURIComponent(origin));
    const reset = settings.getByRole("button", { name: /^(Reset permissions|権限をリセット)$/ });
    await reset.click();
    const dialog = settings.getByRole("dialog", { name: /^(Reset permissions\?|権限をリセットしますか？)$/ });
    await dialog.waitFor();
    report.reset = { requestedOrigin: origin, dialog: await dialog.ariaSnapshot(), clicked: false };
    // Chromeの設定画面は確認ボタンをスロットへ挿入する。
    const confirm = settings.getByRole("button", { name: /^(Reset|リセット)$/ });
    await confirm.click();
    report.reset.clicked = true;
  } finally {
    await settings.close();
    await page.bringToFront();
  }
  await waitFor(async () => (await permission(page)) === "prompt", "ブラウザ設定で初回の権限状態に戻りません。");
}

async function observeTarget(pid, context, page, target, server) {
  const report = { dialogs: [], errors: [] };
  page.on("pageerror", (error) => report.errors.push(error.message));
  const origin = `http://${config.origin_binding}:${server.httpServer.address().port}`;
  try {
    await page.addInitScript(observeMidi);
    await page.goto(origin);
    await page.bringToFront();
    browserUI(pid, "activate");
    const ui = await appUi(page, target);
    report.before = { permission: await permission(page), ui: await ui.read() };
    await ui.click();
    await decide(pid, target, "deny", origin, report);
    report.denied = await observeResponse(page, ui, 0);
    await ui.click();
    report.repeatedDenial = await observeResponse(page, ui, 1);
    report.repeatedDenial.hasDialog = Boolean(permissionControls(browserUI(pid, "snapshot"), origin).deny);
    await resetSitePermission(context, page, origin, report);
    report.afterReset = { permission: await permission(page), ui: await ui.read() };
    browserUI(pid, "activate");
    await ui.click();
    await decide(pid, target, "allow", origin, report);
    report.granted = await observeResponse(page, ui, 2);
    await ui.click();
    report.disconnected = { ui: await ui.read(), probe: await readProbe(page) };
  } catch (error) {
    report.error = error.message;
    try { report.atFailure = { permission: await permission(page), probe: await readProbe(page) }; } catch {}
    try { report.browserAtFailure = browserUI(pid, "snapshot"); } catch {}
  }
  return report;
}

const child = spawn(chrome, [
  `--user-data-dir=${profile}`, "--remote-debugging-address=127.0.0.1", "--remote-debugging-port=0",
  "--no-first-run", "--no-default-browser-check", "--lang=en-US",
  `--window-size=${config.viewport_css_px.join(",")}`, "about:blank",
], { stdio: ["ignore", "ignore", "pipe"] });
let chromeLog = "";
child.stderr.setEncoding("utf8");
child.stderr.on("data", (chunk) => { chromeLog = (chromeLog + chunk).slice(-128 * 1024); });
let browser, nativeServer, upperServer;
try {
  const port = await waitFor(() => {
    if (child.exitCode !== null) throw new Error("独立したChromeの起動に失敗しました。");
    try {
      return readFileSync(join(profile, "DevToolsActivePort"), "utf8").split("\n")[0];
    } catch (error) {
      if (error.code !== "ENOENT") throw error;
      return null;
    }
  }, "独立したChromeの接続ポートが見つかりません。");
  browser = await chromium.connectOverCDP(`http://127.0.0.1:${port}`);
  const context = browser.contexts()[0];
  browserUI(child.pid, "activate");
  nativeServer = await preview({ root, logLevel: "silent", build: { outDir: dist }, preview: options });
  upperServer = await createServer({ root: upstream, logLevel: "silent", server: { ...options, hmr: false, watch: null } });
  await upperServer.listen();
  const reports = {};
  const servers = { "candidate-voice": nativeServer, "upstream-play": upperServer };
  for (const target of targets) {
    const page = await context.newPage();
    page.setDefaultTimeout(config.timeout_ms);
    try {
      reports[target] = await observeTarget(child.pid, context, page, target, servers[target]);
    } finally {
      await page.close();
    }
  }
  console.log(JSON.stringify({ chromium: browser.version(), mode: config.mode, reports }, null, 2));
} finally {
  await browser?.close().catch(() => {});
  if (child.exitCode === null && child.signalCode === null) {
    child.kill();
    await Promise.race([once(child, "exit"), delay(3000)]);
  }
  // Chromeの補助プロセスが終了後に書くログを計測ログから分離する。
  child.stderr.destroy();
  writeFileSync(join(artifacts, "chrome-stderr.log"), chromeLog);
  await nativeServer?.close();
  await upperServer?.close();
}
