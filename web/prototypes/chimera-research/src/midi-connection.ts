import { useCallback, useEffect, useRef, useState } from "react";
import { listenMidi } from "./midi-input";

type OnNote = Parameters<typeof listenMidi>[1];
type OnKey = Parameters<typeof listenMidi>[3];

export function useMidiConnection(onNote: OnNote, onError: (message: string) => void, onKey?: OnKey) {
  const active = useRef<{ detach?: () => void }>(undefined);
  const [inputs, setInputs] = useState<string[]>();
  const [connecting, setConnecting] = useState(false);

  const dispose = useCallback(() => {
    const previous = active.current;
    active.current = undefined;
    previous?.detach?.();
  }, []);
  useEffect(() => dispose, [dispose]);

  async function toggle() {
    onError("");
    if (active.current) {
      dispose();
      onNote(null);
      setInputs(undefined);
      setConnecting(false);
      return;
    }
    const request: { detach?: () => void } = {};
    active.current = request;
    setConnecting(true);
    try {
      if (!navigator.requestMIDIAccess) throw new Error("このブラウザはWeb MIDIに対応していません");
      const access = await navigator.requestMIDIAccess({ sysex: false });
      if (active.current === request) request.detach = listenMidi(access, onNote, setInputs, onKey);
    } catch (failure) {
      if (active.current === request) onError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      if (active.current === request) {
        if (!request.detach) active.current = undefined;
        setConnecting(false);
      }
    }
  }

  return { inputs, connecting, toggle };
}
