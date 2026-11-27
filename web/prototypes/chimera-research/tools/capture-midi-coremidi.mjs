// CoreMIDIから実際に届くMIDIメッセージと、通常画面・Workletの出力を採る。
import { execFileSync, spawn } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { createInterface } from "node:readline";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";
import { createServer, preview } from "vite";

const [casePath, dist, upstream, out, helper, variantPath, passiveInput] = process.argv.slice(2);
const { browser: config, input, measurement } = JSON.parse(readFileSync(casePath, "utf8"));
const variant = variantPath ? JSON.parse(readFileSync(variantPath, "utf8")) : {};
const releaseAction = variant.release_action ?? "note-off";
const shared = variant.shared_note;
const unplug = releaseAction !== "note-off";
const passive = variant.passive_capture;
const sameNameFixture = passiveInput === "fixture-with-same-name-input";
const idleFixture = passiveInput === "fixture-with-idle-input" || sameNameFixture;
const fixture = passiveInput === "fixture" || idleFixture;
const host = "127.0.0.1";
const root = fileURLToPath(new URL("../", import.meta.url));
const options = { host, port: 0 };

function observeMidi({ names, watchUnplug, allInputs }) {
  const requests = [];
  const topology = [];
  const messages = [];
  const subscriptions = new Map();
  const onMessage = new WeakMap();
  const realRequest = navigator.requestMIDIAccess.bind(navigator);
  let access;
  let removedPort = null;
  const realAdd = MIDIInput.prototype.addEventListener;
  const realRemove = MIDIInput.prototype.removeEventListener;
  const property = Object.getOwnPropertyDescriptor(MIDIInput.prototype, "onmidimessage");
  const portFields = ({ name, id, type, state, connection }) => ({ name, id, type, state, connection });
  function observe(listener) {
    return function (event) {
      messages.push({ port: portFields(this), bytes: Array.from(event.data), trusted: event.isTrusted,
        eventMs: event.timeStamp, handlerMs: performance.now() });
      return listener.call(this, event);
    };
  }
  MIDIInput.prototype.addEventListener = function (type, listener, ...args) {
    if ((!allInputs && !names.includes(this.name)) || type !== "midimessage") return realAdd.call(this, type, listener, ...args);
    const wrapped = observe(listener);
    subscriptions.set(listener, { port: this, wrapped });
    return realAdd.call(this, type, wrapped, ...args);
  };
  MIDIInput.prototype.removeEventListener = function (type, listener, ...args) {
    const registration = type === "midimessage" ? subscriptions.get(listener) : undefined;
    if (registration?.port !== this) return realRemove.call(this, type, listener, ...args);
    subscriptions.delete(listener);
    return realRemove.call(this, type, registration.wrapped, ...args);
  };
  Object.defineProperty(MIDIInput.prototype, "onmidimessage", {
    ...property,
    get() { return onMessage.get(this) ?? property.get.call(this); },
    set(listener) {
      if (!allInputs && !names.includes(this.name)) return property.set.call(this, listener);
      if (listener) onMessage.set(this, listener);
      else onMessage.delete(this);
      return property.set.call(this, listener ? observe(listener) : listener);
    },
  });
  const inputPorts = () => [...(access?.inputs.values() ?? [])];
  const ports = () => inputPorts().filter((port) => names.includes(port.name));
  Object.defineProperty(navigator, "requestMIDIAccess", {
    configurable: true,
    value: async (options) => {
      const entry = { options };
      requests.push(entry);
      try {
        access = await realRequest(options);
        Object.assign(entry, { outcome: "granted", sysexEnabled: access.sysexEnabled, initialProbeInputs: ports().length });
        access.addEventListener("statechange", (event) => {
          const port = event.port;
          if (!port || !names.includes(port.name)) return;
          if (watchUnplug && port.state === "disconnected") removedPort = port;
          topology.push({ ...portFields(port), trusted: event.isTrusted, eventMs: event.timeStamp,
            handlerMs: performance.now(), inInputMap: access.inputs.has(port.id) });
        });
        return access;
      } catch (error) {
        entry.outcome = error.name;
        throw error;
      }
    },
  });
  globalThis.coreMidiProbe = () => ({ requests, topology, messages, ports: ports().map(portFields),
    ...(allInputs ? {
      inputPorts: inputPorts().map(portFields),
      subscribedPortIds: [...subscriptions.values()].map(({ port }) => port.id),
    } : {}),
    subscriptions: subscriptions.size + (allInputs ? inputPorts() : ports()).filter((port) => onMessage.has(port)).length,
    removedInput: removedPort && { ...portFields(removedPort), propertyHandlerSet: Boolean(property.get.call(removedPort)) } });
}

function startHelper(args, log) {
  const child = spawn(helper, args, { stdio: ["pipe", "pipe", "pipe"] });
  let errorText = "";
  child.stderr.setEncoding("utf8").on("data", (chunk) => { errorText += chunk; });
  child.stdin.on("error", (error) => { errorText += String(error); });
  child.on("error", (error) => { errorText += String(error); });
  const closed = new Promise((resolve) => child.once("close", resolve));
  const lines = createInterface({ input: child.stdout })[Symbol.asyncIterator]();
  async function next(action) {
    const timeout = new AbortController();
    try {
      const { value, done } = await Promise.race([lines.next(),
        delay(config.timeout_ms, { done: true }, { signal: timeout.signal })]);
      if (done) throw new Error(`CoreMIDIの応答がありません (${action}) ${errorText}`);
      const response = JSON.parse(value);
      log.push(response);
      if (response.action !== action) throw new Error(`CoreMIDIの応答が想定外です (${action})`);
      return response;
    } finally {
      timeout.abort();
    }
  }
  return {
    next,
    send: async (bytes) => {
      child.stdin.write(`${bytes.join(" ")}\n`);
      await next("send");
    },
    remove: async () => {
      child.stdin.end("remove\n");
      await next("remove");
    },
    close: async () => {
      child.stdin.end();
      const timer = setTimeout(() => child.kill(), config.timeout_ms);
      try { return { code: await closed, stderr: errorText }; }
      finally { clearTimeout(timer); }
    },
  };
}

async function candidateEntry(page) {
  const panel = page.getByRole("region", { name: "MIDI鍵盤の発声", exact: true });
  const held = panel.getByLabel("保持中のMIDI音");
  return {
    connect: () => panel.getByRole("button", { name: "MIDIを接続", exact: true }).click(),
    waitSources: (names) => panel.getByText(names.join("、"), { exact: true }).waitFor(),
    waitNoSource: () => panel.getByText("MIDI入力なし", { exact: true }).waitFor(),
    begin: async () => {
      await panel.getByRole("button", { name: "MIDI計測を開始", exact: true }).click();
      await panel.getByText("MIDI計測中", { exact: true }).waitFor();
    },
    snapshot: () => held.evaluate((element) => ({ note: element.textContent, observedMs: performance.now() })),
    waitNote: (note) => panel.getByText(note === null ? "なし" : String(note), { exact: true }).and(held).waitFor(),
    finish: async () => {
      await panel.getByRole("button", { name: "MIDI計測を停止", exact: true }).click();
      await panel.getByText("実時間計測完了", { exact: true }).waitFor();
      for (const [label, file] of [["WAVを保存", "candidate.wav"],
        ["観測JSONを保存", "candidate.json"], ["再実行ケースを保存", "candidate-case.json"]]) {
        const [download] = await Promise.all([page.waitForEvent("download"), panel.getByRole("link", { name: label, exact: true }).click()]);
        await download.saveAs(join(out, file));
      }
    },
    disconnect: () => panel.getByRole("button", { name: "MIDIを切断", exact: true }).click(),
  };
}

async function upstreamEntry(page) {
  await page.getByRole("radio", { name: "Play", exact: true }).click();
  await page.evaluate(async () => {
    const [{ engine }, { useStore }] = await Promise.all([import("/src/audio/AudioEngine.ts"), import("/src/ui/store.ts")]);
    const trace = [];
    const gateMessages = [];
    const gate = engine.gate.bind(engine);
    engine.gate = (level) => {
      gateMessages.push({ level, clock: engine.voiceClock(), observedMs: performance.now() });
      gate(level);
    };
    engine.onTelemetry(({ t }) => trace.push({ clock: t.clock, gate: t.gate, f0: t.f0, rms: t.outRms }));
    globalThis.upperCoreMidiSnapshot = () => {
      const state = useStore.getState();
      return { mode: state.mode, started: state.started, sampleRate: engine.sampleRate,
        note: state.heldNotes.at(-1) ?? null, targetHz: state.source.f0,
        gateTarget: gateMessages.at(-1)?.level ?? null, clock: engine.voiceClock(), observedMs: performance.now() };
    };
    globalThis.upperCoreMidiTrace = () => ({ trace, gateMessages });
  });
  const snapshot = () => page.evaluate(() => globalThis.upperCoreMidiSnapshot());
  const key = page.getByRole("button", { name: `Note ${input.note_on[1]}`, exact: true });
  const pressed = key.and(page.locator(".down"));
  const midiButton = (name) => page.getByRole("button", { name: `MIDI: ${name}`, exact: true });
  return {
    connect: () => page.getByRole("button", { name: "MIDI", exact: true }).click(),
    waitSources: (names) => midiButton(names.join(", ")).waitFor(),
    waitNoSource: () => midiButton("Plug one in").waitFor(),
    begin: () => page.waitForFunction(() => globalThis.upperCoreMidiSnapshot().started && globalThis.upperCoreMidiTrace().trace.length > 0),
    snapshot,
    waitNote: (note) => pressed.waitFor({ state: note === null ? "hidden" : "visible" }),
    finish: () => page.evaluate(() => globalThis.upperCoreMidiTrace()),
    disconnect: (name) => midiButton(name ?? "Plug one in").click(),
  };
}

function inputInventory() {
  return execFileSync(helper, ["--list-inputs"], { encoding: "utf8" }).trim().split("\n").filter(Boolean)
    .map((line) => JSON.parse(line));
}

async function notifyOperator(page, message) {
  await page.evaluate((text) => {
    let prompt = document.getElementById("coremidi-capture-prompt");
    if (!prompt) {
      prompt = document.createElement("p");
      prompt.id = "coremidi-capture-prompt";
      prompt.setAttribute("role", "status");
      Object.assign(prompt.style, { position: "fixed", inset: "auto 1rem 1rem auto", zIndex: "10",
        padding: "1rem", margin: "0", background: "#15232c", color: "#fff" });
      document.body.append(prompt);
    }
    prompt.textContent = text;
  }, message);
}

async function capture(browser, session, server, setup, target, row, attached) {
  const context = await browser.newContext({ acceptDownloads: true });
  const name = `${input.source_prefix} ${process.pid} ${target}`;
  const inputNames = attached ? [attached.name, attached.displayName] : [name];
  if (fixture) inputNames.push(`${name} (表示名)`);
  const names = shared ? [`${name} A`, `${name} B`] : [...new Set(inputNames.filter(Boolean))];
  if (passive) row.inputNameAliases = names;
  const read = (page) => page.evaluate(() => globalThis.coreMidiProbe());
  let source;
  let secondSource;
  let idleSource;
  let observer;
  let receiver;
  let page;
  try {
    page = await context.newPage();
    page.setDefaultTimeout(sameNameFixture ? config.timeout_ms : variant.operator_timeout_ms ?? config.timeout_ms);
    page.on("pageerror", (error) => row.pageErrors.push(error.message));
    const origin = `http://${host}:${server.httpServer.address().port}`;
    const pageSession = await context.newCDPSession(page);
    const { targetInfo: { browserContextId } } = await pageSession.send("Target.getTargetInfo");
    await pageSession.detach();
    if (!browserContextId) throw new Error("Chromiumの試験コンテキストを識別できません");
    for (const sysex of config.test_permission_sysex_variants) {
      await session.send("Browser.setPermission", {
        permission: { ...config.permission, sysex }, setting: "granted", origin, browserContextId,
      });
    }
    await page.addInitScript(observeMidi, { names, watchUnplug: unplug, allInputs: Boolean(passive) });
    await page.goto(origin);
    row.permission = await page.evaluate(async (permission) => (await navigator.permissions.query(permission)).state, config.permission);
    const app = await setup(page);
    await app.connect();
    await page.waitForFunction(() => globalThis.coreMidiProbe().requests[0]?.outcome);
    row.before = await read(page);
    if (row.before.requests[0]?.outcome !== "granted") throw new Error("試験コンテキストのWeb MIDIアクセスが許可されませんでした");
    if (!attached) source = startHelper([names[0], String(input.group)], row.native);
    const endpoint = attached?.endpoint ?? (await source.next("add")).endpoint;
    if (passive) {
      row.selectedInput = attached ?? inputInventory().find((entry) => entry.endpoint === endpoint);
      if (!row.selectedInput) throw new Error("入力の登録情報を取得できません");
      row.received = [];
      receiver = startHelper(["--listen-notes", String(endpoint)], row.received);
      await receiver.next("listening");
    }
    if (variant.native_notification?.method === "separate-coremidi-client-run-loop") {
      row.nativeNotifications = [];
      observer = startHelper(["--watch-removal", String(endpoint)], row.nativeNotifications);
      await observer.next("watching");
    }
    if (!attached) await app.waitSources(names.slice(0, 1));
    if (idleFixture) {
      row.idleFixture = { native: [] };
      const idleName = sameNameFixture ? name : `${name} (無操作)`;
      idleSource = startHelper([idleName, String(input.group)], row.idleFixture.native);
      const idleEndpoint = (await idleSource.next("add")).endpoint;
      row.idleFixture.uid = inputInventory().find((entry) => entry.endpoint === idleEndpoint)?.uid;
      await page.waitForFunction(({ name, count }) => globalThis.coreMidiProbe().inputPorts
        .filter((port) => port.name === name && port.connection === "open").length === count,
      { name: idleName, count: sameNameFixture ? 2 : 1 });
    }
    if (shared) {
      row.shared = { native: [] };
      secondSource = startHelper([names[1], String(input.group)], row.shared.native);
      await secondSource.next("add");
      await app.waitSources(names);
    }
    // 受動収録では同名候補を保ち、受信したノートで端子を照合する。
    await page.waitForFunction(({ passive, expected }) => {
      const { ports } = globalThis.coreMidiProbe();
      return (passive ? ports.length > 0 : ports.length === expected)
        && ports.every((port) => port.connection === "open");
    }, { passive: Boolean(passive), expected: shared ? 2 : 1 });
    row.connected = await read(page);
    await app.begin();
    await delay(measurement.silent_before_ms);
    row.silent = await app.snapshot();
    if (source) await source.send(input.note_on);
    else await notifyOperator(page, "A3（MIDI 57、チャンネル1）を1回押したままにしてください。");
    await app.waitNote(input.note_on[1]);
    if (receiver) await receiver.next("note");
    row.on = await app.snapshot();
    if (shared) {
      await secondSource.send(shared.second_note_on);
      await page.waitForFunction((sourceName) => globalThis.coreMidiProbe().messages.some((message) => message.port.name === sourceName), names[1]);
      row.shared.twoPressed = await app.snapshot();
    }
    await delay(measurement.hold_after_observed_on_ms);
    row.held = await app.snapshot();
    if (unplug) {
      await source.remove();
      if (shared) {
        await app.waitSources(names.slice(1));
        row.shared.afterFirstRemoval = await app.snapshot();
        row.shared.firstRemoval = await read(page);
        await delay(shared.hold_after_first_removal_ms);
        row.shared.beforeLastRemoval = await app.snapshot();
        await secondSource.remove();
      }
      await page.waitForFunction(() => {
        const probe = globalThis.coreMidiProbe();
        return probe.removedInput && probe.ports.length === 0;
      });
      await app.waitNoSource();
    } else if (source) {
      await source.send(passive ? [input.note_on[0], input.note_on[1], 0] : input.note_off);
    } else await notifyOperator(page, "押しているA3を離してください。");
    await app.waitNote(null);
    if (receiver) await receiver.next("note");
    row.off = await app.snapshot();
    if (unplug) row.removed = await read(page);
    await delay(measurement.release_after_observed_off_ms);
    row.released = await app.snapshot();
    row.output = await app.finish();
    await app.disconnect(unplug ? undefined : name);
    row.disconnected = await read(page);
    if (receiver) {
      row.receiver = await receiver.close();
      receiver = undefined;
    }
    if (source && !unplug) await source.remove();
    if (idleSource) await idleSource.remove();
    if (observer) await observer.next("notified");
  } catch (error) {
    row.error = String(error);
    if (page) row.atError = await read(page).catch(() => null);
  } finally {
    if (receiver) row.receiver = await receiver.close();
    if (source) row.helper = await source.close();
    if (secondSource) row.shared.helper = await secondSource.close();
    if (idleSource) row.idleFixture.helper = await idleSource.close();
    if (observer) row.observer = await observer.close();
    await context.close();
  }
}

const report = { mode: config.mode, releaseAction, targets: {} };
let candidate;
let upper;
let browser;
try {
  const executablePath = process.env.CHIMERA_CHROMIUM ?? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
  let attached;
  if (passive) {
    report.inputKind = fixture ? "virtual_fixture" : "attached_device";
    report.inventory = inputInventory();
    if (!fixture) {
      attached = report.inventory.find((entry) => String(entry.uid) === passiveInput && entry.device !== 0
        && (entry.name || entry.displayName));
      if (!attached) report.missingInput = passiveInput;
    }
  }
  if (!passive || fixture || attached) {
    browser = await chromium.launch({ headless: !passive || fixture, executablePath });
    report.chromium = browser.version();
    const session = await browser.newBrowserCDPSession();
    candidate = await preview({ root, build: { outDir: dist }, preview: options });
    const targets = [["candidate", candidate, candidateEntry]];
    if (!passive) {
      upper = await createServer({ root: upstream, server: { ...options, hmr: false, watch: null } });
      await upper.listen();
      targets.push(["upstream", upper, upstreamEntry]);
    }
    for (const [target, server, entry] of targets) {
      const row = report.targets[target] = { native: [], pageErrors: [] };
      await capture(browser, session, server, entry, target, row, attached);
    }
  }
} finally {
  await browser?.close();
  await upper?.close();
  await candidate?.close();
  writeFileSync(join(out, "coremidi-browser.json"), JSON.stringify(report, null, 2) + "\n");
}
