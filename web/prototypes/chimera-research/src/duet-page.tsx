import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { DuetTransport } from "./duet-transport";
import { advanceDuetMotionTime } from "./duet-head-echoes";
import { duetBeatStep } from "./duet-head-expression";
import { DuetTeleTrack, readNoiseBranches, type NoiseBranchLayout } from "./duet-telemetry";
import { buildDuetWords, duetWordAt, readDuetMelody, type DuetWords } from "./duet-words";
import { splitSongLyrics } from "./render-fixed-voice";

type Show = { title: string; audio: string; sample_rate_hz: number; frames: number; spell?: Record<string, string>;
  bpm?: number; downbeat?: number;
  voices: { name: string; tele?: string; melody?: string; noise_branches?: unknown }[] };
type LoadedShow = Omit<Show, "voices"> & {
  voices: { name: string; track?: DuetTeleTrack; noiseBranches?: NoiseBranchLayout; words?: DuetWords; lyricError?: string }[];
};
const initial = { time: 0, duration: 0, playing: false, epoch: 0, motionTime: 0, motionStep: 0 };
const DuetHeads = lazy(() => import("./duet-heads").then(({ DuetHeads }) => ({ default: DuetHeads })));

async function fetchShowAsset(url: string, signal: AbortSignal) {
  const result = await fetch(url, { signal });
  if (!result.ok) throw new Error(`公演の素材を読み込めません（HTTP ${result.status}）`);
  return result;
}

export function DuetPage({ id }: { id: string }) {
  const transport = useRef<DuetTransport | undefined>(undefined);
  const motionTime = useRef(0);
  const [show, setShow] = useState<LoadedShow>();
  const [state, setState] = useState(initial);
  const [error, setError] = useState("");
  const [expressive, setExpressive] = useState(true);
  const [pressureVisible, setPressureVisible] = useState(true);
  const [airflowVisible, setAirflowVisible] = useState(true);
  const [turbulenceVisible, setTurbulenceVisible] = useState(true);
  const base = import.meta.env.BASE_URL;
  useEffect(() => {
    const abort = new AbortController();
    let animation = 0;
    motionTime.current = 0;
    const directory = `${base}shows/${id}/`;
    void (async () => {
      const manifest = await fetchShowAsset(directory + "show.json", abort.signal);
      const next: Show = await manifest.json();
      if (!next.title || !/^[\w.-]+\.wav$/.test(next.audio) || !Array.isArray(next.voices)
          || next.voices.some((voice) => !voice?.name || (voice.tele !== undefined && !/^[\w.-]+\.tele$/.test(voice.tele))
            || (voice.melody !== undefined && !/^[\w.-]+\.json$/.test(voice.melody)))
          || !Number.isSafeInteger(next.sample_rate_hz) || next.sample_rate_hz <= 0
          || !Number.isSafeInteger(next.frames) || next.frames <= 0
          || (next.bpm !== undefined && (!Number.isFinite(next.bpm) || next.bpm < 0))
          || (next.downbeat !== undefined && !Number.isFinite(next.downbeat))) {
        throw new Error("公演の音源またはサンプル数の設定が不正です");
      }
      const bytes = async (name: string) => (await fetchShowAsset(directory + name, abort.signal)).arrayBuffer();
      const readWords = async (file: string) => {
        const response = await fetchShowAsset(directory + file, abort.signal);
        const melody = readDuetMelody(await response.json());
        const syllables = melody.syllables ?? await splitSongLyrics(melody.lyrics, abort.signal);
        return buildDuetWords(melody, syllables, next.sample_rate_hz, next.spell);
      };
      const [file, voices] = await Promise.all([bytes(next.audio), Promise.all(next.voices.map(async ({ name, tele, melody, noise_branches }) => {
        const [track, lyrics] = await Promise.all([
          tele === undefined ? undefined : bytes(tele).then((data) => new DuetTeleTrack(data)),
          melody === undefined ? {} : readWords(melody).then((words) => ({ words })).catch((failure: unknown) => ({
            lyricError: failure instanceof Error ? failure.message : String(failure),
          })),
        ]);
        if (noise_branches !== undefined && !track) throw new Error("乱流源の枝情報に対応するテレメトリがありません");
        const noiseBranches = track && noise_branches !== undefined ? readNoiseBranches(noise_branches, track) : undefined;
        return { name, track, noiseBranches, ...lyrics };
      }))]);
      abort.signal.throwIfAborted();
      const player = new DuetTransport();
      transport.current = player;
      await player.load(file);
      abort.signal.throwIfAborted();
      if (Math.abs(player.duration - next.frames / next.sample_rate_hz) > 1 / next.sample_rate_hz) {
        throw new Error("音源の長さが公演の設定と一致しません");
      }
      setState({ ...player.snapshot(), motionTime: motionTime.current, motionStep: 0 });
      setShow({ ...next, voices });
      let last = performance.now();
      const update = (now: number) => {
        const motionStep = (now - last) / 1000;
        const visualTime = advanceDuetMotionTime(motionTime.current, now - last);
        last = now;
        motionTime.current = visualTime;
        const snapshot = player.snapshot();
        setState((previous) => !snapshot.playing && previous.time === snapshot.time && !previous.playing
          && previous.epoch === snapshot.epoch ? previous : { ...snapshot, motionTime: visualTime, motionStep });
        animation = requestAnimationFrame(update);
      };
      animation = requestAnimationFrame(update);
    })().catch((failure) => {
      if (abort.signal.aborted) return;
      transport.current?.dispose();
      transport.current = undefined;
      setError(failure instanceof Error ? failure.message : String(failure));
    });
    return () => {
      abort.abort();
      cancelAnimationFrame(animation);
      transport.current?.dispose();
      transport.current = undefined;
    };
  }, [base, id]);

  const seek = (seconds: number) => {
    const player = transport.current;
    if (!player) return;
    player.seek(seconds);
    setState({ ...player.snapshot(), motionTime: motionTime.current, motionStep: 0 });
  };
  const toggle = () => {
    const player = transport.current;
    if (!player) return;
    if (player.snapshot().playing) player.pause();
    else player.play();
    setState({ ...player.snapshot(), motionTime: motionTime.current, motionStep: 0 });
  };
  const frame = show ? Math.min(show.frames, Math.round(state.time * show.sample_rate_hz)) : 0;
  const beatStep = state.playing ? duetBeatStep(state.time, show?.bpm, show?.downbeat) : -1;
  const voices = show?.voices.map((voice) => ({ ...voice, word: voice.words ? duetWordAt(voice.words, state.time) : null })) ?? [];
  const observations = voices.flatMap(({ name, track, word, noiseBranches }) => track
    ? [{ name, track, word, noiseBranches, beatStep, ...track.frame(track.indexAt(state.time)) }] : []);
  const lyrics = voices.filter(({ words, lyricError }) => words || lyricError);
  return <main>
    <header>
      <p><a href={base}>CHIMERA 発声研究に戻る</a></p>
      <h1>{show?.title ?? "デュエット"}</h1>
    </header>
    {error ? <p role="alert">{error}</p> : !show ? <p role="status">音源を準備中</p> : <section aria-label="デュエットの再生">
      {!observations.length && !lyrics.length && <p>{show.voices.map(({ name }) => name).join("・")}</p>}
      <p><button type="button" onClick={toggle}>{state.playing ? "一時停止"
        : state.time >= state.duration - 0.05 ? "最初から再生" : "再生"}</button></p>
      <label>音源の位置
        <input type="range" min={0} max={state.duration} step="any" value={state.time}
          onChange={(event) => seek(Number(event.currentTarget.value))} />
      </label>
      <p><output aria-label="音源フレーム" data-epoch={state.epoch} data-time={state.time}>{frame}</output>
        {` / ${show.frames} フレーム · ${state.time.toFixed(3)} / ${state.duration.toFixed(3)} 秒`}</p>
      {observations.length > 0 && <>
        <div className="duet-view-controls">
          <label><input type="checkbox" checked={expressive} onChange={(event) => setExpressive(event.currentTarget.checked)} />
            表情と頭部の動き</label>
          <label><input type="checkbox" checked={pressureVisible} onChange={(event) => setPressureVisible(event.currentTarget.checked)} />
            声道の圧力</label>
          <label><input type="checkbox" checked={airflowVisible} onChange={(event) => setAirflowVisible(event.currentTarget.checked)} />
            気流の軌跡</label>
          {observations.some(({ noiseBranches }) => noiseBranches) && <label>
            <input type="checkbox" checked={turbulenceVisible} onChange={(event) => setTurbulenceVisible(event.currentTarget.checked)} />
            乱流源</label>}
          {pressureVisible && <small className="duet-pressure-scale">
            <span aria-hidden="true" /> 圧力RMS 40–4,000 dyn/cm²
          </small>}
        </div>
        <Suspense fallback={<p role="status">三次元頭部を準備中</p>}>
          <DuetHeads observations={observations} clock={state} expressive={expressive} pressureVisible={pressureVisible}
            airflowVisible={airflowVisible} turbulenceVisible={turbulenceVisible} />
        </Suspense>
      </>}
      {lyrics.length > 0 && <dl className="duet-lyrics" aria-label="声部別の歌詞">
        {lyrics.map(({ name, word, lyricError }, index) => <div key={index}>
          <dt>{name}</dt><dd data-word-key={word?.key}>{lyricError ?? word?.text ?? "—"}</dd>
        </div>)}
      </dl>}
      {observations.length > 0 && <table aria-label="声部別のテレメトリ">
        <thead><tr><th>声部</th><th>観測行</th><th>採取サンプル</th><th>F0 (Hz)</th><th>口唇開度 (cm)</th></tr></thead>
        <tbody>{observations.map(({ name, index, sample, f0, artic }, voice) => <tr key={voice}>
          <th scope="row">{name}</th><td>{index}</td><td>{sample}</td><td>{f0.toFixed(3)}</td>
          <td>{artic[7]?.toFixed(4) ?? "—"}</td>
        </tr>)}</tbody>
      </table>}
    </section>}
  </main>;
}
