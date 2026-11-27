import {
  observationFields, SONG_OBSERVATION_FIELDS, type FixedVoiceInput, type LiveSongKey, type ManualTargets, type VoiceBody,
} from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/fixed-voice";
import processorUrl from "./live-processor.ts?worker&url";
import { LIVE_PROCESSOR, MANUAL_EVENT_WORDS, MIDI_EVENT_WORDS, type LiveCommand, type LiveMessage, type LiveOptions, type LiveResult, type LiveSettings } from "./live-worklet-types";
import { makeManualReplayCase, type AppliedArticulation, type AppliedMidiNote } from "./manual-replay";
import { loadFixedModule, splitSongLyrics } from "./render-fixed-voice";

const timingColumns = ["context_frame", "quantum_frames", "process_ms", "callback_elapsed_ms"];

export function startRealtimeVoice(
  voice: FixedVoiceInput,
  settings: LiveSettings,
  onPhase: (phase: "voicing" | "release") => void,
  song?: { lyrics: string; vibratoCents: number },
) {
  const { quantum, preRoll, maximumVoiced, release } = settings;
  const columns = [...timingColumns, ...(song ? SONG_OBSERVATION_FIELDS
    : observationFields(settings.manual || settings.midi ? "manual" : undefined))];
  if (!Number.isSafeInteger(quantum) || quantum <= 0
      || ![preRoll, maximumVoiced, release].every((n) => Number.isSafeInteger(n) && n > 0 && n % quantum === 0)) {
    throw new Error("準備・発声・減衰のフレーム数はブロック長の正の整数倍で指定してください");
  }
  const context = new AudioContext({ sampleRate: voice.voice.output_sample_rate_hz, latencyHint: "interactive" });
  const resumed = context.resume();
  let node: AudioWorkletNode | undefined;
  let timer: number | undefined;
  let pendingMidiNote: number | null | undefined;
  const pendingSongKeys: LiveSongKey[] = [];

  const finished = (async () => {
    try {
      const ready = Promise.all([loadFixedModule(), context.audioWorklet.addModule(processorUrl), resumed]);
      const [module] = await Promise.race([ready, new Promise<never>((_, reject) => {
        timer = window.setTimeout(() => reject(new Error("実時間AudioContextを開始できませんでした")), 10000);
      })]);
      window.clearTimeout(timer);
      const syllables = song && await splitSongLyrics(song.lyrics, AbortSignal.timeout(10000), module);
      const songMode = song && syllables && {
        syllableBytes: new TextEncoder().encode(JSON.stringify(syllables)), vibratoCents: song.vibratoCents,
      };
      const processorOptions: LiveOptions = {
        module, voice: { ...voice, voice: { ...voice.voice, gate: 0 } }, settings, ...(songMode && { song: songMode }),
      };
      const worklet = new AudioWorkletNode(context, LIVE_PROCESSOR, {
        numberOfInputs: 0,
        numberOfOutputs: 1,
        outputChannelCount: [1],
        processorOptions,
      });
      node = worklet;
      if (pendingMidiNote !== undefined) worklet.port.postMessage({ type: "midi-note", note: pendingMidiNote });
      for (const key of pendingSongKeys) worklet.port.postMessage({ type: "song-key", key });
      pendingSongKeys.length = 0;
      const began = performance.now();
      let voicingNoticeMs: number | null = null;
      let releaseNoticeMs: number | null = null;
      const { pcm, observations, appliedTargets, appliedNotes, songKeys, type: _type, ...stats } = await new Promise<LiveResult>((resolve, reject) => {
        timer = window.setTimeout(() => reject(new Error("実時間Workletの完了通知を受信できませんでした")), 15000);
        worklet.onprocessorerror = () => reject(new Error("実時間AudioWorkletの処理が停止しました"));
        worklet.port.onmessage = ({ data }: MessageEvent<LiveMessage>) => {
          if (data.type === "complete") resolve(data);
          else if (data.type === "error") reject(new Error(data.message));
          else {
            const elapsed = performance.now() - began;
            if (data.type === "voicing") voicingNoticeMs = elapsed;
            else releaseNoticeMs = elapsed;
            onPhase(data.type);
          }
        };
        worklet.connect(context.destination);
      });
      const elapsedWallMs = performance.now() - began;
      const rows = [];
      for (let i = 0; i < observations.length; i += columns.length) {
        rows.push(Array.from(observations.subarray(i, i + columns.length)));
      }
      const articulation: AppliedArticulation[] = [];
      const midiNotes: AppliedMidiNote[] = [];
      let replayCase;
      if (appliedTargets) {
        for (let i = 0; i < appliedTargets.length; i += MANUAL_EVENT_WORDS) {
          const [frame, x, y, lip] = appliedTargets.subarray(i, i + MANUAL_EVENT_WORDS);
          articulation.push({ frame, targets: { tongue_body_x_cm: x, tongue_body_y_cm: y, lip_aperture_cm: lip } });
        }
      }
      if (appliedNotes) {
        for (let i = 0; i < appliedNotes.length; i += MIDI_EVENT_WORDS) {
          const [frame, note] = appliedNotes.subarray(i, i + MIDI_EVENT_WORDS);
          midiNotes.push({ frame, note: note === -1 ? null : note });
        }
      }
      if (appliedTargets || appliedNotes) {
        replayCase = makeManualReplayCase(processorOptions.voice, {
          startFrame: stats.startFrame,
          stopFrame: stats.stopFrame,
          outputFrames: pcm.length,
          controlIntervalOutputFrames: stats.controlIntervalOutputFrames,
        }, articulation, stats.bodyChanges, appliedNotes ? midiNotes : undefined);
      }
      const songReplay = songMode && songKeys ? {
        id: "worklet-midi-song-replay",
        upstream_revision: "c6147d0198890475dbe8a65a0bb8f56240c539b7",
        hypothesis: "歌唱の押下と解放を採用済みの出力フレームで再現する。",
        live_song_voice: {
          body: processorOptions.voice.body, posture: processorOptions.voice.posture, voice: processorOptions.voice.voice,
          internal_sample_rate_hz: processorOptions.voice.fixed_airway.sample_rate_hz,
          vibrato_cents: songMode.vibratoCents, frames: pcm.length, stop_frame: stats.stopFrame,
          syllables, events: songKeys,
        },
      } : undefined;
      return {
        pcm,
        replayCase: songReplay ?? replayCase,
        report: {
          sampleRate: context.sampleRate,
          contextState: context.state,
          baseLatencySeconds: context.baseLatency,
          outputLatencySeconds: context.outputLatency,
          elapsedWallMs,
          voicingNoticeMs,
          releaseNoticeMs,
          outputFrames: pcm.length,
          columns,
          ...stats,
          ...(appliedTargets && { articulation }),
          ...(appliedNotes && { midiNotes }),
          ...(songKeys && { songKeys }),
          observations: rows,
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
      await context.close();
    }
  })();
  const send = (command: LiveCommand) => node?.port.postMessage(command);
  return {
    finished,
    stop: () => send("stop"),
    setManualTargets: (targets: ManualTargets) => send({ type: "articulation", targets }),
    setManualBody: (body: VoiceBody) => send({ type: "body", body }),
    setMidiNote(note: number | null) {
      if (song) return;
      if (node) send({ type: "midi-note", note });
      else pendingMidiNote = note;
    },
    setSongKey(key: LiveSongKey) {
      if (!song) return;
      if (node) send({ type: "song-key", key });
      else pendingSongKeys.push(key);
    },
  };
}
