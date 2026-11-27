import liveExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-realtime-voice.json";
import type { FixedVoiceInput, VoiceBody } from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/fixed-voice";
import { midiFrequency } from "./midi-input";

type Targets = { tongue_body_x_cm: number; tongue_body_y_cm: number; lip_aperture_cm: number };
export type AppliedArticulation = { frame: number; targets: Targets };
export type AppliedBodyChange = { frame: number; body: VoiceBody; cells: [number, number] };
export type AppliedMidiNote = { frame: number; note: number | null };

type ManualClock = {
  controlIntervalOutputFrames: number;
  outputFrames: number;
  startFrame: number;
  stopFrame: number;
};
type Changes = { gate?: number; f0_hz?: number; targets?: Targets; body?: VoiceBody };

export function makeManualReplayCase(voice: FixedVoiceInput, clock: ManualClock, actions: AppliedArticulation[],
  bodyChanges: AppliedBodyChange[] = [], midiNotes?: AppliedMidiNote[]) {
  const { controlIntervalOutputFrames: interval, startFrame, stopFrame, outputFrames } = clock;
  const internalRate = voice.fixed_airway.sample_rate_hz;
  const factor = internalRate / voice.voice.output_sample_rate_hz;
  if (![interval, factor, outputFrames].every((n) => Number.isSafeInteger(n) && n > 0)
      || startFrame < 0 || startFrame > stopFrame || stopFrame >= outputFrames
      || outputFrames % interval !== 0) {
    throw new Error("再実行ケースの制御周期または記録範囲が不正です");
  }
  const events: ({ frame: number } & Changes)[] = [];
  function append(outputFrame: number, changes: Changes) {
    if (!Number.isSafeInteger(outputFrame) || outputFrame < startFrame || outputFrame > stopFrame
        || outputFrame % interval !== 0) {
      throw new Error("操作の適用フレームがCLIの制御境界にありません");
    }
    const frame = outputFrame / interval;
    const previous = events.at(-1);
    if (previous && frame < previous.frame) throw new Error("操作の時刻が昇順ではありません");
    // 同じ時刻で呼気と調音の両方が変わるときは、一つの制御更新にまとめる。
    if (previous?.frame === frame) Object.assign(previous, changes);
    else events.push({ frame, ...changes });
  }
  if (midiNotes) {
    for (const { frame, note } of midiNotes) {
      append(frame, note === null ? { gate: 0 } : { gate: 1, f0_hz: midiFrequency(note) });
    }
  } else {
    append(startFrame, { gate: 1 });
  }
  let nextBody = 0;
  for (const { frame, targets } of actions) {
    while (nextBody < bodyChanges.length && bodyChanges[nextBody].frame < frame) {
      const change = bodyChanges[nextBody++];
      append(change.frame, { body: change.body });
    }
    append(frame, { targets });
  }
  for (const { frame, body } of bodyChanges.slice(nextBody)) append(frame, { body });
  append(stopFrame, { gate: 0 });
  return {
    id: midiNotes ? "midi-voice-replay" : "manual-articulation-replay",
    upstream_revision: liveExperiment.upstream_revision,
    hypothesis: midiNotes ? "採用したMIDI音高と呼気を同じ出力時刻で再現する。"
      : bodyChanges.length ? "採用した体型・調音・呼気を同じ出力時刻で再現する。"
        : "ブラウザで採用した調音目標と呼気を、同じ出力時刻で再現する。",
    body: voice.body,
    posture: voice.posture,
    voice: { ...voice.voice, gate: 0 },
    articulators: {
      sample_rate_hz: internalRate,
      control_block_samples: interval * factor,
      tip_free: true,
      base_weight: 1,
      events,
    },
    measurement: { frames: outputFrames / interval },
  };
}

export type ManualReplayCase = ReturnType<typeof makeManualReplayCase>;
