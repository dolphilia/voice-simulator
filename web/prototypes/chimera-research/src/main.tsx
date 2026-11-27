import type { CreatureMidiInput } from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/creature-midi";
import { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { DuetPage } from "./duet-page";
import fixedCase from "../../../../research/experiments/chimera-rebuild/cases/vowel-voice-i.json";
import experiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-fixed-voice.json";
import liveExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-realtime-voice.json";
import midiExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-midi-voice.json";
import live44100Experiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-realtime-voice-44100.json";
import live32000Experiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-realtime-voice-32000.json";
import live16000Experiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-realtime-voice-16000.json";
import live96000Experiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-realtime-voice-96000.json";
import speechFixture from "../../../../research/experiments/chimera-rebuild/cases/bilabial-p.json";
import speechExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-ipa-voice.json";
import englishFixture from "../../../../research/experiments/chimera-rebuild/cases/english-mom-pop.json";
import englishExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-english-voice.json";
import songFixture from "../../../../research/experiments/chimera-rebuild/cases/song-voice-long.json";
import fastSongFixture from "../../../../research/experiments/chimera-rebuild/cases/song-voice-fast.json";
import preparedSongFixture from "../../../../research/experiments/chimera-rebuild/cases/worklet-song-prepared-source.json";
import songExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-song-voice.json";
import beatFixture from "../../../../research/experiments/chimera-rebuild/cases/beatbox-pattern-hum.json";
import beatExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-beatbox-pattern.json";
import liveBeatExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-live-beatbox.json";
import songbirdSource from "../../../../research/experiments/chimera-rebuild/cases/songbird-sustain-pcm.json";
import sealMidiCallExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-midi-seal-call.json";
import sealMidiExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-midi-seal.json";
import songbirdMidiExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-midi-songbird.json";
import songbirdMidiCallExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-midi-songbird-call.json";
import songbirdExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-songbird-sustain.json";
import fluteSource from "../../../../research/experiments/chimera-rebuild/cases/songbird-flute.json";
import fluteExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-songbird-flute.json";
import callsSource from "../../../../research/experiments/chimera-rebuild/cases/songbird-calls.json";
import trillExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-songbird-trill.json";
import trillObservation from "../../../../research/experiments/chimera-rebuild/cases/worklet-songbird-trill-observation.json";
import chirpsExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-songbird-chirps.json";
import buzzExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-songbird-buzz.json";
import switchExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-songbird-switch.json";
import sealSource from "../../../../research/experiments/chimera-rebuild/cases/seal-sustain-pcm.json";
import sealExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-seal-sustain.json";
import sealTrillSource from "../../../../research/experiments/chimera-rebuild/cases/seal-trill.json";
import sealTrillExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-seal-trill.json";
import sealZapSource from "../../../../research/experiments/chimera-rebuild/cases/seal-zap.json";
import sealZapExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-seal-zap.json";
import sealWhistleSource from "../../../../research/experiments/chimera-rebuild/cases/seal-whistle.json";
import sealWhistleExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-seal-whistle.json";
import sealChugSource from "../../../../research/experiments/chimera-rebuild/cases/seal-chug-v2.json";
import sealChugExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-seal-chug.json";
import alligatorMidiExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-midi-alligator.json";
import alligatorMidiCallExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-midi-alligator-call.json";
import alligatorSource from "../../../../research/experiments/chimera-rebuild/cases/alligator-fixed-voice-v2.json";
import alligatorExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-alligator-fixed-voice.json";
import alligatorBellowSource from "../../../../research/experiments/chimera-rebuild/cases/alligator-bellow.json";
import alligatorBellowExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-alligator-bellow.json";
import alligatorGrowlSource from "../../../../research/experiments/chimera-rebuild/cases/alligator-growl.json";
import alligatorGrowlExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-alligator-growl.json";
import alligatorHissSource from "../../../../research/experiments/chimera-rebuild/cases/alligator-hiss.json";
import alligatorHissExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-alligator-hiss.json";
import alligatorDanceSource from "../../../../research/experiments/chimera-rebuild/cases/alligator-dance.json";
import alligatorDanceExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-alligator-dance.json";
import elephantSource from "../../../../research/experiments/chimera-rebuild/cases/elephant-fixed-voice.json";
import elephantMidiExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-midi-elephant.json";
import elephantMidiCallExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-midi-elephant-call.json";
import elephantExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-elephant-fixed-voice.json";
import elephantRumbleSource from "../../../../research/experiments/chimera-rebuild/cases/elephant-rumble.json";
import elephantRumbleExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-elephant-rumble.json";
import elephantTrumpetSource from "../../../../research/experiments/chimera-rebuild/cases/elephant-trumpet.json";
import elephantTrumpetExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-elephant-trumpet.json";
import elephantSqueakSource from "../../../../research/experiments/chimera-rebuild/cases/elephant-squeak.json";
import elephantSqueakExperiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-elephant-squeak.json";
import dictionaryLicenseUrl from "../../../../research/experiments/chimera-rebuild/data/CMUDICT-LICENSE.txt?url&no-inline";
import mandarinLicenseUrl from "../../../../research/experiments/chimera-rebuild/data/MANDARIN-PINYIN-LICENSE.txt?url&no-inline";
import type { BeatCommand, FixedVoiceInput, ManualTargets, VoiceBodyName } from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/fixed-voice";
import type { SongInput } from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/planning";
import type { SongbirdInput } from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/songbird";
import type { BeatProgress, LiveTractSample, SongSilentLeadQuanta } from "./fixed-worklet-types";
import { IpaTimeline } from "./ipa-timeline";
import { startRealtimeVoice } from "./realtime-fixed-voice";
import {
  renderAlligator, renderElephant, renderSeal, renderSongbird,
  type AlligatorReplayCase, type ElephantReplayCase, type SealReplayCase, type SongbirdReplayCase,
} from "./render-creature";
import {
  floatWave, renderBeatPattern, renderEnglishVoice, renderFixedVoice, renderIpaVoice, renderRealtimeEnglishVoice, renderRealtimeIpaVoice,
  renderRealtimeBeatPattern, renderRealtimeSongVoice, renderSongVoice,
  type SpeechVoiceInput,
} from "./render-fixed-voice";
import "./style.css";
import { useMidiConnection } from "./midi-connection";
import { Tract3DPanel } from "./tract-3d";
import { SpeechTract3D } from "./speech-tract-3d";
import { songRecordingType } from "./song-recording";
import { readEnglishSpeechCase } from "./english-speech-case";
import { RadiationScope } from "./radiation-scope";

type CaptureReport = { sampleRate: number; outputFrames: number; observations: number[][] };

type Capture<Report extends CaptureReport = CaptureReport> = {
  pcm: Float32Array;
  report: Report;
  caseId?: string;
  replayCase?: Awaited<ReturnType<typeof startRealtimeVoice>["finished"]>["replayCase"] | Awaited<ReturnType<typeof renderRealtimeBeatPattern>>["replayCase"]
    | Awaited<ReturnType<typeof renderEnglishVoice | typeof renderSongVoice>>["replayCase"]
    | FixedVoiceInput | SongbirdReplayCase | SealReplayCase | AlligatorReplayCase | ElephantReplayCase;
};

function normalizePose(posture: typeof fixedCase.posture): FixedVoiceInput["posture"] {
  return { ...posture,
    tongue_body_cm: [posture.tongue_body_cm[0], posture.tongue_body_cm[1]],
    tongue_tip_cm: [posture.tongue_tip_cm[0], posture.tongue_tip_cm[1]],
  };
}

function fixedInput(): FixedVoiceInput {
  if (fixedCase.body !== "male") throw new Error("ケースの体型に対応していません");
  return { ...fixedCase, body: fixedCase.body, posture: normalizePose(fixedCase.posture) };
}

function jsonUrl(data: object) {
  return URL.createObjectURL(new Blob(
    [JSON.stringify(data, null, 2) + "\n"], { type: "application/json" },
  ));
}

function CaptureOutput({ capture, name, caseId = fixedCase.id }: {
  capture: Capture; name: string; caseId?: string;
}) {
  const [urls, setUrls] = useState<{ wave: string; report: string; replay?: string }>();
  useEffect(() => {
    const wave = URL.createObjectURL(floatWave(capture.pcm, capture.report.sampleRate));
    const report = jsonUrl({ caseId, ...capture.report });
    const replay = capture.replayCase && jsonUrl(capture.replayCase);
    setUrls({ wave, report, replay });
    return () => {
      URL.revokeObjectURL(wave);
      URL.revokeObjectURL(report);
      if (replay) URL.revokeObjectURL(replay);
    };
  }, [capture, caseId]);
  const { outputFrames, sampleRate, observations } = capture.report;
  return (
    <section aria-labelledby={`${name}-title`}>
      <h2 id={`${name}-title`}>レンダー結果</h2>
      <dl>
        <div><dt>出力レート</dt><dd>{sampleRate.toLocaleString("ja-JP")} Hz</dd></div>
        <div><dt>PCMフレーム</dt><dd>{outputFrames.toLocaleString("ja-JP")}</dd></div>
        <div><dt>観測点</dt><dd>{observations.length.toLocaleString("ja-JP")}</dd></div>
        <div><dt>長さ</dt><dd>{(outputFrames / sampleRate).toFixed(3)} 秒</dd></div>
      </dl>
      {urls && <>
        <audio controls aria-label="レンダー音声の試聴" src={urls.wave} />
        <div className="downloads">
          <a href={urls.wave} download={`${name}.wav`}>WAVを保存</a>
          <a href={urls.report} download={`${name}.json`}>観測JSONを保存</a>
          {urls.replay && <a href={urls.replay} download={`${name}-case.json`}>再実行ケースを保存</a>}
        </div>
      </>}
    </section>
  );
}

const manualAxes = [
  { label: "舌体 X（cm）", min: 1, max: 4.8 },
  { label: "舌体 Y（cm）", min: 4.8, max: 9.2 },
  { label: "口唇開度（cm）", min: -0.4, max: 2.4 },
] as const;

const fixedLiveExperiments = [
  liveExperiment, live44100Experiment, live32000Experiment, live16000Experiment, live96000Experiment,
];

function RealtimePanel({ manual = false }: { manual?: boolean }) {
  const session = useRef<ReturnType<typeof startRealtimeVoice>>(undefined);
  const [phase, setPhase] = useState<"idle" | "starting" | "voicing" | "release">("idle");
  const [capture, setCapture] = useState<Capture>();
  const [error, setError] = useState("");
  const [body, setBody] = useState(defaultBodySelection);
  const initialTargets: ManualTargets = [
    fixedCase.posture.tongue_body_cm[0], fixedCase.posture.tongue_body_cm[1], fixedCase.posture.lip_aperture_cm,
  ];
  const [targets, setTargets] = useState(initialTargets);
  const currentTargets = useRef(initialTargets);
  const titleId = manual ? "manual-title" : "realtime-title";
  const [outputRate, setOutputRate] = useState(liveExperiment.measurement.output_rate_hz);
  const settings = (fixedLiveExperiments.find(({ measurement }) => measurement.output_rate_hz === outputRate)
    ?? liveExperiment).measurement;
  async function start() {
    setPhase("starting");
    setError("");
    setCapture(undefined);
    currentTargets.current = initialTargets;
    setTargets(initialTargets);
    setBody(defaultBodySelection);
    try {
      const input = fixedInput();
      session.current = startRealtimeVoice({
        ...input,
        fixed_airway: { ...input.fixed_airway, sample_rate_hz: settings.internal_rate_hz },
        voice: { ...input.voice, output_sample_rate_hz: settings.output_rate_hz },
      }, {
        quantum: settings.expected_quantum_frames,
        preRoll: settings.pre_roll_frames,
        maximumVoiced: settings.maximum_voiced_frames,
        release: settings.release_frames,
        manual,
      }, setPhase);
      setCapture(await session.current.finished);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      session.current = undefined;
      setPhase("idle");
    }
  }
  function stop() {
    setPhase("release");
    session.current?.stop();
  }
  function changeTarget(index: number, value: number) {
    const next: ManualTargets = [...currentTargets.current];
    next[index] = value;
    currentTargets.current = next;
    setTargets(next);
    session.current?.setManualTargets(next);
  }
  return (
    <section aria-labelledby={titleId}>
      <h2 id={titleId}>{manual ? "舌と唇の操作" : "実時間の発声"}</h2>
      <p>最大{(settings.maximum_voiced_frames / settings.output_rate_hz)
        .toLocaleString("ja-JP", { maximumFractionDigits: 3 })}秒発声します。停止後の減衰まで保存できます。</p>
      <div className="controls">
        {!manual && <div>
          <label htmlFor="realtime-output-rate">出力サンプルレート</label>{" "}
          <select id="realtime-output-rate" value={outputRate} disabled={phase !== "idle"}
            onChange={(event) => setOutputRate(Number(event.target.value))}>
            {fixedLiveExperiments.map(({ measurement: { output_rate_hz: rate } }) =>
              <option key={rate} value={rate}>{rate.toLocaleString("ja-JP")} Hz</option>)}
          </select>
        </div>}
        <button type="button" onClick={start} disabled={phase !== "idle"}>発声を開始</button>
        <button type="button" onClick={stop} disabled={phase !== "voicing"}>発声を停止</button>
      </div>
      {manual && <div className="speech-voice-controls">
        <VoiceBodyControls selection={body} disabled={phase !== "voicing"}
          onChange={(selection) => {
            setBody(selection);
            session.current?.setManualBody(selectedBody(selection));
          }} />
      </div>}
      {manual && <div className="articulation-controls">
        {manualAxes.map(({ label, min, max }, index) => (
          <label key={label}>
            <span>{label}</span><span aria-hidden="true">{targets[index].toFixed(3)}</span>
            <input type="range" aria-label={label} min={min} max={max} step={0.001}
              disabled={phase !== "voicing"} value={targets[index]}
              onChange={(event) => changeTarget(index, event.currentTarget.valueAsNumber)} />
          </label>
        ))}
      </div>}
      {(phase !== "idle" || capture) && <p role="status">{
        phase === "starting" ? "準備中" : phase === "voicing" ? "発声中" :
        phase === "release" ? "減衰を計測中" : "実時間計測完了"
      }</p>}
      {error && <p role="alert">実時間の発声に失敗しました。{error}</p>}
      {capture && <CaptureOutput capture={capture} name={manual ? "worklet-articulation" : "worklet-live-i"} />}
    </section>
  );
}

function MidiPanel() {
  const session = useRef<ReturnType<typeof startRealtimeVoice>>(undefined);
  const held = useRef<number | null>(null);
  const [note, setNote] = useState<number | null>(null);
  const [phase, setPhase] = useState<"idle" | "starting" | "voicing" | "release">("idle");
  const [capture, setCapture] = useState<Capture>();
  const [sing, setSing] = useState(false);
  const [lyrics, setLyrics] = useState("la ma -");
  const [error, setError] = useState("");
  const supported = typeof navigator.requestMIDIAccess === "function";
  const { inputs, connecting, toggle } = useMidiConnection(changeNote,
    (message) => setError(message ? "MIDI入力へのアクセスを取得できませんでした" : ""),
    (key) => session.current?.setSongKey(key));

  useEffect(() => () => {
    session.current?.stop();
  }, []);

  function changeNote(next: number | null) {
    held.current = next;
    setNote(next);
    session.current?.setMidiNote(next);
  }

  async function start() {
    const { expected_quantum_frames, pre_roll_frames, release_frames } = liveExperiment.measurement;
    setPhase("starting");
    setError("");
    setCapture(undefined);
    try {
      const input = sing ? {
        ...fixedInput(), posture: normalizePose(songFixture.song_voice.posture),
        voice: { ...songFixture.song_voice.voice, f0_hz: 110 },
      } : fixedInput();
      session.current = startRealtimeVoice(input, {
        quantum: expected_quantum_frames,
        preRoll: pre_roll_frames,
        maximumVoiced: midiExperiment.measurement.maximum_voiced_frames,
        release: release_frames,
        midi: !sing,
      }, setPhase, sing ? { lyrics, vibratoCents: 0 } : undefined);
      session.current.setMidiNote(held.current);
      setCapture(await session.current.finished);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      session.current = undefined;
      setPhase("idle");
    }
  }

  return <section aria-labelledby="midi-voice-title">
    <h2 id="midi-voice-title">MIDI鍵盤の発声</h2>
    {supported ? <>
      <div className="controls">
        <button type="button" onClick={toggle}>{inputs || connecting ? "MIDIを切断" : "MIDIを接続"}</button>
        <button type="button" onClick={start} disabled={!inputs?.length || phase !== "idle"}>
          MIDI計測を開始
        </button>
        <button type="button" onClick={() => session.current?.stop()} disabled={phase !== "voicing"}>
          MIDI計測を停止
        </button>
      </div>
      <label><input type="checkbox" checked={sing} disabled={phase !== "idle"} onChange={(e) => {
        setSing(e.target.checked);
        setCapture(undefined);
      }} />MIDIで歌唱する</label>
      {sing && <label>鍵盤歌唱の歌詞
        <input value={lyrics} disabled={phase !== "idle"} onChange={(e) => setLyrics(e.target.value)} />
      </label>}
      <p data-midi-inputs>{inputs ? inputs.join("、") || "MIDI入力なし"
        : connecting ? "MIDI接続を待っています" : "MIDI未接続"}</p>
      <output aria-label="保持中のMIDI音">{note === null ? "なし" : note}</output>
    </> : <p>この環境ではWeb MIDIを使えません。</p>}
    {(phase !== "idle" || capture) && <p role="status">{
      phase === "starting" ? "準備中" : phase === "voicing" ? "MIDI計測中"
        : phase === "release" ? "減衰を計測中" : "実時間計測完了"}</p>}
    {error && <p role="alert">{error}</p>}
    {capture && <CaptureOutput capture={capture} name={sing ? "worklet-midi-song" : "worklet-midi-voice"}
      caseId={sing ? "worklet-midi-song" : midiExperiment.id} />}
  </section>;
}

type BodySelection = { name: VoiceBodyName | "mix"; female: string; child: string };
const defaultBodySelection: BodySelection = { name: "male", female: "0.4", child: "0.3" };

function selectedBody(selection: BodySelection): FixedVoiceInput["body"] {
  return selection.name === "mix" ? { female: Number(selection.female), child: Number(selection.child) } : selection.name;
}

function VoiceBodyControls({ selection, onChange, disabled }: {
  selection: BodySelection; onChange: (selection: BodySelection) => void; disabled: boolean;
}) {
  return <>
    <label>体型
      <select value={selection.name} disabled={disabled}
        onChange={(event) => onChange({ ...selection, name: event.target.value as BodySelection["name"] })}>
        <option value="male">成人男性</option>
        <option value="female">成人女性</option>
        <option value="child">子ども</option>
        <option value="mix">混合</option>
      </select>
    </label>
    {selection.name === "mix" && <>
      <label>成人内の女性比
        <input type="number" min="0" max="1" step="any" required value={selection.female} disabled={disabled}
          onChange={(event) => onChange({ ...selection, female: event.target.value })} />
      </label>
      <label>子ども比
        <input type="number" min="0" max="1" step="any" required value={selection.child} disabled={disabled}
          onChange={(event) => onChange({ ...selection, child: event.target.value })} />
      </label>
    </>}
  </>;
}

type ImportedEnglishCase = ReturnType<typeof readEnglishSpeechCase> & { caseId: string };

function SpeechPanel({ english = false }: { english?: boolean }) {
  const source = english ? englishFixture : speechFixture;
  const fixture = source.speech_voice;
  const plan = english ? englishExperiment : speechExperiment;
  const name = english ? "english" : "ipa";
  const [text, setText] = useState(fixture.input.text);
  const [body, setBody] = useState(defaultBodySelection);
  const [pitch, setPitch] = useState("");
  const [tractGrid, setTractGrid] = useState(false);
  const [liveTract, setLiveTract] = useState<LiveTractSample>();
  const [liveViewPrepared, setLiveViewPrepared] = useState(false);
  const [importedCase, setImportedCase] = useState<ImportedEnglishCase>();
  type SpeechReport = Awaited<ReturnType<typeof renderEnglishVoice | typeof renderIpaVoice>>["report"];
  const [capture, setCapture] = useState<Capture<SpeechReport>>();
  const [pending, setPending] = useState<"offline" | "live">();
  const realtimeAbort = useRef<AbortController>(undefined);
  const [error, setError] = useState("");
  useEffect(() => () => realtimeAbort.current?.abort(), []);

  async function run(realtime = false, caseInput?: File | ImportedEnglishCase) {
    const abort = realtime ? new AbortController() : undefined;
    realtimeAbort.current = abort;
    setPending(realtime ? "live" : "offline");
    setCapture(undefined);
    setLiveTract(undefined);
    setError("");
    let animation: number | undefined;
    let latest: LiveTractSample | undefined;
    const displayTract = (sample: LiveTractSample) => {
      latest = sample;
      animation ??= requestAnimationFrame(() => {
        animation = undefined;
        if (!abort?.signal.aborted) setLiveTract(latest);
      });
    };
    try {
      if (caseInput) {
        let imported: ImportedEnglishCase;
        if (caseInput instanceof File) {
          setImportedCase(undefined);
          const parsed = readEnglishSpeechCase(JSON.parse(await caseInput.text()));
          imported = { ...parsed, caseId: parsed.caseId ?? caseInput.name };
        } else {
          imported = caseInput;
        }
        const { config, text, rate, start, inputId, caseId } = imported;
        const stride = plan.measurement.observation_stride_frames;
        if (abort) {
          const query = new URLSearchParams(location.search);
          const result = await renderRealtimeEnglishVoice(config, text, rate, stride, abort.signal, start, inputId, {
            tracePhases: query.get("speechRenderPhases") === "1",
            traceWasmCore: query.get("speechWasmCore") === "1",
            preparation: query.get("speechRenderPreparation") ?? undefined,
            delayOneQuantum: query.get("speechDelayOneQuantum") === "1",
          });
          setCapture({ ...result, caseId });
        } else {
          const { audio, report, replayCase } = await renderEnglishVoice(config, text, rate, stride, start, inputId);
          setImportedCase(imported);
          setCapture({ pcm: audio.getChannelData(0), report, replayCase, caseId });
        }
        return;
      }
      const { f0_hz: _fixturePitch, ...voice } = fixture.voice;
      const input: SpeechVoiceInput = {
        body: selectedBody(body),
        posture: normalizePose(fixture.posture),
        voice: { ...voice, ...(pitch !== "" && { f0_hz: Number(pitch) }) },
        fixed_airway: { sample_rate_hz: fixture.internal_sample_rate_hz, impulse_volume_cm3: 0, sample_count: 0 },
      };
      if (abort) {
        setCapture(await renderRealtimeIpaVoice(input, text, fixture.input.rate,
          plan.measurement.observation_stride_frames, abort.signal, tractGrid ? displayTract : undefined));
      } else {
        const stride = plan.measurement.observation_stride_frames;
        const result = english
          ? await renderEnglishVoice(input, text, fixture.input.rate, stride)
          : await renderIpaVoice(input, text, fixture.input.rate, stride, undefined, tractGrid);
        setCapture({ pcm: result.audio.getChannelData(0), report: result.report, replayCase: result.replayCase });
      }
    } catch (failure) {
      if (!abort?.signal.aborted) setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      if (animation !== undefined) cancelAnimationFrame(animation);
      setLiveTract(undefined);
      realtimeAbort.current = undefined;
      setPending(undefined);
    }
  }
  return (
    <section aria-labelledby={`${name}-title`}>
      <h2 id={`${name}-title`}>{english ? "英語発話" : "IPA発話"}</h2>
      <form className="ipa-form" onSubmit={(event) => { event.preventDefault(); void run(); }}>
        <label htmlFor={`${name}-input`}>{english ? "英語テキスト" : "IPA"}</label>
        <input id={`${name}-input`} value={text} onChange={(event) => setText(event.target.value)}
          spellCheck={false} autoCapitalize="none" disabled={Boolean(pending)} />
        <div className="speech-voice-controls">
          <VoiceBodyControls selection={body} onChange={setBody} disabled={Boolean(pending)} />
          <label>基準F0（Hz）
            <input type="number" min="0" step="any" placeholder="体型の既定値" value={pitch}
              onChange={(event) => setPitch(event.target.value)} disabled={Boolean(pending)} />
          </label>
        </div>
        {!english && <label className="tract-grid-option">
          <input type="checkbox" checked={tractGrid} disabled={Boolean(pending)}
            onChange={(event) => {
              setLiveViewPrepared(false);
              setTractGrid(event.currentTarget.checked);
            }} />
          三次元断面を観測する
        </label>}
        <button type="submit" disabled={Boolean(pending) || !text.trim()}>{english ? "英語をレンダー" : "IPAをレンダー"}</button>
        {!english && <button type="button" disabled={Boolean(pending) || !text.trim() || (tractGrid && !liveViewPrepared)}
          onClick={(event) => { if (event.currentTarget.form?.reportValidity()) void run(true); }}>IPAを実時間で発声</button>}
        {pending === "live" && <button type="button" onClick={() => realtimeAbort.current?.abort()}>
          {english ? "英語を停止" : "IPAを停止"}
        </button>}
        {english && <label htmlFor="english-case-file">
          英語発話ケースをレンダー
          <input id="english-case-file" type="file" accept=".json,application/json" disabled={Boolean(pending)}
            onChange={(event) => {
              const file = event.currentTarget.files?.[0];
              event.currentTarget.value = "";
              if (file) void run(false, file);
            }} />
        </label>}
        {english && importedCase && <button type="button" disabled={Boolean(pending)}
          onClick={() => void run(true, importedCase)}>読み込んだケースを実時間で発声</button>}
      </form>
      {(pending || capture) && <p role="status">{
        pending === "live" ? (english ? "英語を実時間で発声中" : "IPAを実時間で発声中") : pending ? "発話をレンダー中" :
        capture?.report.realtime ? (english ? "実時間の英語発話完了" : "実時間のIPA発話完了") : "発話レンダー完了"
      }</p>}
      {error && <p role="alert">発話のレンダーに失敗しました。{error}</p>}
      {!english && tractGrid && <div hidden={pending === "offline" || Boolean(capture)}>
        <SpeechTract3D sample={liveTract?.grid} lipMinimum={liveTract?.lipMinimum} contextFrame={liveTract?.contextFrame}
          sampleRate={fixture.voice.output_sample_rate_hz} onPrepared={setLiveViewPrepared} live />
      </div>}
      {capture?.caseId && <p>{capture.caseId} {capture.report.input}</p>}
      {capture && "shown" in capture.report.speech && <p>発音 <strong data-speech-transcript="">{capture.report.speech.shown}</strong></p>}
      {capture && "basePitchHz" in capture.report && typeof capture.report.basePitchHz === "number" && <p>
        基準F0 {capture.report.basePitchHz.toLocaleString("ja-JP", { maximumFractionDigits: 2 })} Hz
      </p>}
      {capture && <>
        <IpaTimeline pcm={capture.pcm} report={capture.report} closedArea={speechExperiment.measurement.closed_area_cm2} />
        <CaptureOutput capture={capture} name={capture.report.realtime ? `worklet-live-${name}` : `worklet-${name}`}
          caseId={capture.caseId ?? source.id} />
      </>}
    </section>
  );
}

function readNotes(source: string) {
  return source.split(/\r?\n/).flatMap((line, row) => {
    const text = line.trim();
    if (!text) return [];
    const values = text.split(/\s+/).map(Number);
    if (values.length !== 2 || !values.every(Number.isFinite) || values[1] <= 0) {
      throw new Error(`${row + 1}行目にMIDI番号と正の拍数を指定してください`);
    }
    return [{ midi: values[0], beats: values[1] }];
  });
}

function SongPanel() {
  const presets = { long: songFixture, fast: fastSongFixture, prepared: preparedSongFixture };
  const [preset, setPreset] = useState<keyof typeof presets>("long");
  const activeFixture = presets[preset];
  const fixture = activeFixture.song_voice;
  const [body, setBody] = useState(defaultBodySelection);
  const [notation, setNotation] = useState<"lyrics" | "syllables">("lyrics");
  const [lyrics, setLyrics] = useState(fixture.score.lyrics);
  const [syllables, setSyllables] = useState('[{"text":"pɑ","onset":[{"ipa":"p"}],"nucleus":{"ipa":"ɑ"},"coda":[]}]');
  const [bpm, setBpm] = useState(String(fixture.score.bpm));
  const [start, setStart] = useState(String(fixture.score.start_seconds));
  const [vibrato, setVibrato] = useState(String(fixture.vibrato_cents));
  const [turbulence, setTurbulence] = useState("1");
  const [glottisGain, setGlottisGain] = useState("");
  const [constrictionGain, setConstrictionGain] = useState("");
  const [teethLowpassFloor, setTeethLowpassFloor] = useState("");
  const [warmUpFrames, setWarmUpFrames] = useState(String(preparedSongFixture.song_voice.warm_up_frames));
  const [renderEndSeconds, setRenderEndSeconds] = useState(String(preparedSongFixture.song_voice.render_end_seconds));
  const [notes, setNotes] = useState(fixture.score.notes.map((note) => `${note.midi} ${note.beats}`).join("\n"));
  const [capture, setCapture] = useState<Capture<Awaited<ReturnType<typeof renderSongVoice>>["report"]>>();
  const [pending, setPending] = useState<"offline" | "live" | "record">();
  const [recording, setRecording] = useState(false);
  const [recordTract, setRecordTract] = useState(false);
  const [video, setVideo] = useState<File>();
  const recordingCanvas = useRef<HTMLCanvasElement>(null);
  const realtimeAbort = useRef<AbortController>(undefined);
  const [error, setError] = useState("");
  useEffect(() => () => realtimeAbort.current?.abort(), []);

  function selectPreset(value: typeof preset) {
    const next = presets[value].song_voice;
    setPreset(value);
    setNotation("lyrics");
    setLyrics(next.score.lyrics);
    setBpm(String(next.score.bpm));
    setStart(String(next.score.start_seconds));
    setVibrato(String(next.vibrato_cents));
    setTurbulence(String("turbulence" in next ? next.turbulence.scale : 1));
    setGlottisGain("");
    setConstrictionGain("");
    setTeethLowpassFloor("");
    if ("warm_up_frames" in next) {
      setWarmUpFrames(String(next.warm_up_frames));
      setRenderEndSeconds(String(next.render_end_seconds));
    }
    setNotes(next.score.notes.map((note) => `${note.midi} ${note.beats}`).join("\n"));
    setCapture(undefined);
    setVideo(undefined);
    setError("");
  }

  const ready = !pending && Boolean((notation === "lyrics" ? lyrics : syllables).trim() && notes.trim());
  async function run(mode: "offline" | "live" | "record" = "offline") {
    const abort = mode === "offline" ? undefined : new AbortController();
    realtimeAbort.current = abort;
    setPending(mode);
    setCapture(undefined);
    setVideo(undefined);
    setError("");
    try {
      const voice = {
        body: selectedBody(body), posture: normalizePose(fixture.posture), voice: fixture.voice,
        ...(preset === "prepared" && { warm_up_frames: Number(warmUpFrames),
          ...(renderEndSeconds !== "" && { render_end_seconds: Number(renderEndSeconds) }) }),
        fixed_airway: { sample_rate_hz: fixture.internal_sample_rate_hz, impulse_volume_cm3: 0, sample_count: 0 },
        turbulence: {
          scale: Number(turbulence),
          ...(glottisGain !== "" && { glottis_gain_multiplier: Number(glottisGain) }),
          ...(constrictionGain !== "" && { constriction_gain_multiplier: Number(constrictionGain) }),
          ...(teethLowpassFloor !== "" && { teeth_lowpass_floor_hz: Number(teethLowpassFloor) }),
        },
      };
      const noteSettings = {
        id: fixture.score.id, bpm: Number(bpm), notes: readNotes(notes),
        start_seconds: Number(start), vibrato_cents: Number(vibrato),
      };
      let input: SongInput;
      if (notation === "lyrics") {
        input = { ...noteSettings, lyrics };
      } else {
        let parsed: unknown;
        try { parsed = JSON.parse(syllables); } catch { throw new Error("IPA音節をJSONで入力してください"); }
        if (!Array.isArray(parsed) || !parsed.length) throw new Error("IPA音節を空でない配列で指定してください");
        input = { ...noteSettings, syllables: parsed };
      }
      const stride = songExperiment.measurement.observation_stride_frames;
      if (abort) {
        const canvas = recordingCanvas.current;
        if (mode === "record" && !canvas) throw new Error("録画用キャンバスを準備できません");
        const request = mode === "record" && canvas
          ? { canvas, includeTract: recordTract, onStarted: () => setRecording(true) } : undefined;
        const query = new URLSearchParams(window.location.search);
        const silentLead = query.get("songSilentLead");
        const scorePreparationBlock = query.get("songScorePreparationBlock");
        const scorePreparationInitialBlocks = query.get("songScorePreparationInitialBlocks");
        const silentLeadQuanta: SongSilentLeadQuanta | undefined = silentLead === "4" ? 4 : silentLead === "8" ? 8 : undefined;
        const startup = mode === "live" ? { traceStartup: query.has("songStartupTrace"),
          parallelRegistration: query.has("songParallelRegistration"),
          registerBeforeResume: query.has("songRegisterBeforeResume"),
          traceEvaluation: query.has("songModuleEvaluation"),
          traceNativeRegistration: query.has("songNativeRegistrationTrace"),
          traceRenderPhases: query.has("songRenderPhaseTrace"),
          renderPreparation: query.get("songRenderPreparation") ?? undefined,
          scorePreparationBlockFrames: scorePreparationBlock === null ? undefined : Number(scorePreparationBlock),
          scorePreparationInitialBlocks: scorePreparationInitialBlocks?.split(",").map(Number),
          traceScorePreparationBlocks: query.has("songScorePreparationTiming"),
          silentLeadQuanta,
          silentLeadTraceInput: query.has("songSilentLeadTrace"),
          silentLeadTraceNative: query.has("songSilentLeadNativeTrace"),
          parallelSilentLeadRegistration: query.get("songSilentLeadRegistration") === "parallel",
        } : undefined;
        const result = await renderRealtimeSongVoice(voice, input, stride, abort.signal, request, startup);
        setCapture(result);
        setVideo(result.video);
      } else {
        const result = await renderSongVoice(voice, input, stride);
        setCapture({ pcm: result.audio.getChannelData(0), report: result.report, replayCase: result.replayCase });
      }
    } catch (failure) {
      if (!abort?.signal.aborted) setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      realtimeAbort.current = undefined;
      setPending(undefined);
      setRecording(false);
    }
  }

  return (
    <section aria-labelledby="song-title">
      <h2 id="song-title">歌唱</h2>
      <form className="song-form" onSubmit={(event) => { event.preventDefault(); void run(); }}>
        <div className="song-settings">
          <label>歌唱プリセット
            <select value={preset} disabled={Boolean(pending)}
              onChange={(event) => selectPreset(event.target.value as typeof preset)}>
              <option value="long">長い音符</option>
              <option value="fast">短い音符</option>
              <option value="prepared">上流音源の比較</option>
            </select>
          </label>
          <label>音節の入力形式
            <select value={notation} disabled={Boolean(pending)}
              onChange={(event) => setNotation(event.target.value as typeof notation)}>
              <option value="lyrics">歌詞（英語・韓国語・ロシア語・中国語）</option>
              <option value="syllables">IPA音節 JSON</option>
            </select>
          </label>
          <VoiceBodyControls selection={body} onChange={setBody} disabled={Boolean(pending)} />
        </div>
        {preset === "prepared" && <div className="song-settings">
          <label>予約前の描画フレーム数
            <input type="number" min="0" step="1" required value={warmUpFrames} disabled={Boolean(pending)}
              onChange={(event) => setWarmUpFrames(event.target.value)} />
          </label>
          <label>出力終了（秒）
            <input type="number" min="0.001" step="any" value={renderEndSeconds} disabled={Boolean(pending)}
              onChange={(event) => setRenderEndSeconds(event.target.value)} />
          </label>
        </div>}
        {notation === "lyrics" ? <label>歌詞（英語・韓国語・ロシア語・中国語）
          <input value={lyrics} onChange={(event) => setLyrics(event.target.value)} disabled={Boolean(pending)} />
        </label> : <label>IPA音節 JSON
          <textarea value={syllables} onChange={(event) => setSyllables(event.target.value)} rows={5}
            spellCheck={false} disabled={Boolean(pending)} />
        </label>}
        <div className="song-settings">
          <label>テンポ（BPM）
            <input type="number" min="1" step="any" value={bpm} required disabled={Boolean(pending)}
              onChange={(event) => setBpm(event.target.value)} />
          </label>
          <label>ビブラート（セント）
            <input type="number" step="any" value={vibrato} required disabled={Boolean(pending)}
              onChange={(event) => setVibrato(event.target.value)} />
          </label>
          <label>乱流係数
            <input type="number" min="0" step="any" value={turbulence} required disabled={Boolean(pending)}
              onChange={(event) => setTurbulence(event.target.value)} />
          </label>
          <label>最初の拍（秒）
            <input type="number" min="0" step="any" value={start} required disabled={Boolean(pending)}
              onChange={(event) => setStart(event.target.value)} />
          </label>
        </div>
        <details>
          <summary>乱流源の設定</summary>
          <div className="song-settings">
            <label>声門の乱流ゲイン倍率
              <input type="number" min="0" step="any" placeholder="1" value={glottisGain} disabled={Boolean(pending)}
                onChange={(event) => setGlottisGain(event.target.value)} />
            </label>
            <label>狭窄の乱流ゲイン倍率
              <input type="number" min="0" step="any" placeholder="1" value={constrictionGain} disabled={Boolean(pending)}
                onChange={(event) => setConstrictionGain(event.target.value)} />
            </label>
            <label>歯の乱流の低域通過周波数の下限（Hz）
              <input type="number" min="0" step="any" placeholder="0" value={teethLowpassFloor} disabled={Boolean(pending)}
                onChange={(event) => setTeethLowpassFloor(event.target.value)} />
            </label>
          </div>
        </details>
        <label>MIDI番号と拍数
          <textarea value={notes} onChange={(event) => setNotes(event.target.value)}
            rows={3} aria-describedby="midi-help" spellCheck={false} disabled={Boolean(pending)} />
        </label>
        <p id="midi-help">1行に1音を入力し、番号と拍数を空白で区切ります。</p>
        <button type="submit" disabled={!ready}>歌唱をレンダー</button>
        <button type="button" disabled={!ready}
          onClick={(event) => { if (event.currentTarget.form?.reportValidity()) void run("live"); }}>実時間で歌唱</button>
        {songRecordingType() && <>
          <label className="tract-grid-option">
            <input type="checkbox" checked={recordTract} disabled={Boolean(pending)}
              onChange={(event) => setRecordTract(event.currentTarget.checked)} />
            録画に声道の三次元断面を含める
          </label>
          <button type="button" disabled={!ready}
            onClick={(event) => { if (event.currentTarget.form?.reportValidity()) void run("record"); }}>歌唱を録画</button>
        </>}
        {pending === "live" && <button type="button" onClick={() => realtimeAbort.current?.abort()}>歌唱を停止</button>}
        {pending === "record" && <button type="button" onClick={() => realtimeAbort.current?.abort()}>録画を中止</button>}
      </form>
      <p className="dictionary-credit">
        <a href={dictionaryLicenseUrl}>英語発音辞書のライセンス</a>
        {" · "}
        <a href={mandarinLicenseUrl}>中国語発音辞書のライセンス</a>
      </p>
      {(pending || capture) && <p role="status">{
        pending === "record" ? (recording ? "歌唱を録画中" : "歌唱の録画を準備中") :
          pending === "live" ? "実時間で歌唱中" : pending ? "歌唱をレンダー中" :
          video ? "歌唱の録画完了" : capture?.report.realtime ? "実時間の歌唱完了" : "歌唱レンダー完了"
      }</p>}
      <canvas ref={recordingCanvas} hidden={!recording} aria-label={recordTract
        ? "録画中の三次元断面と拍" : "録画中の拍と経過時刻"} className="song-recording-preview" />
      {video && <RecordedSong video={video} />}
      {error && <p role="alert">歌唱のレンダーに失敗しました。{error}</p>}
      {capture && <CaptureOutput capture={capture}
        name={capture.report.realtime ? "worklet-live-song" : "worklet-song"} caseId={activeFixture.id} />}
    </section>
  );
}

function RecordedSong({ video }: { video: File }) {
  const [url, setUrl] = useState<string>();
  useEffect(() => {
    const next = URL.createObjectURL(video);
    setUrl(next);
    return () => URL.revokeObjectURL(next);
  }, [video]);
  return url && <div className="song-recording-result">
    <video src={url} controls aria-label="録画した歌唱" className="song-recording-preview" />
    <a href={url} download={video.name}>歌唱の動画を保存</a>
  </div>;
}

function BeatPanel() {
  const fixture = beatFixture.beatbox_pattern;
  const strides = beatExperiment.measurement.observation_stride_frames;
  const { output_frames, output_rate_hz } = liveBeatExperiment.measurement;
  const beatSender = useRef<(command: BeatCommand) => void>(undefined);
  const [midiError, setMidiError] = useState("");
  const { inputs: midiInputs, connecting: connectingMidi, toggle: toggleMidi } = useMidiConnection(
    () => {}, setMidiError, (key) => {
      beatSender.current?.({ type: "bass_key", note: key.note, pressed: key.type === "note-on" });
    });
  const [humStep, setHumStep] = useState("1");
  const liveAbort = useRef<AbortController>(undefined);
  const [pattern, setPattern] = useState(fixture.pattern);
  const [bpm, setBpm] = useState(String(fixture.bpm));
  const [swing, setSwing] = useState(String(fixture.swing));
  const [stride, setStride] = useState(String(strides[0]));
  const [duration, setDuration] = useState(String(output_frames / output_rate_hz));
  const [pending, setPending] = useState<"offline" | "live">();
  const [progress, setProgress] = useState<BeatProgress>();
  const [capture, setCapture] = useState<Capture<Awaited<ReturnType<typeof renderBeatPattern>>["report"]>>();
  const [error, setError] = useState("");

  async function run(live = false) {
    const abort = live ? new AbortController() : undefined;
    liveAbort.current = abort;
    setPending(live ? "live" : "offline");
    setProgress(undefined);
    setCapture(undefined);
    setError("");
    try {
      const voice = {
        body: "male" as const, posture: normalizePose(fixture.posture), voice: fixture.voice,
        fixed_airway: { sample_rate_hz: fixture.internal_sample_rate_hz, impulse_volume_cm3: 0, sample_count: 0 },
      };
      const beat = { pattern, bpm: Number(bpm), swing: Number(swing),
        initialPitchHz: fixture.initial_f0_hz, noiseScale: fixture.noise_scale };
      const frames = Math.round((live ? Number(duration) : fixture.render_end_seconds) * voice.voice.output_sample_rate_hz);
      if (abort) {
        const result = await renderRealtimeBeatPattern(voice, beat, frames, Number(stride), (state, send) => {
          beatSender.current = send;
          setProgress(state);
        }, abort.signal);
        setCapture(result);
      } else {
        const { audio, report } = await renderBeatPattern(voice, beat, frames, Number(stride));
        setCapture({ pcm: audio.getChannelData(0), report });
      }
    } catch (failure) {
      if (!abort?.signal.aborted) setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      beatSender.current = undefined;
      liveAbort.current = undefined;
      setPending(undefined);
    }
  }

  const observations = capture?.report.observations;
  const liveCapture = Boolean(capture?.replayCase);
  const tempoDisabled = pending === "offline" || (pending === "live" && !progress);
  const stepColumn = capture?.report.columns.indexOf("beat_step") ?? -1;
  const changes = observations?.filter((row, i) => i === 0 || row[stepColumn] !== observations[i - 1][stepColumn]);
  const stepCount = Math.min(256, pattern.split(/[\s|]+/u).filter(Boolean).length);
  const slot = Number(humStep) - 1;
  return (
    <section aria-labelledby="beat-title">
      <h2 id="beat-title">ビートボックス</h2>
      <form className="song-form" onSubmit={(event) => { event.preventDefault(); void run(); }}>
        <label>ビートパターン
          <textarea value={pattern} onChange={(event) => setPattern(event.target.value)}
            rows={2} aria-describedby="beat-help" spellCheck={false} disabled={Boolean(pending)} />
        </label>
        <p id="beat-help">空白でステップを区切ります。休符は「.」、有声の打音に音高を付けるときは「m:43」と入力します。</p>
        <div className="song-settings">
          <label>テンポ（BPM）
            <input type="number" min="40" max="240" step="any" value={bpm} required disabled={tempoDisabled}
              onChange={(event) => setBpm(event.target.value)} />
          </label>
          <label>スウィング
            <input type="number" min="0" max="0.6" step="any" value={swing} required disabled={tempoDisabled}
              onChange={(event) => setSwing(event.target.value)} />
          </label>
        </div>
        <label>
          <span id="beat-stride-label">観測間隔（フレーム）</span>
          <select aria-labelledby="beat-stride-label" value={stride} disabled={Boolean(pending)}
            onChange={(event) => setStride(event.target.value)}>
            {strides.map((value) => <option key={value}>{value}</option>)}
          </select>
        </label>
        <label>実時間の採取時間（秒）
          <input type="number" min="0.1" step="any" value={duration} required disabled={Boolean(pending)}
            onChange={(event) => setDuration(event.target.value)} />
        </label>
        <button type="submit" disabled={Boolean(pending) || !pattern.trim()}>ビートをレンダー</button>
        <button type="button" disabled={Boolean(pending) || !pattern.trim()}
          onClick={(event) => { if (event.currentTarget.form?.reportValidity()) void run(true); }}>実時間でビートを再生</button>
        <button type="button" onClick={toggleMidi}>
          {midiInputs || connectingMidi ? "ビートのMIDIを切断" : "ビートのMIDIを接続"}
        </button>
        {connectingMidi && <p role="status">MIDI接続を待っています</p>}
        {midiInputs && <p role="status">ビートのMIDI入力 {midiInputs.join("、") || "機器待ち"}</p>}
        {midiError && <p role="alert">ビートのMIDI接続に失敗しました。{midiError}</p>}
        {pending === "live" && <>
          <div className="controls">
            <button type="button" disabled={!progress || !bpm || Number(bpm) < 40 || Number(bpm) > 240}
              onClick={() => beatSender.current?.({ type: "tempo", bpm: Number(bpm) })}>テンポを適用</button>
            <button type="button" disabled={!progress || !swing || Number(swing) < 0 || Number(swing) > 0.6}
              onClick={() => beatSender.current?.({ type: "tempo", swing: Number(swing) })}>スウィングを適用</button>
            <button type="button" disabled={!progress}
              onClick={() => { if (progress) beatSender.current?.({ type: "playing", playing: !progress.playing }); }}>
              {progress?.playing === false ? "ビートを再開" : "ビートを停止"}
            </button>
          </div>
          <div className="controls">
            <label>ハムを切り替えるステップ
              <input type="number" min="1" max={stepCount} step="1" value={humStep}
                onChange={(event) => setHumStep(event.target.value)} />
            </label>
            <button type="button" disabled={!progress || !Number.isInteger(slot) || slot < 0 || slot >= stepCount}
              onClick={() => beatSender.current?.({ type: "toggle_hum", step: slot })}>ハムを切り替え</button>
          </div>
          <button type="button" onClick={() => liveAbort.current?.abort()}>採取をキャンセル</button>
        </>}
      </form>
      {(pending || capture) && <p role="status">{
        pending === "live" ? progress ? "ビートを採取中" : "ビートを準備中"
          : pending ? "ビートをレンダー中" : liveCapture ? "実時間のビート採取完了" : "ビートのレンダー完了"
      }</p>}
      {pending === "live" && progress && <p data-beat-rendered={progress.framesRendered}>
        {(progress.framesRendered / output_rate_hz).toFixed(2)} 秒
        {" / "}{progress.playing ? progress.step < 0 ? "開始待ち" : `ステップ ${progress.step}` : "ビート停止中"}
      </p>}
      {error && <p role="alert">ビートのレンダーに失敗しました。{error}</p>}
      {capture && <>
        <CaptureOutput capture={capture} name={liveCapture ? "worklet-live-beatbox" : "worklet-beatbox"}
          caseId={liveCapture ? liveBeatExperiment.id : beatFixture.id} />
        <table className="beat-playhead">
          <caption>観測した再生位置の変化</caption>
          <thead><tr><th scope="col">出力フレーム</th><th scope="col">ステップ（0始まり）</th></tr></thead>
          <tbody>{changes?.map((row) => <tr key={row[0]}>
            <td>{row[0]}</td><td>{row[stepColumn] < 0 ? liveCapture ? "開始待ち・停止中" : "開始待ち" : row[stepColumn]}</td>
          </tr>)}</tbody>
        </table>
      </>}
    </section>
  );
}

type CreaturePreset = {
  id: string;
  label: string;
  action: string;
  caseId: string;
  downloadName: string;
  render(): Promise<Capture>;
};

function songbirdPresets(source: {
  songbird_voice: SongbirdInput;
  measurement: { variants: { id: string; overrides: Partial<SongbirdInput> }[] };
}, fixture: {
  id: string;
  upstream_revision: string;
  measurement: {
    variants: string[];
    observation_stride_frames: number;
    observation_offset_frames?: number;
    expected_render_quantum_frames: number;
    extra_output_frames?: number[];
  };
}, callLabel?: string, profile?: { id: string; label: string; stride: number; offset: number }): CreaturePreset[] {
  return fixture.measurement.variants.map((id) => {
    const variant = source.measurement.variants.find((entry) => entry.id === id);
    if (!variant) throw new Error(`鳴禽の基準条件 ${id} が見つかりません`);
    const input: SongbirdReplayCase["songbird_voice"] = {
      ...source.songbird_voice, ...variant.overrides, observe_syrinx: true,
      ...(callLabel && { observe_call_id: true }),
    };
    return {
      id: profile?.id ?? id,
      action: callLabel ? `${callLabel}を再生` : "持続音と停止を再生",
      label: profile?.label ?? callLabel ?? `${input.sample_rate_hz.toLocaleString("ja-JP")} Hz`,
      caseId: fixture.id,
      downloadName: callLabel ? fixture.id : "worklet-songbird",
      async render() {
        const config = fixture.measurement;
        const result = await renderSongbird(input, config.expected_render_quantum_frames, {
          stride: profile?.stride ?? config.observation_stride_frames,
          offset: profile?.offset ?? config.observation_offset_frames,
          exactFrames: config.extra_output_frames,
          countRenderCalls: profile !== undefined,
        });
        const replayCase: SongbirdReplayCase = {
          id: `worklet-songbird-${id}`, upstream_revision: fixture.upstream_revision, songbird_voice: input,
        };
        return { ...result, replayCase };
      },
    };
  });
}

const songbirdVariants = songbirdPresets(songbirdSource, songbirdExperiment);
function CreatureMidiPanel({ kind }: { kind: "songbird" | "seal" | "alligator" | "elephant" }) {
  const isSeal = kind === "seal";
  const isAlligator = kind === "alligator";
  const isElephant = kind === "elephant";
  const instrument = { songbird: "鳴禽", seal: "ウェッデルアザラシ",
    alligator: "アメリカアリゲーター", elephant: "アフリカゾウ" }[kind];
  const titleId = `${kind}-midi-title`;
  const heldSender = useRef<(note: number | null) => void>(undefined);
  const keySender = useRef<(note: number, pressed: boolean) => void>(undefined);
  const held = useRef<number | null>(null);
  const pressedKeys = useRef(new Set<number>());
  const [call, setCall] = useState("");
  const fixture = isElephant ? (call ? elephantMidiCallExperiment : elephantMidiExperiment) : isAlligator
    ? (call ? alligatorMidiCallExperiment : alligatorMidiExperiment) : isSeal
    ? (call ? sealMidiCallExperiment : sealMidiExperiment)
    : (call ? songbirdMidiCallExperiment : songbirdMidiExperiment);
  const initialDuration = { songbird: songbirdMidiExperiment.measurement.capture_seconds,
    seal: sealMidiExperiment.input.capture_seconds, alligator: alligatorMidiExperiment.input.capture_seconds,
    elephant: elephantMidiExperiment.input.capture_seconds }[kind];
  const [duration, setDuration] = useState(String(initialDuration));
  const [phase, setPhase] = useState<"starting" | "playing">();
  const [error, setError] = useState("");
  const [capture, setCapture] = useState<Capture>();

  const { inputs, connecting, toggle } = useMidiConnection(changeNote, setError, ({ note, type }) => {
    const pressed = type === "note-on";
    if (pressed) pressedKeys.current.add(note);
    else pressedKeys.current.delete(note);
    keySender.current?.(note, pressed);
  });

  function changeNote(note: number | null) {
    if (held.current === note) return;
    held.current = note;
    heldSender.current?.(note);
  }

  async function run() {
    setPhase("starting");
    setCapture(undefined);
    setError("");
    const seconds = Number(duration);
    const { quantum_frames, observation_stride_frames } = fixture.measurement;
    const sampling = { stride: observation_stride_frames };
    const onMidiReady = (send: (input: CreatureMidiInput) => void) => {
      if (call) {
        keySender.current = (note, pressed) => send({ call, note, pressed });
        for (const note of pressedKeys.current) keySender.current(note, true);
      } else {
        heldSender.current = (note) => send({ note });
        if (held.current !== null) heldSender.current(held.current);
      }
      setPhase("playing");
    };
    try {
      function recordedEvents(report: Awaited<ReturnType<typeof renderSongbird>>["report"]) {
        if (!report.midiEvents) throw new Error("採用したMIDI入力を取得できませんでした");
        return report.midiEvents.map((event) => {
          const { frame, note } = event;
          return "call" in event
            ? { frame, midi_call: { id: event.call, note: event.note, pressed: event.pressed } }
            : { frame, held_midi: { note } };
        });
      }
      if (isElephant) {
        const base = elephantSource.elephant_voice;
        const input: ElephantReplayCase["elephant_voice"] = {
          ...base, frames: Math.round(seconds * base.sample_rate_hz), events: [], observe_call: true, observe_valve: true,
        };
        const result = await renderElephant(input, quantum_frames, sampling, onMidiReady);
        const replayCase: ElephantReplayCase = {
          id: fixture.id, upstream_revision: fixture.upstream_revision,
          elephant_voice: { ...input, events: recordedEvents(result.report) },
        };
        setCapture({ ...result, replayCase });
        return;
      }
      if (isAlligator) {
        const base = alligatorSource.alligator_voice;
        const input: AlligatorReplayCase["alligator_voice"] = {
          ...base, frames: Math.round(seconds * base.sample_rate_hz), events: [], observe_call: true,
          ...(call === "hiss" && { observe_noise: true }),
        };
        const result = await renderAlligator(input, quantum_frames, sampling, onMidiReady);
        const replayCase: AlligatorReplayCase = {
          id: fixture.id, upstream_revision: fixture.upstream_revision,
          alligator_voice: { ...input, events: recordedEvents(result.report) },
        };
        setCapture({ ...result, replayCase });
        return;
      }
      if (isSeal) {
        const base = sealSource.seal_voice;
        const input: SealReplayCase["seal_voice"] = {
          ...base, breath: { ...base.breath, frames: Math.round(seconds * base.breath.sample_rate_hz), events: [] },
          events: [], observe_call_id: true, observe_glottis: true,
        };
        const result = await renderSeal(input, quantum_frames, sampling, onMidiReady);
        const replayCase: SealReplayCase = {
          id: fixture.id, upstream_revision: fixture.upstream_revision,
          seal_voice: { ...input, events: recordedEvents(result.report) },
        };
        setCapture({ ...result, replayCase });
        return;
      }
      const base = songbirdSource.songbird_voice;
      const input: SongbirdReplayCase["songbird_voice"] = {
        ...base, frames: Math.round(seconds * base.sample_rate_hz),
        events: [], observe_call_id: true, observe_syrinx: true,
      };
      const result = await renderSongbird(input, quantum_frames, sampling, onMidiReady);
      const replayCase: SongbirdReplayCase = {
        id: fixture.id, upstream_revision: fixture.upstream_revision,
        songbird_voice: { ...input, events: recordedEvents(result.report) },
      };
      setCapture({ ...result, replayCase });
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      heldSender.current = undefined;
      keySender.current = undefined;
      setPhase(undefined);
    }
  }

  return (
    <section aria-labelledby={titleId}>
      <h2 id={titleId}>MIDIで{instrument}を演奏</h2>
      <form className="song-form" onSubmit={(event) => { event.preventDefault(); void run(); }}>
        <button type="button" onClick={toggle}>
          {instrument}のMIDIを{inputs || connecting ? "切断" : "接続"}
        </button>
        {connecting && <p role="status">MIDI接続を待っています</p>}
        {inputs && <p>{inputs.join("、") || "MIDI機器待ち"}</p>}
        <label>鍵盤で鳴らす音
          <select value={call} disabled={Boolean(phase)} onChange={(event) => {
            setCall(event.target.value);
            setCapture(undefined);
          }}>
            <option value="">持続音</option>
            {isElephant ? <>
              <option value="rumble">Rumble</option>
              <option value="trumpet">Trumpet</option>
              <option value="squeak">Squeak</option>
            </> : isAlligator ? <>
              <option value="bellow">Bellow</option>
              <option value="growl">Growl</option>
              <option value="hiss">Hiss</option>
              <option value="dance">Water dance</option>
            </> : isSeal ? <>
              <option value="trill">Descending trill</option>
              <option value="zap">Laser chirp</option>
              <option value="whistle">U whistle</option>
              <option value="chug">Chug</option>
            </> : <>
              <option value="flute">Flute phrase</option>
              <option value="trill">Canary trill</option>
              <option value="chirps">Chirp cascade</option>
              <option value="buzz">Finch buzz</option>
            </>}
          </select>
        </label>
        <label>採取時間（秒）
          <input type="number" min="0.1" step="any" required value={duration} disabled={Boolean(phase)}
            onChange={(event) => setDuration(event.target.value)} />
        </label>
        <button type="submit" disabled={!inputs?.length || Boolean(phase)}>{instrument}のMIDI計測を開始</button>
      </form>
      <p role="status">{phase === "starting" ? `${instrument}のMIDIを準備中` : phase === "playing" ?
        `${instrument}のMIDIを計測中` : capture ? `${instrument}のMIDI計測完了` : ""}</p>
      {error && <p role="alert">{error}</p>}
      {capture && <CaptureOutput capture={capture} name={fixture.id} caseId={fixture.id} />}
    </section>
  );
}

const trillObservationLabels: Record<string, string> = {
  "trill-control-start": "trillの観測対照（制御区間の先頭、64フレーム刻み）",
  "trill-control-end": "trillの観測対照（制御区間の末尾、64フレーム刻み）",
  "trill-quantum-end": "trillの観測対照（描画量子の末尾、128フレーム刻み）",
};
const trillObservationVariants = trillObservation.measurement.observation_profiles.flatMap((profile) =>
  songbirdPresets(callsSource, {
    ...trillObservation,
    measurement: { ...trillExperiment.measurement, variants: trillObservation.measurement.variants },
  }, "trill", { ...profile, label: trillObservationLabels[profile.id] }));
const songbirdCallVariants = [
  ...songbirdPresets(fluteSource, fluteExperiment, "flute の途中停止"),
  ...songbirdPresets(callsSource, trillExperiment, "trill"),
  ...songbirdPresets(callsSource, chirpsExperiment, "chirps"),
  ...songbirdPresets(callsSource, buzzExperiment, "buzz"),
  ...songbirdPresets(callsSource, switchExperiment, "buzz → trill"),
  ...trillObservationVariants,
];

type SealPresetInput = SealReplayCase["seal_voice"];

function sealPresets(source: {
  seal_voice: SealPresetInput;
  measurement: { variants: {
    id: string; breath: Partial<SealPresetInput["breath"]>; level?: number; events?: SealPresetInput["events"] | null;
    shape?: Partial<SealPresetInput["shape"]>;
  }[] };
}, fixture: {
  id: string;
  upstream_revision: string;
  measurement: {
    variants: string[];
    expected_render_quantum_frames: number;
    observation_stride_frames: number;
    observation_offset_frames: number;
    observation_stride_by_variant?: Record<string, number>;
    extra_output_frames: Record<string, number[]>;
  };
}, action: string, replayPrefix: string): CreaturePreset[] {
  const config = fixture.measurement;
  return config.variants.map((id) => {
    const variant = source.measurement.variants.find((entry) => entry.id === id);
    if (!variant) throw new Error(`アザラシの基準条件 ${id} が見つかりません`);
    const base = source.seal_voice;
    const events = variant.events ?? base.events;
    const input: SealPresetInput = {
      ...base, breath: { ...base.breath, ...variant.breath }, level: variant.level ?? base.level,
      shape: { ...base.shape, ...variant.shape },
      ...(events && { events }),
      ...((events?.length || base.observe_glottis) && { observe_call_id: true }),
    };
    return {
      id, action, label: `${input.breath.sample_rate_hz.toLocaleString("ja-JP")} Hz`,
      caseId: fixture.id, downloadName: fixture.id,
      async render() {
        const result = await renderSeal(input, config.expected_render_quantum_frames, {
          stride: config.observation_stride_by_variant?.[id] ?? config.observation_stride_frames,
          offset: config.observation_offset_frames,
          exactFrames: config.extra_output_frames[id],
        });
        const replayCase: SealReplayCase = {
          id: `${replayPrefix}-${id}`, upstream_revision: fixture.upstream_revision, seal_voice: input,
        };
        return { ...result, replayCase };
      },
    };
  });
}

const sealVariants = sealPresets(sealSource, sealExperiment, "持続音と停止を再生", "worklet-seal");
const sealTrillVariants = sealPresets(sealTrillSource, sealTrillExperiment, "trillを再生", "worklet-seal-trill");
const sealZapVariants = sealPresets(sealZapSource, sealZapExperiment, "zapを再生", "worklet-seal-zap");
const sealWhistleVariants = sealPresets(sealWhistleSource, sealWhistleExperiment, "whistleを再生", "worklet-seal-whistle");
const sealChugVariants = sealPresets(sealChugSource, sealChugExperiment, "chugを再生", "worklet-seal-chug");

type AlligatorPresetInput = AlligatorReplayCase["alligator_voice"];

function alligatorPresets(source: {
  alligator_voice: AlligatorPresetInput;
  measurement: { variants: ({ id: string; shape?: Partial<AlligatorPresetInput["shape"]> }
    & Partial<Pick<AlligatorPresetInput, "sample_rate_hz" | "frames" | "events">>)[] };
}, fixture: {
  id: string;
  upstream_revision: string;
  measurement: {
    variants: string[];
    expected_render_quantum_frames: number;
    observation_stride_frames: number;
    observation_offset_frames: number;
    observation_stride_by_variant?: Record<string, number>;
    observation_windows_output_frames?: Record<string, number[][]>;
    extra_output_frames: Record<string, number[]>;
  };
}, labels: Record<string, string>, action: string, replayPrefix: string): CreaturePreset[] {
  const config = fixture.measurement;
  return config.variants.map((id) => {
    const variant = source.measurement.variants.find((entry) => entry.id === id);
    if (!variant || !labels[id]) throw new Error(`アリゲーターの基準条件 ${id} が見つかりません`);
    const base = source.alligator_voice;
    const input: AlligatorPresetInput = {
      sample_rate_hz: variant.sample_rate_hz ?? base.sample_rate_hz,
      frames: variant.frames ?? base.frames,
      shape: { ...base.shape, ...variant.shape },
      events: variant.events ?? base.events,
      level: base.level,
      ...(base.observe_call !== undefined && { observe_call: base.observe_call }),
      ...(base.observe_noise !== undefined && { observe_noise: base.observe_noise }),
    };
    return {
      id, label: labels[id], action, caseId: fixture.id, downloadName: fixture.id,
      async render() {
        const result = await renderAlligator(input, config.expected_render_quantum_frames, {
          stride: config.observation_stride_by_variant?.[id] ?? config.observation_stride_frames,
          offset: config.observation_offset_frames,
          windows: config.observation_windows_output_frames?.[id],
          exactFrames: config.extra_output_frames[id],
        });
        const replayCase: AlligatorReplayCase = {
          id: `${replayPrefix}-${id}`, upstream_revision: fixture.upstream_revision, alligator_voice: input,
        };
        return { ...result, replayCase };
      },
    };
  });
}

const alligatorVariants = alligatorPresets(alligatorSource, alligatorExperiment, {
  "official-sustain-48000": "標準の開始・停止（48 kHz）",
  "open-mouth-48000": "口を広げる（48 kHz）",
  "minimum-nostrils-48000": "鼻孔を最小にする（48 kHz）",
  "hiss-44100": "声門を開く（44.1 kHz）",
  "silent-96000": "無呼気（96 kHz）",
}, "固定発声を再生", "worklet-alligator");

const alligatorBellowVariants = alligatorPresets(alligatorBellowSource, alligatorBellowExperiment, {
  "official-prefix-48000": "公式デモ先頭（48 kHz）",
  "manual-stop-44100": "手動入力と途中停止（44.1 kHz）",
  "pitch-floor-96000": "移調時の音高下限（96 kHz）",
}, "bellowを再生", "worklet-alligator-bellow");

const alligatorGrowlVariants = alligatorPresets(alligatorGrowlSource, alligatorGrowlExperiment, {
  "official-prefix-48000": "公式デモ先頭（48 kHz）",
  "switch-44100": "bellowからの切り替え（44.1 kHz）",
  "pitch-ceiling-96000": "移調時の音高上限（96 kHz）",
}, "growlを再生", "worklet-alligator-growl");

const alligatorHissVariants = alligatorPresets(alligatorHissSource, alligatorHissExperiment, {
  "official-prefix-48000": "公式デモ先頭（48 kHz）",
  "switch-44100": "growlからの切り替え（44.1 kHz）",
  "standalone-96000": "単独のhiss（96 kHz）",
}, "hissを再生", "worklet-alligator-hiss");

const alligatorDanceVariants = alligatorPresets(alligatorDanceSource, alligatorDanceExperiment, {
  "official-full-48000": "公式デモ全体（48 kHz）",
  "switch-44100": "hissからの切り替え（44.1 kHz）",
  "standalone-96000": "単独のdance（96 kHz）",
}, "danceを再生", "worklet-alligator-dance");

type ElephantPresetInput = ElephantReplayCase["elephant_voice"];

function elephantPresets(source: {
  elephant_voice: ElephantPresetInput;
  measurement: { variants: ({ id: string; shape?: Partial<ElephantPresetInput["shape"]> }
    & Partial<Pick<ElephantPresetInput, "sample_rate_hz" | "frames" | "events">>)[] };
}, fixture: {
  id: string;
  upstream_revision: string;
  measurement: {
    variants: string[];
    expected_render_quantum_frames: number;
    observation_stride_frames: number;
    observation_offset_frames: number;
    observation_stride_by_variant?: Record<string, number>;
    observation_windows_output_frames: Record<string, number[][]>;
    extra_output_frames: Record<string, number[]>;
  };
}, labels: Record<string, string>, action: string): CreaturePreset[] {
  const config = fixture.measurement;
  return config.variants.map((id) => {
    const variant = source.measurement.variants.find((entry) => entry.id === id);
    if (!variant || !labels[id]) throw new Error(`ゾウの基準条件 ${id} が見つかりません`);
    const base = source.elephant_voice;
    const input: ElephantPresetInput = {
      ...base,
      sample_rate_hz: variant.sample_rate_hz ?? base.sample_rate_hz,
      frames: variant.frames ?? base.frames,
      shape: { ...base.shape, ...variant.shape },
      events: variant.events ?? base.events,
    };
    return {
      id, label: labels[id], action, caseId: fixture.id, downloadName: fixture.id,
      async render() {
        const result = await renderElephant(input, config.expected_render_quantum_frames, {
          stride: config.observation_stride_by_variant?.[id] ?? config.observation_stride_frames,
          offset: config.observation_offset_frames,
          exactFrames: config.extra_output_frames[id],
          windows: config.observation_windows_output_frames[id],
        });
        const replayCase: ElephantReplayCase = {
          id: `${fixture.id}-${id}`,
          upstream_revision: fixture.upstream_revision,
          elephant_voice: input,
        };
        return { ...result, replayCase };
      },
    };
  });
}

const elephantVariants = elephantPresets(elephantSource, elephantExperiment, {
  "official-sustain-48000": "公式デモの固定発声（48 kHz）",
  "route-switch-44100": "口から鼻への経路変更（44.1 kHz）",
  "oral-sustain-96000": "口側を維持（96 kHz）",
  "silent-48000": "無呼気（48 kHz）",
}, "固定発声を再生");

const elephantRumbleVariants = elephantPresets(elephantRumbleSource, elephantRumbleExperiment, {
  "official-rumble-48000": "公式デモ先頭（48 kHz）",
  "manual-stop-44100": "移調と途中停止（44.1 kHz）",
  "natural-end-96000": "自然終了（96 kHz）",
}, "rumbleを再生");

const elephantTrumpetVariants = elephantPresets(elephantTrumpetSource, elephantTrumpetExperiment, {
  "official-trumpet-48000": "公式デモ先頭（48 kHz）",
  "switch-stop-44100": "rumbleから置き換え・途中停止（44.1 kHz）",
  "requested-pitch-96000": "700 Hz指定・自然終了（96 kHz）",
  "default-pitch-96000-prefix": "音高指定なし・先頭区間（96 kHz）",
}, "trumpetを再生");

const elephantSqueakVariants = elephantPresets(elephantSqueakSource, elephantSqueakExperiment, {
  "official-full-48000": "公式デモ全体（48 kHz）",
  "switch-stop-44100": "trumpetから置き換え・途中停止（44.1 kHz）",
  "natural-end-96000": "初期モード0・自然終了（96 kHz）",
  "initial-mode-one-96000": "初期モード1・先頭区間（96 kHz）",
}, "squeakを再生");

function CreaturePanel({ title, titleId, variants, selectLabel = "出力サンプルレート" }: {
  title: string; titleId: string; variants: CreaturePreset[]; selectLabel?: string;
}) {
  const [selection, setSelection] = useState(variants[0].id);
  const [capture, setCapture] = useState<Capture>();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const variant = variants.find(({ id }) => id === selection) ?? variants[0];

  async function run() {
    setPending(true);
    setCapture(undefined);
    setError("");
    try {
      setCapture(await variant.render());
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setPending(false);
    }
  }
  return (
    <section aria-labelledby={titleId}>
      <h2 id={titleId}>{title}</h2>
      <label>{selectLabel}{" "}
        <select value={selection} disabled={pending} onChange={(event) => {
          setSelection(event.target.value);
          setCapture(undefined);
          setError("");
        }}>
          {variants.map(({ id, label }) => <option key={id} value={id}>{label}</option>)}
        </select>
      </label>{" "}
      <button type="button" disabled={pending} onClick={run}>{variant.action}</button>
      <p role="status">{pending ? "実時間計測中" : capture ? "実時間計測完了" : ""}</p>
      {error && <p role="alert">{title}の計測に失敗しました。{error}</p>}
      {capture && <CaptureOutput capture={capture} name={variant.downloadName} caseId={variant.caseId} />}
    </section>
  );
}

function App() {
  const [capture, setCapture] = useState<Capture<Awaited<ReturnType<typeof renderFixedVoice>>["report"]>>();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [observeRadiation, setObserveRadiation] = useState(false);
  async function run() {
    setPending(true);
    setCapture(undefined);
    setError("");
    try {
      const input = {
        ...fixedCase, ...fixedInput(),
        ...(observeRadiation && { fixed_voice_probe: { radiation_components: true } }),
      };
      const result = await renderFixedVoice(input, experiment.measurement.observation_stride_frames);
      setCapture({
        pcm: result.audio.getChannelData(0), report: result.report, replayCase: observeRadiation ? input : undefined,
      });
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setPending(false);
    }
  }
  return (
    <main>
      <header>
        <h1>CHIMERA 発声研究</h1>
        <p>AudioWorkletで合成した音声と観測値を保存できます。WAVはWeb Audioでの追加加工前の出力です。</p>
        <p><a href="?show=duet-clock">デュエットの再生時計</a></p>
      </header>
      <div className="fixed-render-controls">
        <button type="button" onClick={run} disabled={pending}>固定母音 /i/ をレンダー</button>
        <label>
          <input type="checkbox" checked={observeRadiation} disabled={pending}
            onChange={(event) => setObserveRadiation(event.target.checked)} />
          放射流量を観測する
        </label>
      </div>
      <p role="status">{pending ? "レンダー中" : capture ? "レンダー完了" : ""}</p>
      {error && <p role="alert">レンダーに失敗しました。{error}</p>}
      {capture && <CaptureOutput capture={capture} name="worklet-i" />}
      {capture?.report.radiation && <RadiationScope pcm={capture.pcm} sampleRate={capture.report.sampleRate}
        radiation={capture.report.radiation} />}
      <Tract3DPanel input={fixedInput()} />
      <RealtimePanel />
      <RealtimePanel manual />
      <SpeechPanel />
      <SpeechPanel english />
      <MidiPanel />
      <SongPanel />
      <BeatPanel />
      <CreaturePanel title="鳴禽の持続音" titleId="songbird-title" variants={songbirdVariants} />
      <CreatureMidiPanel kind="songbird" />
      <CreaturePanel title="鳴禽のコール" titleId="songbird-calls-title" variants={songbirdCallVariants}
        selectLabel="再生ケース" />
      <CreaturePanel title="ウェッデルアザラシの持続音" titleId="seal-title" variants={sealVariants} />
      <CreatureMidiPanel kind="seal" />
      <CreaturePanel title="ウェッデルアザラシの trill" titleId="seal-trill-title" variants={sealTrillVariants} />
      <CreaturePanel title="ウェッデルアザラシの zap" titleId="seal-zap-title" variants={sealZapVariants} />
      <CreaturePanel title="ウェッデルアザラシの whistle" titleId="seal-whistle-title" variants={sealWhistleVariants} />
      <CreaturePanel title="ウェッデルアザラシの chug" titleId="seal-chug-title" variants={sealChugVariants} />
      <CreaturePanel title="アメリカアリゲーターの固定発声" titleId="alligator-title" variants={alligatorVariants}
        selectLabel="再生ケース" />
      <CreatureMidiPanel kind="alligator" />
      <CreaturePanel title="アメリカアリゲーターの bellow" titleId="alligator-bellow-title"
        variants={alligatorBellowVariants} selectLabel="再生ケース" />
      <CreaturePanel title="アメリカアリゲーターの growl" titleId="alligator-growl-title"
        variants={alligatorGrowlVariants} selectLabel="再生ケース" />
      <CreaturePanel title="アメリカアリゲーターの hiss" titleId="alligator-hiss-title"
        variants={alligatorHissVariants} selectLabel="再生ケース" />
      <CreaturePanel title="アメリカアリゲーターの dance" titleId="alligator-dance-title"
        variants={alligatorDanceVariants} selectLabel="再生ケース" />
      <CreaturePanel title="アフリカゾウの固定発声" titleId="elephant-fixed-title"
        variants={elephantVariants} selectLabel="再生ケース" />
      <CreatureMidiPanel kind="elephant" />
      <CreaturePanel title="アフリカゾウの rumble" titleId="elephant-rumble-title"
        variants={elephantRumbleVariants} selectLabel="再生ケース" />
      <CreaturePanel title="アフリカゾウの trumpet" titleId="elephant-trumpet-title"
        variants={elephantTrumpetVariants} selectLabel="再生ケース" />
      <CreaturePanel title="アフリカゾウの squeak" titleId="elephant-squeak-title"
        variants={elephantSqueakVariants} selectLabel="再生ケース" />
    </main>
  );
}

const showId = new URLSearchParams(location.search).get("show");
createRoot(document.getElementById("root")!).render(showId && /^[\w-]+$/.test(showId)
  ? <DuetPage id={showId} /> : <App />);
