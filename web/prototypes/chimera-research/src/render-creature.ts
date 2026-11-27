import type { CreatureMidiInput } from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/creature-midi";
import { ALLIGATOR_CALL_CODES, ALLIGATOR_PARAMS, type AlligatorEvent, type AlligatorInput } from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/alligator";
import { ELEPHANT_CALL_CODES, ELEPHANT_PARAMS, type ElephantEvent, type ElephantInput } from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/elephant";
import { SONGBIRD_CALL_CODES, type SongbirdEvent, type SongbirdInput } from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/songbird";
import { SEAL_CALL_CODES, type SealCallEvent, type SealEvent, type SealInput } from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/seal";
import processorUrl from "./creature-processor.ts?worker&url";
import { loadFixedModule } from "./render-fixed-voice";
import {
  CREATURE_PROCESSOR, CREATURE_TIMING_COLUMNS, creatureColumns, creatureSchedule,
  type CreatureInput, type CreatureMidiCommand, type CreatureWorkletMessage, type CreatureWorkletOptions,
} from "./creature-worklet-types";

export type SongbirdReplayCase = {
  id: string;
  upstream_revision: string;
  songbird_voice: SongbirdInput & { observe_syrinx: true };
};

export type SealReplayCase = {
  id: string;
  upstream_revision: string;
  seal_voice: SealInput;
};

export type AlligatorReplayCase = {
  id: string;
  upstream_revision: string;
  alligator_voice: AlligatorInput;
};

export type ElephantReplayCase = {
  id: string;
  upstream_revision: string;
  elephant_voice: ElephantInput;
};

type Sampling = {
  stride: number; offset?: number; exactFrames?: readonly number[]; windows?: readonly number[][];
  countRenderCalls?: boolean;
};

export async function renderAlligator(input: AlligatorInput, quantum: number, sampling: Sampling, midiReady?: MidiReady) {
  const optionalFinite = (value: number | undefined) => value === undefined || Number.isFinite(value);
  const paramsAllowed = new Set<string>(ALLIGATOR_PARAMS);
  const events = input.events;
  const isMidi = (event: AlligatorEvent) => Boolean(event.held_midi || event.midi_call);
  if ((midiReady && events.length > 0)
    || !orderedEvents(events, input.frames, (i) => isMidi(events[i - 1]) && isMidi(events[i]))
    || events.some((event) => {
      const { gate, params, play_call, stop_call, held_midi, midi_call } = event;
      const direct = gate !== undefined || Boolean(params || play_call || stop_call);
      return isMidi(event) === direct
        || Boolean(held_midi && midi_call)
        || Boolean(midi_call && !ALLIGATOR_CALL_CODES.has(midi_call.id))
        || (gate !== undefined && !(gate >= 0 && gate <= 1.5))
        || Boolean(params && Object.entries(params).some(([key, value]) => !paramsAllowed.has(key) || !Number.isFinite(value)))
        || Boolean(play_call && (stop_call || !ALLIGATOR_CALL_CODES.has(play_call.id)
          || !optionalFinite(play_call.pitch_hz) || !optionalFinite(play_call.amplitude)));
    })) {
    throw new Error("アリゲーターの手動目標・MIDI・コールの内容と時刻順を確認してください");
  }
  return renderCreature({ kind: "alligator", input }, quantum, sampling, midiReady);
}

type MidiReady = (send: (input: CreatureMidiInput) => void) => void;

export async function renderSongbird(input: SongbirdInput, quantum: number, sampling: Sampling, midiReady?: MidiReady) {
  const events = input.events;
  const isMidi = (event: SongbirdEvent) => Boolean(event.held_midi || event.midi_call);
  if ((midiReady && events.length > 0)
    || !orderedEvents(events, input.frames, (i) => isMidi(events[i - 1]) && isMidi(events[i]))
    || events.some((event) => {
      const { gate, controls, play_call, stop_call, held_midi, midi_call } = event;
      const hasDirectControls = Boolean(gate !== undefined || controls || play_call || stop_call);
      return (gate !== undefined && !(gate >= 0 && gate <= 1.5))
        || isMidi(event) === hasDirectControls
        || Boolean(held_midi && midi_call)
        || Boolean(midi_call && !SONGBIRD_CALL_CODES.has(midi_call.id))
        || Boolean(play_call && (!SONGBIRD_CALL_CODES.has(play_call.id) || stop_call));
    })) {
    throw new Error("鳴禽のイベントを確認してください");
  }
  return renderCreature({ kind: "songbird", input }, quantum, sampling, midiReady);
}

export async function renderElephant(input: ElephantInput, quantum: number, sampling: Sampling, midiReady?: MidiReady) {
  const optionalFinite = (value: number | undefined) => value === undefined || Number.isFinite(value);
  const paramsAllowed = new Set<string>(ELEPHANT_PARAMS);
  const events = input.events;
  const isMidi = (event: ElephantEvent) => Boolean(event.held_midi || event.midi_call);
  if ((midiReady && events.length > 0)
    || !orderedEvents(events, input.frames, (i) => isMidi(events[i - 1]) && isMidi(events[i]))
    || events.some((event) => {
      const { gate, params, play_call, stop_call, held_midi, midi_call } = event;
      const direct = gate !== undefined || Boolean(params || play_call || stop_call);
      return isMidi(event) === direct
        || Boolean(held_midi && midi_call)
        || Boolean(midi_call && !ELEPHANT_CALL_CODES.has(midi_call.id))
        || (gate !== undefined && !(gate >= 0 && gate <= 1.5))
        || Boolean(params && Object.entries(params).some(([key, value]) => !paramsAllowed.has(key) || !Number.isFinite(value)))
        || Boolean(play_call && (!ELEPHANT_CALL_CODES.has(play_call.id) || stop_call
          || !optionalFinite(play_call.pitch_hz) || !optionalFinite(play_call.amplitude)));
    })) {
    throw new Error("ゾウの手動目標・MIDI・コールと時刻を確認してください");
  }
  return renderCreature({ kind: "elephant", input }, quantum, sampling, midiReady);
}

export async function renderSeal(input: SealInput, quantum: number, sampling: Sampling, midiReady?: MidiReady) {
  const { frames, events: breath } = input.breath;
  const calls = input.events ?? [];
  const optionalFinite = (value: number | undefined) => value === undefined || Number.isFinite(value);
  const isMidi = (event: SealCallEvent) => Boolean(event.held_midi || event.midi_call);
  if ((midiReady && (breath.length > 0 || calls.length > 0))
    || !orderedEvents(breath, frames)
    || !orderedEvents(calls, frames, (i) => isMidi(calls[i - 1]) && isMidi(calls[i]))
    || breath.some(({ gate, controls }) => !optionalFinite(gate) || (gate === undefined && !controls))
    || calls.some((event) => {
      const { pitch_hz, roughness, play_call, stop_call, held_midi, midi_call } = event;
      const direct = pitch_hz !== undefined || roughness !== undefined || Boolean(play_call || stop_call);
      return !optionalFinite(pitch_hz) || !optionalFinite(roughness)
        || isMidi(event) === direct
        || Boolean(held_midi && midi_call)
        || Boolean(midi_call && !SEAL_CALL_CODES.has(midi_call.id))
        || Boolean(play_call && (stop_call || !SEAL_CALL_CODES.has(play_call.id)
          || !optionalFinite(play_call.pitch_hz) || !optionalFinite(play_call.amplitude)));
    })) {
    throw new Error("アザラシの呼気・コールの内容と時刻順を確認してください");
  }
  // 同じフレームの呼気、コール、MIDIをCLIと同じ順序で適用する。
  const events: SealEvent[] = [...breath.map((event) => ({ frame: event.frame, breath: event })),
    ...calls.map((event) => ({ frame: event.frame, call: event }))];
  events.sort((a, b) => a.frame - b.frame);
  return renderCreature({ kind: "seal", input, events }, quantum, sampling, midiReady);
}

function orderedEvents(events: readonly { frame: number }[], frames: number,
  canShareFrame?: (index: number) => boolean): boolean {
  return events.every(({ frame }, i) => Number.isSafeInteger(frame) && frame >= 0 && frame < frames
    && (i === 0 || events[i - 1].frame < frame || (events[i - 1].frame === frame && canShareFrame?.(i))));
}

async function renderCreature(voice: CreatureInput, quantum: number, sampling: Sampling, midiReady?: MidiReady) {
  const { stride, offset = stride - 1, exactFrames = [], windows = [], countRenderCalls } = sampling;
  const input = creatureSchedule(voice);
  const isOutputFrame = (frame: number) => Number.isSafeInteger(frame) && frame >= 0 && frame < input.frames;
  if (![input.sample_rate_hz, input.frames, stride, quantum].every((n) => Number.isSafeInteger(n) && n > 0)
    || !Number.isSafeInteger(offset) || offset < 0 || offset >= stride
    || exactFrames.some((frame) => !isOutputFrame(frame))
    || windows.some((window) => window.length !== 2 || !isOutputFrame(window[0])
      || !Number.isSafeInteger(window[1]) || window[1] <= window[0] || window[1] > input.frames)) {
    throw new Error("動物音声のレンダー長・観測間隔・イベント時刻を確認してください");
  }
  const points = new Set([...exactFrames, input.frames - 1]);
  for (let frame = offset; frame < input.frames; frame += stride) points.add(frame);
  for (const [start, end] of windows) {
    for (let frame = start; frame < end; frame++) points.add(frame);
  }
  const observationFrames = [...points].sort((a, b) => a - b);
  const columns = creatureColumns(voice);
  const context = new AudioContext({ sampleRate: input.sample_rate_hz, latencyHint: "interactive" });
  let node: AudioWorkletNode | undefined;
  let timer: number | undefined;
  try {
    const [module] = await Promise.race([
      Promise.all([loadFixedModule(), context.audioWorklet.addModule(processorUrl), context.resume()]),
      new Promise<never>((_, reject) => {
        timer = window.setTimeout(() => reject(new Error("動物音声のAudioContextを起動できませんでした")), 10000);
      }),
    ]);
    window.clearTimeout(timer);
    const options: CreatureWorkletOptions = {
      module, voice, observationFrames, quantum, countRenderCalls, captureMidi: Boolean(midiReady),
    };
    const worklet = new AudioWorkletNode(context, CREATURE_PROCESSOR, {
      numberOfInputs: 0, numberOfOutputs: 1, outputChannelCount: [1], processorOptions: options,
    });
    node = worklet;
    const { pcm, observations, timing, renderCalls, type: _type, sampleRate: workletSampleRate, ...stats } =
      await new Promise<Extract<CreatureWorkletMessage, { type: "complete" }>>((resolve, reject) => {
        timer = window.setTimeout(() => reject(new Error("動物音声の計測結果を受信できませんでした")),
          15000 + input.frames / input.sample_rate_hz * 1000);
        worklet.onprocessorerror = () => reject(new Error("動物音声のAudioWorkletの処理が停止しました"));
        worklet.port.onmessage = ({ data }: MessageEvent<CreatureWorkletMessage>) => {
          if (data.type === "error") reject(new Error(data.message));
          else if (data.type === "complete") resolve(data);
          else midiReady?.((input) => worklet.port.postMessage({ type: "midi", input } satisfies CreatureMidiCommand));
        };
        worklet.connect(context.destination);
      });
    return {
      pcm,
      report: {
        sampleRate: context.sampleRate, workletSampleRate, outputFrames: pcm.length, contextState: context.state,
        columns, observations: rows(observations, columns.length),
        timingColumns: CREATURE_TIMING_COLUMNS, timing: rows(timing, CREATURE_TIMING_COLUMNS.length),
        ...(renderCalls && { renderCalls: Array.from(renderCalls) }),
        ...stats,
      },
    };
  } finally {
    window.clearTimeout(timer);
    if (node) {
      node.onprocessorerror = null;
      node.port.onmessage = null;
      node.port.close();
      node.disconnect();
    }
    if (context.state !== "closed") await context.close();
  }
}

function rows(values: Float64Array, width: number): number[][] {
  const result = [];
  for (let i = 0; i < values.length; i += width) {
    result.push(Array.from(values.subarray(i, i + width)));
  }
  return result;
}
