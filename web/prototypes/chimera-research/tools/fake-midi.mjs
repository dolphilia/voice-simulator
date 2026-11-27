// 入力だけを置き換え、画面から下流の描画経路は実ブラウザで動かす。
export function installMidi(ports) {
  const inputs = new Map();
  const make = (id) => {
    const port = Object.assign(new EventTarget(), { id, name: id, state: "connected", onmidimessage: null });
    const listeners = new Set();
    port.addEventListener = (type, listener) => {
      if (type === "midimessage") listeners.add(listener);
      EventTarget.prototype.addEventListener.call(port, type, listener);
    };
    port.removeEventListener = (type, listener) => {
      if (type === "midimessage") listeners.delete(listener);
      EventTarget.prototype.removeEventListener.call(port, type, listener);
    };
    port.hasListener = () => listeners.size > 0 || !!port.onmidimessage;
    return port;
  };
  for (const id of ports) inputs.set(id, make(id));
  const access = Object.assign(new EventTarget(), { inputs, onstatechange: null });
  function stateChange() {
    const event = new Event("statechange");
    access.dispatchEvent(event);
    access.onstatechange?.(event);
  }
  const requests = [];
  Object.defineProperty(navigator, "requestMIDIAccess", {
    configurable: true,
    value: async (options) => {
      requests.push(options);
      return access;
    },
  });
  globalThis.chimeraTestMidi = {
    requests,
    apply({ port, bytes, change }) {
      const input = inputs.get(port);
      if (change === "unplug") {
        input.state = "disconnected";
        inputs.delete(port);
        stateChange();
      } else if (change === "replug") {
        inputs.set(port, make(port));
        stateChange();
      } else {
        if (!input?.hasListener()) throw new Error(`MIDI入力 ${port} が購読されていません`);
        const event = Object.assign(new Event("midimessage"), { data: Uint8Array.from(bytes) });
        input.dispatchEvent(event);
        input.onmidimessage?.(event);
      }
    },
    listenerCount: () => [...inputs.values()].filter((input) => input.hasListener()).length,
  };
}
