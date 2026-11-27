import {
  AREA_GRID_COLUMNS,
  GLOTTAL_COLUMNS,
  RADIATION_COLUMNS,
  observationFields,
  TRACT_ACOUSTIC_WORDS,
  TRACT_GEOMETRY_WORDS,
  type BeatPattern,
  type BeatCommand,
  type FixedVoiceInput,
  type ScoreTurbulence,
} from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/fixed-voice";
import {
  lyricSyllables, planEnglish, planIpa, planSong, type SongInput,
} from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/planning";
import dictionaryUrl from "../../../../research/experiments/chimera-rebuild/data/cmudict.txt.gz?url&no-inline";
import profileExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-tract-profile.json";
import realtimeExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-live-ipa.json";
import speechExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-ipa-voice.json";
import englishExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-english-voice.json";
import songExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-song-voice.json";
import realtimeSongExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-live-song.json";
import songWarmupExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-live-song-render-warmup.json";
import speechWarmupExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-live-tsp-firefox-render-preparation.json";
import liveBeatExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-live-beatbox.json";
import wasmUrl from "../../../../research/experiments/chimera-rebuild/target/wasm32-unknown-unknown/release/vocal_wasm.wasm?url&no-inline";
import processorUrl from "./fixed-processor-entry.ts?worker&url";
import measuredProcessorUrl from "./fixed-processor-measured-entry.ts?worker&url";
import {
  PROCESSOR_NAME, REALTIME_SPEECH_COLUMNS, SCORE_PREPARATION_COLUMNS, type BeatProgress, type LiveTractMessage, type LiveTractSample,
  type ProcessorOptions, type TractProfile, type WorkletCommand, type WorkletMessage, type WorkletModuleTiming,
  type SongSilentLeadQuanta,
} from "./fixed-worklet-types";
import { SongRecording, type SongRecordingOptions, type SongRecordingRequest } from "./song-recording";
import { prepareSongSilentLead, registerSongSilentLead } from "./song-silent-lead";
import type { RecordedTract } from "./recorded-tract";

const tractStride = profileExperiment.measurement.profile_stride_output_frames;

type StartupMark = (phase: string) => void;

const nativeRegistrationPhases = new Set(["worklet_module_start", "worklet_module_ready", "worklet_ready_received"]);

function startSongTrace(traceEvaluation: boolean, traceNativeRegistration: boolean) {
  let context: AudioContext | undefined;
  const marks: { phase: string; wallMs: number; epochMs?: number; contextFrame: number | null;
    contextState: AudioContextState | null }[] = [];
  return {
    marks,
    attach: (audioContext: AudioContext) => { context = audioContext; },
    mark: (phase: string) => {
      const wallMs = performance.now();
      marks.push({ phase, wallMs, ...((traceEvaluation || traceNativeRegistration) && { epochMs: Date.now() }),
        contextFrame: context ? Math.round(context.currentTime * context.sampleRate) : null,
        contextState: context?.state ?? null });
      if (traceNativeRegistration && nativeRegistrationPhases.has(phase)) {
        const name = `chimera:${phase}`;
        performance.mark(name, { startTime: wallMs });
        performance.clearMarks(name);
      }
    },
  };
}

export async function loadFixedModule(signal?: AbortSignal, mark?: StartupMark): Promise<WebAssembly.Module> {
  mark?.("wasm_fetch");
  const response = await fetch(wasmUrl, { signal });
  if (!response.ok) throw new Error(`WASMの取得に失敗しました（${response.status}）`);
  const bytes = await response.arrayBuffer();
  if (!mark) return WebAssembly.compile(bytes);
  mark("wasm_bytes");
  const module = await WebAssembly.compile(bytes);
  mark("wasm_ready");
  return module;
}

let englishModuleLoad: Promise<WebAssembly.Module> | undefined;

function loadEnglishModule(): Promise<WebAssembly.Module> {
  // 一つの再生の中止で、同じ読み込みを待つほかの再生を中止しない。
  return englishModuleLoad ??= loadFixedModule().catch((error: unknown) => {
    englishModuleLoad = undefined;
    throw error;
  });
}

export async function renderFixedVoice(voice: FixedVoiceInput, observationStride: number) {
  const outputRate = voice.voice.output_sample_rate_hz;
  const factor = voice.fixed_airway.sample_rate_hz / outputRate;
  const frames = voice.fixed_airway.sample_count / factor;
  if (![frames, observationStride, factor].every((n) => Number.isSafeInteger(n) && n > 0)) {
    throw new Error("レンダー長、観測間隔、間引き率は正の整数で指定してください");
  }
  return renderOffline(await loadFixedModule(), voice, frames, observationStride);
}

export type SpeechVoiceInput = Omit<FixedVoiceInput, "voice"> & {
  voice: Omit<FixedVoiceInput["voice"], "f0_hz"> & { f0_hz?: number };
  source_variation?: { pitch_drift_cents?: number; period_jitter?: number; amplitude_shimmer?: number };
  turbulence?: ScoreTurbulence;
};

export async function renderIpaVoice(
  voice: SpeechVoiceInput, text: string, rate: number, observationStride: number, start = 0.05, tractGrid = false,
) {
  const module = await loadFixedModule();
  const { initialVoice, frames, score, details, replayCase } = prepareIpaVoice(module, voice, text, rate, start);
  const { audio, report } = await renderOffline(module, initialVoice, frames, observationStride, score, tractStride, tractGrid);
  return { audio, report: { ...report, ...details }, replayCase };
}

function prepareIpaVoice(module: WebAssembly.Module, voice: SpeechVoiceInput, text: string, rate: number, start: number) {
  const { speech, gestures, score, basePitchHz, initialPitchHz } = planIpa(
    module, text, start, rate, voice.voice.f0_hz, voice.body,
  );
  const frames = Math.round(speech.render_end_seconds * voice.voice.output_sample_rate_hz);
  const initialVoice = { ...voice, voice: { ...voice.voice, f0_hz: initialPitchHz } };
  const details = { input: text, speech, gestures, body: voice.body, basePitchHz };
  const replayCase = makeSpeechReplay("ipa", voice, text, rate, start, score.noiseScale);
  return { score, frames, initialVoice, details, replayCase };
}

export async function renderBeatPattern(voice: FixedVoiceInput, beat: BeatPattern, frames: number, stride: number) {
  const { pattern, ...settings } = beat;
  const mode = { ...settings, text: new TextEncoder().encode(pattern) };
  const { audio, report } = await renderOffline(await loadFixedModule(), voice, frames, stride, mode);
  return { audio, report: { ...report, beat, voice, observationStride: stride } };
}

type BeatControls = (progress: BeatProgress, send: (command: BeatCommand) => void) => void;

export function renderRealtimeBeatPattern(
  voice: FixedVoiceInput, beat: BeatPattern, frames: number, stride: number,
  controls: BeatControls, signal: AbortSignal,
) {
  const rate = voice.voice.output_sample_rate_hz;
  const { expected_render_quantum_frames, lead_frames } = liveBeatExperiment.measurement;
  return withRealtimeContext(rate, signal, async (context, module) => {
    const { pattern, ...settings } = beat;
    const mode = { ...settings, text: new TextEncoder().encode(pattern) };
    const realtime = { quantum: expected_render_quantum_frames, leadFrames: lead_frames };
    const { pcm, report } = await captureWorklet(
      context, { module, voice, frames, observationStride: stride, mode, realtime }, signal, { beat: controls },
    );
    if (!pcm || !report.beatEvents) throw new Error("実時間のビートのPCMまたは操作記録がありません");
    const replayCase = {
      id: "worklet-live-beatbox-replay",
      upstream_revision: liveBeatExperiment.upstream_revision,
      beatbox_pattern: {
        pattern, bpm: beat.bpm, swing: beat.swing, voice: voice.voice, posture: voice.posture,
        internal_sample_rate_hz: voice.fixed_airway.sample_rate_hz, initial_f0_hz: beat.initialPitchHz,
        noise_scale: beat.noiseScale, render_end_seconds: pcm.length / rate,
        events: report.beatEvents.map(({ contextFrame: _context, ...operation }) => operation),
      },
    };
    return { pcm, report: { ...report, beat, voice, observationStride: stride }, replayCase };
  });
}

export async function renderRealtimeIpaVoice(voice: SpeechVoiceInput, text: string, rate: number,
  observationStride: number, signal: AbortSignal, onTract?: (sample: LiveTractSample) => void) {
  const outputRate = voice.voice.output_sample_rate_hz;
  return withRealtimeContext(outputRate, signal, async (context, module) => {
    const { initialVoice, frames, score, details, replayCase } = prepareIpaVoice(module, voice, text, rate, 0.05);
    const quantum = speechExperiment.measurement.expected_render_quantum_frames;
    const realtime = { quantum, leadFrames: realtimeExperiment.measurement.lead_frames, publishTract: Boolean(onTract) };
    const { pcm, report } = await captureWorklet(context,
      { module, voice: initialVoice, frames, observationStride, mode: score, tractStride, tractGrid: Boolean(onTract), realtime },
      signal, { onTract });
    if (!pcm) throw new Error("実時間WorkletのPCMがありません");
    return { pcm, report: { ...report, ...details }, replayCase };
  });
}

async function registerFixedWorklet(context: BaseAudioContext, mark?: StartupMark, traceEvaluation = false) {
  mark?.("worklet_module_start");
  await context.audioWorklet.addModule(traceEvaluation ? measuredProcessorUrl : processorUrl);
  mark?.("worklet_module_ready");
}

async function withRealtimeContext<T>(outputRate: number, signal: AbortSignal,
  run: (context: AudioContext, module: WebAssembly.Module, registration?: Promise<void>) => Promise<T>,
  startup?: { trace?: ReturnType<typeof startSongTrace>; parallelRegistration?: boolean;
    registerBeforeResume?: boolean; traceEvaluation?: boolean; loadModule?: () => Promise<WebAssembly.Module> }) {
  signal.throwIfAborted();
  const trace = startup?.trace;
  const mark = trace?.mark;
  mark?.("context_start");
  const context = new AudioContext({ sampleRate: outputRate, latencyHint: "interactive" });
  trace?.attach(context);
  mark?.("context_created");
  let cancel: () => void;
  const cancelled = new Promise<never>((_, reject) => {
    cancel = () => reject(signal.reason);
    signal.addEventListener("abort", cancel, { once: true });
  });
  const resume = () => {
    signal.throwIfAborted();
    mark?.("resume_start");
    return context.resume();
  };
  const registerWhileSuspended = async () => {
    // ChromiumはContext生成時にも描画を開始できるため、登録前に停止完了を待つ。
    mark?.("suspend_before_registration_start");
    await context.suspend();
    signal.throwIfAborted();
    mark?.("suspend_before_registration_ready");
    await registerFixedWorklet(context, mark, startup?.traceEvaluation);
  };
  const start = async () => {
    const loading = startup?.loadModule ? startup.loadModule() : loadFixedModule(signal, mark);
    let registration = startup?.registerBeforeResume ? registerWhileSuspended() : undefined;
    const resuming = registration ? registration.then(resume) : resume();
    if (!registration && startup?.parallelRegistration) {
      registration = registerFixedWorklet(context, mark, startup.traceEvaluation);
    }
    // 計画完了前の失敗もここで監視し、ノード生成の直前に元の拒否を受け取る。
    void registration?.catch(() => {});
    const [module] = await Promise.all([loading, mark ? resuming.then(() => mark("resume_ready")) : resuming]);
    mark?.("parallel_ready");
    signal.throwIfAborted();
    return run(context, module, registration);
  };
  try {
    return await Promise.race([start(), cancelled]);
  } finally {
    signal.removeEventListener("abort", cancel!);
    if (context.state !== "closed") {
      await context.close().catch((error) => { if (!signal.aborted) throw error; });
    }
  }
}

export async function renderEnglishVoice(
  voice: SpeechVoiceInput, text: string, rate: number, observationStride: number, start = 0.05, inputId?: string,
) {
  const [module, dictionary] = await Promise.all([loadEnglishModule(), loadDictionary()]);
  const { initialVoice, frames, score, details, replayCase } = prepareEnglishVoice(module, dictionary, voice,
    text, rate, start, inputId);
  const { audio, report } = await renderOffline(module, initialVoice, frames, observationStride, score, tractStride);
  return { audio, report: { ...report, ...details }, replayCase };
}

export function renderRealtimeEnglishVoice(
  voice: SpeechVoiceInput, text: string, rate: number, observationStride: number, signal: AbortSignal,
  start = 0.05, inputId?: string,
  diagnostic?: { tracePhases: boolean; traceWasmCore: boolean; preparation?: string; delayOneQuantum?: boolean },
) {
  return withRealtimeContext(voice.voice.output_sample_rate_hz, signal, async (context, module) => {
    const dictionary = await loadDictionary();
    signal.throwIfAborted();
    const { initialVoice, frames, score, details, replayCase } = prepareEnglishVoice(module, dictionary, voice,
      text, rate, start, inputId);
    const requested = diagnostic?.preparation;
    const warmup = speechWarmupExperiment.measurement;
    const onsetLoadFrames = new Map([
      ["split-onset-load-224", 224],
      ["split-onset-load-256", 256],
      ["split-onset-load-288", 288],
      ["split-onset-load-320", 320],
      ["split-onset-load-416", 416],
    ]);
    const finalBlockFrames = onsetLoadFrames.get(requested ?? "");
    const deferFinalBlock = requested === "split-onset-load" || finalBlockFrames !== undefined;
    const onsetLoad = requested === "split-early-load" || deferFinalBlock;
    const split = requested === "split" || onsetLoad;
    const blockFrames = warmup.draw_block_frames * (onsetLoad ? 2 : 1);
    const renderPreparation = requested === "zero" || requested === "draw" || split ? {
      calls: warmup.zero_frame_calls,
      frames: requested === "zero" ? 0 : warmup.draw_frames + (finalBlockFrames === undefined ? 0 : finalBlockFrames - blockFrames),
      blockFrames,
      distributed: split,
      startDuringLead: split,
      deferFinalBlock,
      finalBlockFrames,
    } : undefined;
    const quantum = englishExperiment.measurement.expected_render_quantum_frames;
    const leadFrames = realtimeExperiment.measurement.lead_frames + (split && diagnostic?.delayOneQuantum ? quantum : 0);
    const realtime: ProcessorOptions["realtime"] = { quantum, leadFrames,
      ...((diagnostic?.tracePhases || diagnostic?.traceWasmCore || renderPreparation) && { traceRenderPhases: "speech" }),
      traceWasmCore: diagnostic?.traceWasmCore, renderPreparation };
    const { pcm, report } = await captureWorklet(context,
      { module, voice: initialVoice, frames, observationStride, mode: score, tractStride, realtime }, signal);
    if (!pcm) throw new Error("実時間WorkletのPCMがありません");
    return { pcm, report: { ...report, ...details }, replayCase };
  }, { loadModule: loadEnglishModule });
}

function prepareEnglishVoice(module: WebAssembly.Module, dictionary: Uint8Array, voice: SpeechVoiceInput,
  text: string, rate: number, start: number, inputId?: string) {
  const { speech, gestures, score, initialPitchHz } = planEnglish(
    module, text, dictionary, start, rate, voice.voice.f0_hz, voice.body,
  );
  const frames = Math.round(speech.render_end_seconds * voice.voice.output_sample_rate_hz);
  const initialVoice = { ...voice, voice: { ...voice.voice, f0_hz: initialPitchHz } };
  const { source_variation: variation, turbulence } = voice;
  if (variation) {
    score.sourcePreparation = { warmUpFrames: 0, pitchDriftCents: variation.pitch_drift_cents ?? 0,
      periodJitter: variation.period_jitter ?? 0, amplitudeShimmer: variation.amplitude_shimmer ?? 0 };
  }
  if (turbulence) score.turbulence = turbulence;
  const replayCase = makeSpeechReplay("english", voice, text, rate, start, score.noiseScale, inputId);
  return { initialVoice, frames, score, details: { input: text, speech, gestures, body: voice.body,
    basePitchHz: score.basePitchHz }, replayCase };
}

function makeSpeechReplay(language: "ipa" | "english", voice: SpeechVoiceInput, text: string,
  rate: number, start: number, noiseScale: number | null, inputId = `worklet-${language}`) {
  const experiment = language === "ipa" ? speechExperiment : englishExperiment;
  const turbulence = voice.turbulence ?? (noiseScale != null ? { scale: noiseScale } : undefined);
  return {
    id: `worklet-${language}-replay`,
    upstream_revision: experiment.upstream_revision,
    speech_voice: {
      language, body: voice.body,
      input: { id: inputId, text, rate, start_seconds: start },
      posture: voice.posture, internal_sample_rate_hz: voice.fixed_airway.sample_rate_hz, voice: voice.voice,
      source_variation: voice.source_variation, turbulence,
    },
  };
}

let dictionaryLoad: Promise<Uint8Array> | undefined;

function loadDictionary(): Promise<Uint8Array> {
  return dictionaryLoad ??= readDictionary().catch((error: unknown) => {
    dictionaryLoad = undefined;
    throw error;
  });
}

export async function splitSongLyrics(text: string, signal: AbortSignal, loaded?: WebAssembly.Module) {
  const [module, dictionary] = await Promise.all([loaded ?? loadFixedModule(signal), loadDictionary()]);
  signal.throwIfAborted();
  return lyricSyllables(module, text, dictionary);
}

async function readDictionary(): Promise<Uint8Array> {
  const response = await fetch(dictionaryUrl);
  if (!response.ok) throw new Error(`英語の発音辞書を取得できません（${response.status}）`);
  const bytes = new Uint8Array(await response.arrayBuffer());
  // サーバーがContent-Encodingとして展開済みの場合は受け取ったバイト列を使う。
  if (bytes[0] !== 0x1f || bytes[1] !== 0x8b) return bytes;
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

type SongVoiceInput = Omit<FixedVoiceInput, "voice"> & {
  voice: Omit<FixedVoiceInput["voice"], "f0_hz"> & {
    base_pitch_hz?: number;
    pitch_drift_cents?: number;
    period_jitter?: number;
    amplitude_shimmer?: number;
  };
  warm_up_frames?: number;
  render_end_seconds?: number;
  turbulence?: ScoreTurbulence;
};

export async function renderSongVoice(
  voice: SongVoiceInput, input: SongInput, observationStride: number,
) {
  const [module, dictionary] = await Promise.all([loadFixedModule(), songDictionary(input)]);
  const { details, replayCase, score, frames, initialVoice } = prepareSongVoice(module, dictionary, voice, input);
  const { audio, report } = await renderOffline(module, initialVoice, frames, observationStride, score);
  return { audio, report: { ...report, ...details }, replayCase };
}

export function renderRealtimeSongVoice(voice: SongVoiceInput, input: SongInput,
  observationStride: number, signal: AbortSignal, recording?: SongRecordingRequest,
  startup?: { traceStartup: boolean; parallelRegistration: boolean; traceEvaluation: boolean; traceNativeRegistration: boolean;
    registerBeforeResume?: boolean;
    traceRenderPhases?: boolean; renderPreparation?: string;
    scorePreparationBlockFrames?: number; scorePreparationInitialBlocks?: readonly number[];
    traceScorePreparationBlocks?: boolean;
    silentLeadQuanta?: SongSilentLeadQuanta; silentLeadTraceInput?: boolean; silentLeadTraceNative?: boolean;
    parallelSilentLeadRegistration?: boolean }) {
  const traceEvaluation = startup?.traceEvaluation ?? false;
  const traceNativeRegistration = startup?.traceNativeRegistration ?? false;
  const trace = startup?.traceStartup || traceEvaluation || traceNativeRegistration
    ? startSongTrace(traceEvaluation, traceNativeRegistration) : undefined;
  const mark = trace?.mark;
  const registerBeforeResume = startup?.registerBeforeResume ?? false;
  const parallelRegistration = !registerBeforeResume && (startup?.parallelRegistration ?? false);
  return withRealtimeContext(voice.voice.output_sample_rate_hz, signal, async (context, module, registration) => {
    const dictionaryState = input.lyrics === undefined ? "none" : dictionaryLoad ? "warm" : "cold";
    mark?.("dictionary_start");
    const dictionary = await songDictionary(input);
    mark?.("dictionary_ready");
    signal.throwIfAborted();
    mark?.("planner_start");
    const { details, replayCase, score, frames, initialVoice } = prepareSongVoice(module, dictionary, voice, input, mark);
    mark?.("planner_ready");
    const warmup = songWarmupExperiment.measurement;
    const requested = startup?.renderPreparation;
    const firstQuantumOffset = requested === "split-192" ? 0 : requested === "split-192-deferred" ? 2 : undefined;
    const distributed = firstQuantumOffset !== undefined;
    const warmupFrames = distributed ? 192 : requested === "draw" ? warmup.draw_frames : Number(requested);
    const validWarmup = requested === "zero" || (Number.isSafeInteger(warmupFrames) && warmupFrames > 0
      && warmupFrames <= warmup.draw_frames && warmupFrames % warmup.draw_block_frames === 0);
    const quantum = songExperiment.measurement.expected_render_quantum_frames;
    const scorePreparationBlockFrames = startup?.scorePreparationBlockFrames;
    const scorePreparationInitialBlocks = startup?.scorePreparationInitialBlocks;
    if (scorePreparationInitialBlocks !== undefined && scorePreparationBlockFrames === undefined) {
      throw new Error("最初の予備描画片を指定する場合は、後続の分割長も指定してください");
    }
    if (scorePreparationBlockFrames !== undefined && !score.sourcePreparation) {
      throw new Error("分割予備描画には上流音源の設定を指定してください");
    }
    const realtime = {
      quantum,
      leadFrames: realtimeSongExperiment.measurement.lead_frames,
      reportSchedule: recording !== undefined,
      publishTract: recording?.includeTract,
      traceRenderPhases: startup?.traceRenderPhases,
      traceFirstOutput: startup?.traceStartup,
      scorePreparationSplit: scorePreparationBlockFrames === undefined ? undefined
        : { blockFrames: scorePreparationBlockFrames, initialBlocks: scorePreparationInitialBlocks },
      traceScorePreparationBlocks: startup?.traceScorePreparationBlocks,
      renderPreparation: validWarmup ? {
        calls: warmup.zero_frame_calls,
        frames: requested === "zero" ? 0 : warmupFrames,
        blockFrames: warmup.draw_block_frames,
        distributed,
        firstQuantumOffset,
      } : undefined,
    };
    const recordTract = recording?.includeTract;
    let silentLead: Awaited<ReturnType<typeof prepareSongSilentLead>> | undefined;
    if (startup?.silentLeadQuanta !== undefined) {
      registration ??= registerFixedWorklet(context, mark, traceEvaluation);
      if (startup.parallelSilentLeadRegistration) {
        await Promise.all([registration, registerSongSilentLead(context, mark)]);
      } else {
        await registration;
      }
      signal.throwIfAborted();
      mark?.("silent_lead_start");
      if (!startup.parallelSilentLeadRegistration) await registerSongSilentLead(context, mark);
      mark?.("silent_lead_connect");
      silentLead = await prepareSongSilentLead(context, realtime.quantum,
        { quanta: startup.silentLeadQuanta, traceInput: startup.silentLeadTraceInput,
          traceNative: startup.silentLeadTraceNative }, signal);
      mark?.("silent_lead_ready");
    }
    try {
      const { pcm, report, clip } = await captureWorklet(context,
        { module, voice: initialVoice, frames, observationStride, mode: score, realtime,
          ...(recordTract && { tractStride, tractGrid: true }) }, signal,
        { recording: recording && { ...recording, notes: details.song.plan.notes, frames }, startupMark: mark, registration,
          traceEvaluation });
      if (!pcm) throw new Error("実時間WorkletのPCMがありません");
      return { pcm, report: { ...report, ...details, ...(clip && { recording: clip.observation }),
        ...(trace && { startupTrace: { dictionaryState, parallelRegistration, registerBeforeResume, marks: trace.marks } }),
        ...(silentLead && { silentLead: silentLead.observation }) },
        replayCase, video: clip?.file };
    } finally {
      silentLead?.close();
    }
  }, { trace, parallelRegistration, registerBeforeResume, traceEvaluation });
}

function songDictionary(input: SongInput) {
  return input.lyrics === undefined ? undefined : loadDictionary();
}

function prepareSongVoice(module: WebAssembly.Module, dictionary: Uint8Array | undefined,
  voice: SongVoiceInput, input: SongInput, mark?: StartupMark) {
  const { turbulence, warm_up_frames, render_end_seconds, ...voiceInput } = voice;
  const { base_pitch_hz, pitch_drift_cents, period_jitter, amplitude_shimmer } = voice.voice;
  const { song, gestures, score, initialPitchHz } = planSong(module, input, dictionary, voice.body, mark);
  if (turbulence) {
    score.noiseScale = turbulence.scale;
    if (turbulence.glottis_gain_multiplier !== undefined || turbulence.constriction_gain_multiplier !== undefined
      || turbulence.teeth_lowpass_floor_hz !== undefined) {
      score.turbulence = turbulence;
    }
  }
  if (base_pitch_hz !== undefined) score.basePitchHz = base_pitch_hz;
  if ([warm_up_frames, pitch_drift_cents, period_jitter, amplitude_shimmer].some((value) => value !== undefined)) {
    score.sourcePreparation = { warmUpFrames: warm_up_frames ?? 0, pitchDriftCents: pitch_drift_cents ?? 0,
      periodJitter: period_jitter ?? 0, amplitudeShimmer: amplitude_shimmer ?? 0 };
  }
  const frames = Math.round((render_end_seconds ?? song.plan.render_end_seconds) * voice.voice.output_sample_rate_hz);
  const initialVoice = { ...voiceInput, voice: { ...voice.voice, f0_hz: initialPitchHz } };
  const { vibrato_cents, ...notation } = input;
  const replayCase = {
    id: "worklet-song-replay",
    upstream_revision: songExperiment.upstream_revision,
    song_voice: {
      body: voice.body, posture: voice.posture, voice: voice.voice,
      internal_sample_rate_hz: voice.fixed_airway.sample_rate_hz,
      warm_up_frames, render_end_seconds,
      score: { ...notation, ...(input.syllables !== undefined && { dictionary: false }) },
      vibrato_cents, turbulence: turbulence ?? { scale: score.noiseScale ?? 1 },
    },
  };
  return { details: { input, song, gestures, body: voice.body }, score, frames, initialVoice, replayCase };
}

async function renderOffline(
  module: WebAssembly.Module,
  voice: FixedVoiceInput,
  frames: number,
  observationStride: number,
  mode?: ProcessorOptions["mode"],
  tractStride?: number,
  tractGrid?: boolean,
) {
  const context = new OfflineAudioContext(1, frames, voice.voice.output_sample_rate_hz);
  const { audio, report } = await captureWorklet(context, {
    module, voice, frames, observationStride, mode, tractStride, tractGrid,
  });
  if (!audio) throw new Error("オフラインの音声バッファがありません");
  return { audio, report };
}

async function captureWorklet(
  context: OfflineAudioContext | AudioContext, options: ProcessorOptions, signal?: AbortSignal,
  controls?: { beat?: BeatControls; recording?: SongRecordingOptions; onTract?: (sample: LiveTractSample) => void;
    startupMark?: StartupMark; registration?: Promise<void>; traceEvaluation?: boolean },
) {
  const { frames, voice, mode, observationStride, tractStride, realtime } = options;
  if (![frames, observationStride, tractStride ?? 1].every((n) => Number.isSafeInteger(n) && n > 0)) {
    throw new Error("レンダー長と観測間隔は正の整数で指定してください");
  }
  if (realtime && (!Number.isSafeInteger(realtime.quantum) || realtime.quantum < 1
      || !Number.isSafeInteger(realtime.leadFrames) || realtime.leadFrames < 0
      || realtime.leadFrames % realtime.quantum !== 0)) {
    throw new Error("実時間の開始待ちを描画量子の整数倍で指定してください");
  }
  const outputRate = voice.voice.output_sample_rate_hz;
  const columns = [realtime ? "output_frame" : "context_frame", ...observationFields(mode)];
  const mark = controls?.startupMark;
  await (controls?.registration ?? registerFixedWorklet(context, mark, controls?.traceEvaluation));
  const tractRecording = controls?.recording?.includeTract ? await import("./recorded-tract") : undefined;
  signal?.throwIfAborted();
  // 実時間の処理は接続前にも進みうるため、準備はノードを作る前に済ませる。
  const recordedTract: RecordedTract | undefined = tractRecording && new tractRecording.RecordedTract();
  let node: AudioWorkletNode;
  try {
    mark?.("node_start");
    node = new AudioWorkletNode(context, PROCESSOR_NAME, {
      numberOfInputs: 0,
      numberOfOutputs: 1,
      outputChannelCount: [1],
      processorOptions: options,
    });
    mark?.("node_ready");
  } catch (failure) {
    recordedTract?.close();
    throw failure;
  }
  let timer: number | undefined;
  let readyRate: number | undefined;
  let moduleTiming: WorkletModuleTiming | undefined;
  let scoreConstruction: Extract<WorkletMessage, { type: "ready" }>["scoreConstruction"];
  let abort: (() => void) | undefined;
  let recorder: SongRecording | undefined;
  const sendBeat = (command: BeatCommand) => node.port.postMessage(command);
  const measured = new Promise<Extract<WorkletMessage, { type: "complete" }>>((resolve, reject) => {
    const durationMs = realtime ? 1000 * frames / outputRate : 0;
    timer = window.setTimeout(() => reject(new Error("Workletの完了通知を受信できませんでした")), 15000 + durationMs);
    if (signal) {
      abort = () => {
        recorder?.cancel();
        reject(signal.reason);
      };
      signal.addEventListener("abort", abort, { once: true });
    }
    node.onprocessorerror = () => reject(new Error("AudioWorkletの処理が停止しました"));
    node.port.onmessage = ({ data }: MessageEvent<WorkletMessage>) => {
      if (data.type === "ready") {
        readyRate = data.sampleRate;
        scoreConstruction = data.scoreConstruction;
        if (data.moduleTiming) {
          mark?.("worklet_ready_received");
          moduleTiming = data.moduleTiming;
        }
      }
      else if (data.type === "scheduled") recorder?.schedule(data.contextFrame);
      else if (data.type === "error") reject(new Error(data.message));
      else if (data.type === "beat-progress") controls?.beat?.(data, sendBeat);
      else if (data.type === "tract-frame") {
        try {
          if (!signal?.aborted) {
            const sample = unpackLiveTract(data);
            controls?.onTract?.(sample);
            recorder?.observeTract(sample);
          }
        } catch (failure) {
          reject(failure);
        } finally {
          const returned: WorkletCommand = { type: "return-tract-buffer", values: data.values };
          node.port.postMessage(returned, [data.values.buffer]);
        }
      }
      else if (readyRate !== outputRate) reject(new Error("Workletの準備通知または出力レートが不正です"));
      else resolve(data);
    };
  });
  try {
    const began = performance.now();
    if (controls?.recording && context instanceof AudioContext) {
      recorder = new SongRecording(context, node, controls.recording, recordedTract);
    }
    mark?.("connect_start");
    node.connect(context.destination);
    mark?.("connected");
    const [audio, { observations, tract, glottal, radiation, realtime: live, scorePreparationTrace, type: _type, ...stats }] =
      await Promise.all([context instanceof OfflineAudioContext ? context.startRendering() : undefined, measured]);
    let realtimeReport;
    let clip;
    if (live && context instanceof AudioContext) {
      const { pcm: _pcm, timing, ...clock } = live;
      realtimeReport = {
        ...clock, contextState: context.state, baseLatencySeconds: context.baseLatency,
        outputLatencySeconds: context.outputLatency, elapsedWallMs: performance.now() - began,
        columns: REALTIME_SPEECH_COLUMNS, blocks: unpackRows(timing, REALTIME_SPEECH_COLUMNS.length),
      };
      if (recorder) clip = await recorder.finish(clock.scheduledContextFrame, signal);
    }
    return {
      audio, pcm: live?.pcm, clip,
      report: {
        sampleRate: context.sampleRate,
        outputChannels: audio?.numberOfChannels ?? 1,
        outputFrames: audio?.length ?? live?.pcm.length ?? 0,
        workletSampleRate: readyRate,
        columns,
        ...stats,
        ...(moduleTiming && { workletModuleTiming: moduleTiming }),
        ...(scoreConstruction && { scoreConstruction }),
        ...(scorePreparationTrace && { scorePreparationTrace: { clock: scorePreparationTrace.clock,
          omittedCallbacks: scorePreparationTrace.omittedCallbacks, columns: SCORE_PREPARATION_COLUMNS,
          blocks: unpackRows(scorePreparationTrace.values, SCORE_PREPARATION_COLUMNS.length),
        } }),
        observations: unpackRows(observations, columns.length),
        ...(tract && { tract: unpackTract(tract) }),
        ...(glottal && { glottal: { columns: GLOTTAL_COLUMNS, values: Array.from(glottal) } }),
        ...(radiation && { radiation: { columns: RADIATION_COLUMNS, values: Array.from(radiation) } }),
        ...(realtimeReport && { realtime: realtimeReport }),
      },
    };
  } finally {
    recorder?.cancel();
    recordedTract?.close();
    window.clearTimeout(timer);
    if (abort) signal?.removeEventListener("abort", abort);
    node.onprocessorerror = null;
    node.port.onmessage = null;
    node.port.close();
    node.disconnect();
  }
}

function unpackTract(tract: NonNullable<Extract<WorkletMessage, { type: "complete" }>["tract"]>): TractProfile {
  const cells = tract.counts[0] + tract.counts[1];
  const geometryEnd = 1 + TRACT_GEOMETRY_WORDS * cells;
  const rows = unpackRows(tract.rows, geometryEnd + TRACT_ACOUSTIC_WORDS * cells);
  const grid = tract.grid && unpackTractGrid(tract.grid, rows);
  return {
    counts: tract.counts,
    rows: rows.map((row) => row.slice(0, geometryEnd)),
    acoustics: {
      columns: ["frame", "pressure_dyn_cm2", "outward_flow_cm3_s"],
      rows: rows.map((row) => [row[0], ...row.slice(geometryEnd)]),
    },
    ...(grid && { grid }),
  };
}

function unpackTractGrid(grid: { rowWords: number; rows: Float64Array }, cells: number[][]) {
  const { rowWords, rows } = grid;
  if (rows.length !== cells.length * rowWords) throw new Error("声道測定線の観測回数が一致しません");
  const frames = cells.map(([cellFrame], i) => {
    const offset = i * rowWords;
    const frame = rows[offset];
    if (frame !== cellFrame) throw new Error("声道測定線の観測フレームが音響セルと一致しません");
    return { frame, rows: gridRows(rows, offset + 1, rowWords - 1) };
  });
  return { columns: AREA_GRID_COLUMNS, frames };
}

function unpackLiveTract({ counts, frame, contextFrame, values }: LiveTractMessage): LiveTractSample {
  const cells = counts[0] + counts[1];
  const gridOffset = (TRACT_GEOMETRY_WORDS + TRACT_ACOUSTIC_WORDS) * cells;
  return {
    contextFrame,
    lipMinimum: values[TRACT_GEOMETRY_WORDS * cells - 1],
    grid: { frame, rows: gridRows(values, gridOffset, values.length - gridOffset) },
  };
}

function gridRows(data: Float64Array, offset: number, width: number): number[][] {
  const words = AREA_GRID_COLUMNS.length;
  const count = data[offset];
  if (!Number.isSafeInteger(count) || count < 2 || count * words + 1 > width) {
    throw new Error("声道測定線の観測行数が不正です");
  }
  return unpackRows(data.subarray(offset + 1, offset + 1 + count * words), words);
}

function unpackRows(data: Float64Array, width: number): number[][] {
  const rows: number[][] = [];
  for (let i = 0; i < data.length; i += width) {
    rows.push(Array.from(data.subarray(i, i + width)));
  }
  return rows;
}

// モノラルIEEE Float WAV。実数のビットを変えずに保存する。
export function floatWave(pcm: Float32Array, sampleRate: number): Blob {
  const bytes = pcm.length * 4;
  const view = new DataView(new ArrayBuffer(58 + bytes));
  const tag = (at: number, text: string) => {
    for (let i = 0; i < text.length; i++) view.setUint8(at + i, text.charCodeAt(i));
  };
  tag(0, "RIFF");
  view.setUint32(4, bytes + 50, true);
  tag(8, "WAVEfmt ");
  view.setUint32(16, 18, true);
  view.setUint16(20, 3, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 4, true);
  view.setUint16(32, 4, true);
  view.setUint16(34, 32, true);
  tag(38, "fact");
  view.setUint32(42, 4, true);
  view.setUint32(46, pcm.length, true);
  tag(50, "data");
  view.setUint32(54, bytes, true);
  for (let frame = 0; frame < pcm.length; frame++) view.setFloat32(58 + frame * 4, pcm[frame], true);
  return new Blob([view.buffer], { type: "audio/wav" });
}
