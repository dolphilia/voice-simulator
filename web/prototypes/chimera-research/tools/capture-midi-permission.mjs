// 試験コンテキストでChromiumのWeb MIDI権限と画面状態を観測する。
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";
import { createServer, preview } from "vite";

const [casePath, candidateDist, upstream] = process.argv.slice(2);
const { panels, browser: config } = JSON.parse(readFileSync(casePath, "utf8"));
const root = fileURLToPath(new URL("../", import.meta.url));
const options = { host: "127.0.0.1", port: 0 };
const panelsById = {
  voice: ["#midi-voice-title", "MIDI", "MIDI入力なし"],
  beat: ["#beat-title", "ビートのMIDI", "ビートのMIDI入力 機器待ち"],
  songbird: ["#songbird-midi-title", "鳴禽のMIDI", "MIDI機器待ち"],
  seal: ["#seal-midi-title", "ウェッデルアザラシのMIDI", "MIDI機器待ち"],
  alligator: ["#alligator-midi-title", "アメリカアリゲーターのMIDI", "MIDI機器待ち"],
  elephant: ["#elephant-midi-title", "アフリカゾウのMIDI", "MIDI機器待ち"],
};

function observeNativeMidi() {
  const original = navigator.requestMIDIAccess.bind(navigator);
  const requests = [];
  const accesses = [];
  let hold = false;
  Object.defineProperty(navigator, "requestMIDIAccess", {
    configurable: true,
    value: (options) => {
      const entry = { options, outcome: null, inputs: null, sysexEnabled: null, delivered: false };
      requests.push(entry);
      const deliver = hold ? new Promise((resolve) => { entry.release = resolve; }) : Promise.resolve();
      return original(options).then(async (access) => {
        const observers = new Set();
        const add = access.addEventListener.bind(access);
        const remove = access.removeEventListener.bind(access);
        access.addEventListener = (type, listener, ...args) => {
          if (type === "statechange") observers.add(listener);
          add(type, listener, ...args);
        };
        access.removeEventListener = (type, listener, ...args) => {
          if (type === "statechange") observers.delete(listener);
          remove(type, listener, ...args);
        };
        accesses.push({ access, observers });
        entry.outcome = "granted";
        entry.inputs = access.inputs.size;
        entry.sysexEnabled = access.sysexEnabled;
        await deliver;
        entry.delivered = true;
        return access;
      }, async (error) => {
        entry.outcome = error.name;
        await deliver;
        entry.delivered = true;
        throw error;
      });
    },
  });
  globalThis.midiPermissionProbe = {
    requests,
    hold: () => { hold = true; },
    release: (index) => requests[index].release(),
    report: () => ({
      requests: requests.map(({ options, outcome, inputs, sysexEnabled, delivered }) => ({
        options, outcome, inputs, sysexEnabled, delivered,
      })),
      subscriptions: accesses.map(({ access, observers }) => observers.size + Number(Boolean(access.onstatechange))),
    }),
  };
}

const readProbe = (page) => page.evaluate(() => globalThis.midiPermissionProbe.report());
const hold = (page) => page.evaluate(() => globalThis.midiPermissionProbe.hold());
async function release(page, index) {
  await page.evaluate(async (i) => {
    globalThis.midiPermissionProbe.release(i);
    await new Promise(requestAnimationFrame);
    await new Promise(requestAnimationFrame);
  }, index);
}
async function waitRequest(page, index) {
  await page.waitForFunction((i) => globalThis.midiPermissionProbe.requests[i]?.outcome, index,
    { timeout: config.timeout_ms });
}

function candidateUi(page, id) {
  const [heading, label, empty] = panelsById[id];
  const panel = page.locator('section[aria-labelledby="' + heading.slice(1) + '"]');
  const connect = panel.getByRole("button", { name: label + "を接続", exact: true });
  const disconnect = panel.getByRole("button", { name: label + "を切断", exact: true });
  const alert = panel.getByRole("alert");
  return {
    connect, disconnect, alert,
    ready: () => panel.getByText(empty, { exact: true }).waitFor(),
    snapshot: async () => ({
      canConnect: await connect.count() === 1 && await connect.isEnabled(),
      canDisconnect: await disconnect.count() === 1 && await disconnect.isEnabled(),
      waiting: await panel.getByText("MIDI接続を待っています", { exact: true }).count() === 1,
      noInputs: await panel.getByText(empty, { exact: true }).count() === 1,
      error: await alert.count() > 0,
      note: id === "voice" ? await panel.getByLabel("保持中のMIDI音").textContent() : null,
    }),
  };
}

async function withPage(browser, browserSession, server, callback) {
  const context = await browser.newContext();
  try {
    const page = await context.newPage();
    page.setDefaultTimeout(config.timeout_ms);
    const pageSession = await context.newCDPSession(page);
    const { targetInfo: { browserContextId } } = await pageSession.send("Target.getTargetInfo");
    await pageSession.detach();
    if (!browserContextId) throw new Error("Chromiumの試験コンテキストを識別できません");
    const origin = "http://127.0.0.1:" + server.httpServer.address().port;
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.addInitScript(observeNativeMidi);
    await page.goto(origin);
    const permission = async (setting) => {
      for (const sysex of [false, true]) {
        await browserSession.send("Browser.setPermission", {
          permission: { ...config.permission, sysex }, setting, origin, browserContextId,
        });
      }
      return page.evaluate(async (descriptor) => (await navigator.permissions.query(descriptor)).state, config.permission);
    };
    try {
      return { ...await callback(page, permission), errors };
    } catch (error) {
      console.error("Web MIDIの取得状態", JSON.stringify(await readProbe(page)));
      throw error;
    }
  } finally {
    await context.close();
  }
}

async function observeCandidate(page, permission, id) {
  const ui = candidateUi(page, id);
  const permissions = [await permission("denied")];
  await ui.connect.click();
  await ui.alert.waitFor();
  const denied = await ui.snapshot();
  permissions.push(await permission("granted"));
  await ui.connect.click();
  await ui.ready();
  const granted = await ui.snapshot();
  await ui.disconnect.click();
  const disconnected = await readProbe(page);
  await hold(page);
  await ui.connect.click();
  await waitRequest(page, 2);
  const waiting = await ui.snapshot();
  if (!waiting.canDisconnect) {
    await release(page, 2);
    await ui.ready();
    await ui.disconnect.click();
    return { permissions, denied, granted, disconnected, waiting, probe: await readProbe(page) };
  }
  await ui.disconnect.click();
  await release(page, 2);
  const canceled = await ui.snapshot();
  const afterCancel = await readProbe(page);
  permissions.push(await permission("denied"));
  await ui.connect.click();
  await waitRequest(page, 3);
  await ui.disconnect.click();
  permissions.push(await permission("granted"));
  await ui.connect.click();
  await waitRequest(page, 4);
  await release(page, 3);
  const oldRejection = await ui.snapshot();
  await release(page, 4);
  await ui.ready();
  const retried = await ui.snapshot();
  const afterRetry = await readProbe(page);
  await ui.disconnect.click();
  return { permissions, denied, granted, disconnected, waiting, canceled, afterCancel,
    oldRejection, retried, afterRetry, probe: await readProbe(page) };
}

async function observeUpper(page, permission) {
  await page.getByRole("radio", { name: "Play", exact: true }).click();
  const button = page.locator(".midi-chip");
  const value = () => button.textContent();
  const wait = (status) => page.getByRole("button", { name: status, exact: true }).waitFor();
  const stop = () => page.evaluate(async () => (await import("/src/ui/store.ts")).useStore.getState().setMidi(false));
  const permissions = [await permission("denied")];
  await button.click();
  await wait("MIDI: Blocked by the browser");
  const denied = await value();
  permissions.push(await permission("granted"));
  await button.click();
  await wait("MIDI: Plug one in");
  const granted = await value();
  await button.click();
  await wait("MIDI");
  const disconnected = await readProbe(page);
  await hold(page);
  await button.click();
  await waitRequest(page, 2);
  await button.click();
  const secondClick = { button: await value(), requests: (await readProbe(page)).requests.length };
  await stop();
  await release(page, 2);
  const canceled = await value();
  const afterCancel = await readProbe(page);

  permissions.push(await permission("denied"));
  await button.click();
  await waitRequest(page, 3);
  await stop();
  permissions.push(await permission("granted"));
  await button.click();
  await waitRequest(page, 4);
  await release(page, 3);
  const oldRejection = await value();
  await release(page, 4);
  await wait("MIDI: Plug one in");
  const retried = await value();
  await button.click();
  return { permissions, denied, granted, disconnected, secondClick, canceled, afterCancel, oldRejection,
    retried, probe: await readProbe(page) };
}

const browser = await chromium.launch({ headless: true, executablePath: process.env.CHIMERA_CHROMIUM ??
  (process.platform === "darwin" ? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" : undefined) });
let candidateServer;
let upstreamServer;
try {
  const session = await browser.newBrowserCDPSession();
  candidateServer = await preview({ root, logLevel: "silent", build: { outDir: candidateDist }, preview: options });
  upstreamServer = await createServer({ root: upstream, logLevel: "silent", server: { ...options, hmr: false, watch: null } });
  await upstreamServer.listen();
  const candidate = {};
  for (const panel of panels) {
    candidate[panel] = await withPage(browser, session, candidateServer,
      (page, permission) => observeCandidate(page, permission, panel));
  }
  const upper = await withPage(browser, session, upstreamServer, observeUpper);
  console.log(JSON.stringify({ chromium: browser.version(), candidate, upper }, null, 2));
} finally {
  await browser.close();
  await candidateServer?.close();
  await upstreamServer?.close();
}
