import type { LiveSongKey } from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/fixed-voice";

export function midiFrequency(note: number): number {
  return 440 * 2 ** ((note - 69) / 12);
}

// 音ごとの所有数と、最初に押された順を保持する。
export function listenMidi(access: MIDIAccess, onNote: (note: number | null) => void,
  onInputs: (names: string[]) => void, onKey?: (key: LiveSongKey) => void): () => void {
  const inputs = new Map<MIDIInput, {
    channels: Map<number, Set<number>>;
    receiveMessage: (event: MIDIMessageEvent) => void;
  }>();
  const owners = new Map<number, number>();
  let sounding: number | null = null;

  function publish() {
    const latest = [...owners.keys()].at(-1) ?? null;
    if (sounding === latest) return;
    sounding = latest;
    onNote(latest);
  }

  function release(note: number) {
    const count = owners.get(note) ?? 0;
    if (count <= 1) {
      if (owners.delete(note)) onKey?.({ type: "note-off", note });
    } else owners.set(note, count - 1);
  }

  function receive(channels: Map<number, Set<number>>, data: Uint8Array) {
    if (data.length !== 3 || data[1] > 127 || data[2] > 127) return;
    const kind = data[0] & 0xf0;
    const channel = data[0] & 15;
    const note = data[1];
    let held = channels.get(channel);
    if (kind === 0x90 && data[2] > 0) {
      if (!held) {
        held = new Set();
        channels.set(channel, held);
      }
      if (!held.has(note)) {
        held.add(note);
        const previous = owners.get(note) ?? 0;
        owners.set(note, previous + 1);
        if (previous === 0) onKey?.({ type: "note-on", note, velocity: data[2] });
      }
    } else if (held && (kind === 0x80 || kind === 0x90)) {
      if (held.delete(note)) release(note);
    } else if (held && kind === 0xb0 && (note === 120 || note === 123)) {
      for (const key of held) release(key);
      held.clear();
    }
    publish();
  }

  function refresh() {
    const live = new Set<MIDIInput>();
    access.inputs.forEach((input) => {
      if (input.state === "disconnected") return;
      live.add(input);
      if (inputs.has(input)) return;
      const channels = new Map<number, Set<number>>();
      const receiveMessage = ({ data }: MIDIMessageEvent) => {
        if (data) receive(channels, data);
      };
      inputs.set(input, { channels, receiveMessage });
      input.addEventListener("midimessage", receiveMessage);
    });
    for (const [input, { channels, receiveMessage }] of inputs) {
      if (live.has(input)) continue;
      input.removeEventListener("midimessage", receiveMessage);
      inputs.delete(input);
      for (const held of channels.values()) for (const note of held) release(note);
    }
    publish();
    onInputs([...live].map((input) => input.name || "MIDI入力"));
  }

  access.addEventListener("statechange", refresh);
  refresh();
  return () => {
    access.removeEventListener("statechange", refresh);
    for (const [input, { receiveMessage }] of inputs) {
      input.removeEventListener("midimessage", receiveMessage);
    }
    inputs.clear();
    for (const note of owners.keys()) onKey?.({ type: "note-off", note });
    owners.clear();
  };
}
