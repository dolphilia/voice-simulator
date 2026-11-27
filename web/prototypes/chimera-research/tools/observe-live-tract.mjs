// 実ページでWorkletの到着順と描画済みのフレームを記録する。
export function observeLiveTract({ stallFrame, stallMilliseconds, geometry }) {
  const packets = [];
  const draws = [];
  const runs = [];
  const vertices = [];
  const gpu = new WeakMap();
  let stall = null;
  let sequence = 0;
  const counters = (canvas) => {
    if (!gpu.has(canvas)) gpu.set(canvas, { canvasId: ++sequence, buffers: 0, updates: 0, draws: 0 });
    return gpu.get(canvas);
  };
  for (const [method, field] of [["createBuffer", "buffers"], ["bufferSubData", "updates"], ["drawArrays", "draws"]]) {
    const original = WebGL2RenderingContext.prototype[method];
    WebGL2RenderingContext.prototype[method] = function (...args) {
      counters(this.canvas)[field]++;
      return original.apply(this, args);
    };
  }
  globalThis.AudioWorkletNode = new Proxy(AudioWorkletNode, {
    construct(target, [context, ...args]) {
      const node = Reflect.construct(target, [context, ...args]);
      const run = runs.length;
      if (!args[1]?.processorOptions?.realtime?.publishTract) return node;
      const result = { completedAtMs: null, contextClosedAtMs: null };
      runs.push(result);
      context.addEventListener("statechange", () => {
        if (context.state === "closed") result.contextClosedAtMs = performance.now();
      });
      node.port.addEventListener("message", ({ data }) => {
        if (data.type === "complete") {
          result.completedAtMs = performance.now();
          return;
        }
        if (data.type !== "tract-frame") return;
        const receivedMs = performance.now();
        packets.push({ run, frame: data.frame, contextFrame: data.contextFrame,
          receiptContextFrame: Math.round(context.currentTime * context.sampleRate),
          receivedMs, counts: data.counts, values: Array.from(data.values) });
        if (stallFrame === data.frame && !stall) {
          const beganMs = performance.now();
          // 同じ音声処理を続けたままページだけを止め、返送が滞る条件を作る。
          while (performance.now() - beganMs < stallMilliseconds) { /* ページの停止を再現 */ }
          stall = { frame: data.frame, beganMs, endedMs: performance.now(),
            endedContextFrame: Math.round(context.currentTime * context.sampleRate) };
        }
      });
      return node;
    },
  });
  new MutationObserver(() => {
    const label = document.querySelector("[data-live-context-frame]");
    if (!label) return;
    const run = runs.length - 1;
    const frame = Number(label.dataset.speechGridFrame);
    if (draws.at(-1)?.run === run && draws.at(-1)?.frame === frame) return;
    const canvas = label.closest("section")?.querySelector("canvas");
    if (canvas && gpu.has(canvas)) {
      draws.push({ run, frame, contextFrame: Number(label.dataset.liveContextFrame), lipArea: Number(label.dataset.liveLipArea),
        atMs: performance.now(), ...gpu.get(canvas) });
      if (!geometry) return;
      const packet = packets.findLast((entry) => entry.run === run && entry.frame === frame);
      if (!packet) return;
      const offset = 5 * (packet.counts[0] + packet.counts[1]);
      const rows = packet.values[offset];
      const last = offset + 1 + (rows - 1) * 11;
      const open = packet.values[last + 9] >= geometry.minimum_open_area_cm2
        && draws.at(-1).lipArea >= geometry.minimum_open_area_cm2;
      const closed = packet.values[last + 8] <= geometry.maximum_closed_gap_cm
        && draws.at(-1).lipArea <= geometry.maximum_closed_acoustic_area_cm2;
      const seen = new Set(vertices.filter((entry) => entry.run === run).map((entry) => entry.phase));
      const phases = [];
      if (!seen.has("first")) phases.push("first");
      if (!seen.has("closed") && closed) phases.push("closed");
      if (open && !seen.has("closed") && !seen.has("before") && frame >= geometry.before_frame) phases.push("before");
      if (open && seen.has("closed") && !seen.has("after")) phases.push("after");
      for (const phase of phases) {
        canvas.dispatchEvent(new CustomEvent("chimera:read-live-tract", { detail: (drawing) => {
          vertices.push({ run, phase, ...drawing, contextFrame: packet.contextFrame });
        } }));
      }
    }
  }).observe(document, { childList: true, subtree: true, attributes: true,
    attributeFilter: ["data-live-context-frame"] });
  window.liveTractEvidence = { packets, draws, runs, ...(geometry && { vertices }), get stall() { return stall; } };
}
