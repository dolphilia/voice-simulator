import { spawn } from "node:child_process";
import { createServer } from "node:net";
import { setTimeout as delay } from "node:timers/promises";

export async function withSafari(capture) {
  const reservation = createServer().listen(0, "127.0.0.1");
  await new Promise((resolve, reject) => reservation.once("listening", resolve).once("error", reject));
  const { port } = reservation.address();
  await new Promise((resolve, reject) => reservation.close((error) => error ? reject(error) : resolve()));
  const driver = spawn("/usr/bin/safaridriver", ["-p", String(port)], { stdio: "inherit" });
  let session;
  const command = async (path, body, method = body === undefined ? "GET" : "POST") => {
    const response = await fetch(`http://127.0.0.1:${port}${path}`, { method, signal: AbortSignal.timeout(20_000),
      ...(body !== undefined && { body: JSON.stringify(body), headers: { "Content-Type": "application/json" } }) });
    const { value } = await response.json();
    if (!response.ok) throw new Error(`Safari WebDriver ${path}: ${value?.message ?? response.status}`);
    return value;
  };
  try {
    for (let attempt = 0;; attempt++) {
      try {
        await command("/status");
        break;
      } catch (error) {
        if (attempt >= 39 || driver.exitCode !== null) throw error;
        await delay(100);
      }
    }
    const { sessionId, capabilities } = await command("/session", { capabilities: { alwaysMatch: { browserName: "safari" } } });
    session = `/session/${sessionId}`;
    return await capture((suffix, body) => command(session + suffix, body), capabilities);
  } finally {
    try {
      if (session) await command(session, undefined, "DELETE");
    } finally {
      driver.kill();
    }
  }
}
