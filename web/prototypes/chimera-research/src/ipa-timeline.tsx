import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { EnglishSpeech, IpaSpeech } from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/planning";
import type { GlottalTrace, TractProfile } from "./fixed-worklet-types";
import { GlottalScope } from "./glottal-scope";
import { SpeechSpectrum } from "./speech-spectrum";
import { SpeechTract3D } from "./speech-tract-3d";
import { TractProfileView } from "./tract-profile";

const ENVELOPE_BINS = 384;
const HEIGHT = 232;
const LIP_TOP = 67;
const LIP_BOTTOM = 120;
const PCM_TOP = 150;
const PCM_BOTTOM = 208;
const PCM_MIDDLE = (PCM_TOP + PCM_BOTTOM) / 2;

type LipSample = { frame: number; area: number };
type TimelineReport = {
  sampleRate: number;
  columns: string[];
  observations: number[][];
  speech: IpaSpeech | EnglishSpeech;
  tract?: TractProfile;
  glottal?: GlottalTrace;
};

function pcmEnvelope(pcm: Float32Array) {
  const count = Math.min(pcm.length, ENVELOPE_BINS);
  let peak = 0;
  const bins = Array.from({ length: count }, (_, bin) => {
    const from = Math.floor(bin * pcm.length / count);
    const to = Math.floor((bin + 1) * pcm.length / count);
    let low = pcm[from];
    let high = low;
    for (let i = from + 1; i < to; ++i) {
      low = Math.min(low, pcm[i]);
      high = Math.max(high, pcm[i]);
    }
    peak = Math.max(peak, -low, high);
    return { middle: (from + to) / 2, low, high };
  });
  return { bins, peak };
}

function sampledClosures(samples: LipSample[], threshold: number, frames: number) {
  const spans: { from: number; to: number }[] = [];
  let from: number | undefined;
  for (const { frame, area } of samples) {
    if (area < threshold) from ??= frame + 1;
    else if (from !== undefined) {
      spans.push({ from, to: frame + 1 });
      from = undefined;
    }
  }
  if (from !== undefined) spans.push({ from, to: frames });
  return spans;
}

function observationAt<T>(samples: T[], frame: number, frameOf: (sample: T) => number): T | undefined {
  let left = 0;
  let right = samples.length;
  while (left < right) {
    const middle = Math.floor((left + right) / 2);
    if (frameOf(samples[middle]) <= frame) left = middle + 1;
    else right = middle;
  }
  return samples[left - 1];
}

export function IpaTimeline({ pcm, report, closedArea }: {
  pcm: Float32Array; report: TimelineReport; closedArea: number;
}) {
  const { sampleRate } = report;
  const frames = pcm.length;
  const [frame, setFrame] = useState(0);
  const [width, setWidth] = useState(640);
  const graph = useRef<HTMLDivElement>(null);
  const titleId = useId();
  useEffect(() => {
    const element = graph.current;
    if (!element) return;
    const observer = new ResizeObserver(([{ contentRect }]) => {
      if (contentRect.width > 0) setWidth(Math.round(contentRect.width));
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const source = useMemo(() => {
    const frameColumn = report.columns[0] === "output_frame" ? 0 : report.columns.indexOf("context_frame");
    const lipColumn = report.columns.indexOf("lip_minimum_cm2");
    const samples: LipSample[] = report.observations.map((row) => ({ frame: row[frameColumn], area: row[lipColumn] }));
    const lipMax = samples.reduce((max, { area }) => Math.max(max, area), closedArea);
    const speech = report.speech;
    const segments = "utterances" in speech
      ? speech.utterances.flatMap((utterance) => utterance.segments)
      : speech.phrases.flatMap((phrase) => phrase.timing.segments);
    return { samples, lipMax, segments, closed: sampledClosures(samples, closedArea, frames), envelope: pcmEnvelope(pcm) };
  }, [closedArea, frames, pcm, report]);

  const left = 18;
  const right = width - 18;
  const drawing = useMemo(() => {
    const x = (elapsed: number) => left + elapsed / frames * (right - left);
    const lip = source.samples.map(({ frame: index, area }) =>
      `${x(index + 1)},${LIP_BOTTOM - area / source.lipMax * (LIP_BOTTOM - LIP_TOP)}`).join(" ");
    const radius = (PCM_BOTTOM - PCM_TOP) / 2 / (source.envelope.peak || 1);
    const wave = source.envelope.bins.map(({ middle, high, low }) =>
      `M${x(middle)},${PCM_MIDDLE - high * radius}V${PCM_MIDDLE - low * radius}`).join(" ");
    return { x, lip, wave };
  }, [frames, left, right, source]);
  const { x } = drawing;
  const time = (frame + 1) / sampleRate;
  const active = source.segments.find(({ start_seconds, end_seconds }) => start_seconds <= time && time < end_seconds);
  const lip = observationAt(source.samples, frame, (sample) => sample.frame);
  const tract = report.tract;
  const profile = tract && observationAt(tract.rows, frame, (sample) => sample[0]);
  const divisions = width < 440 ? 4 : 5;
  return (
    <section className="ipa-timeline" aria-labelledby={titleId}>
      <h2 id={titleId}>発話の時系列</h2>
      <div ref={graph}>
        <svg viewBox={`0 0 ${width} ${HEIGHT}`} role="img" aria-label="音素区間・口唇断面積・PCM波形"
          onClick={(event) => {
            const bounds = event.currentTarget.getBoundingClientRect();
            const at = (event.clientX - bounds.left) * width / bounds.width;
            setFrame(Math.max(0, Math.min(frames - 1, Math.round((at - left) / (right - left) * frames) - 1)));
          }}>
          {Array.from({ length: divisions + 1 }, (_, i) => {
            const elapsed = i / divisions * frames;
            return <g key={i} className="timeline-grid">
              <line x1={x(elapsed)} y1={23} x2={x(elapsed)} y2={PCM_BOTTOM} />
              <text x={x(elapsed)} y={225} textAnchor={i === 0 ? "start" : i === divisions ? "end" : "middle"}>
                {(elapsed / sampleRate).toFixed(2)} s
              </text>
            </g>;
          })}
          <line data-timeline-axis="" x1={left} x2={right} y1={PCM_BOTTOM} y2={PCM_BOTTOM} className="timeline-guide" />
          {source.closed.map(({ from, to }) => (
            <rect key={from} data-lip-closed="" className="timeline-closed" x={x(from)} y={LIP_TOP}
              width={x(to) - x(from)} height={LIP_BOTTOM - LIP_TOP} />
          ))}
          <text x={left} y={16} className="timeline-label">計画音素</text>
          <text x={left} y={59} className="timeline-label">口唇の最小断面積（cm²）</text>
          <text x={right} y={59} textAnchor="end">{source.lipMax.toFixed(2)}</text>
          <line x1={left} x2={right} y1={LIP_BOTTOM} y2={LIP_BOTTOM} className="timeline-guide" />
          <polyline data-lip-series="" className="timeline-lip" points={drawing.lip} />
          <text x={left} y={140} className="timeline-label">PCM波形</text>
          <text x={right} y={140} textAnchor="end">±{source.envelope.peak.toFixed(3)}</text>
          <line x1={left} x2={right} y1={PCM_MIDDLE} y2={PCM_MIDDLE} className="timeline-guide" />
          <path data-pcm-envelope="" className="timeline-wave" d={drawing.wave} />
          {source.segments.map(({ segment, start_seconds, end_seconds }, i) => {
            const start = x(start_seconds * sampleRate);
            const end = x(end_seconds * sampleRate);
            const span = end - start;
            return <g key={i} className={active === source.segments[i] ? "timeline-phone active" : "timeline-phone"}>
              <rect data-phone={segment.ipa} x={start} y={23} width={span} height={20}>
                <title>{segment.ipa} {start_seconds.toFixed(3)}–{end_seconds.toFixed(3)} s</title>
              </rect>
              {span >= 19 && <text x={(start + end) / 2} y={37} textAnchor="middle">{segment.ipa}</text>}
            </g>;
          })}
          <line data-timeline-cursor="" x1={x(frame + 1)} y1={23} x2={x(frame + 1)} y2={PCM_BOTTOM}
            className="timeline-cursor" />
        </svg>
      </div>
      <label className="timeline-slider">出力フレーム
        <input type="range" min={0} max={frames - 1} step={1} value={frame}
          onChange={(event) => setFrame(event.currentTarget.valueAsNumber)} />
      </label>
      <dl className="timeline-values">
        <div><dt>フレーム</dt><dd data-timeline-frame="">{frame}</dd></div>
        <div><dt>出力時刻</dt><dd data-timeline-time="">{time.toFixed(6)} s</dd></div>
        <div><dt>計画音素</dt><dd data-timeline-phone="">{active?.segment.ipa ?? "—"}</dd></div>
        <div><dt>観測フレーム</dt><dd data-timeline-observation="">{lip?.frame ?? "—"}</dd></div>
        <div><dt>口唇最小断面積</dt><dd data-timeline-area="">{lip ? `${lip.area.toFixed(6)} cm²` : "—"}</dd></div>
      </dl>
      <p className="timeline-key">色付きの帯は閉鎖の観測区間（最小断面積 {closedArea} cm² 未満）です。</p>
      {tract && <TractProfileView profile={tract} row={profile} sampleRate={sampleRate} />}
      {tract?.grid && <SpeechTract3D
        sample={profile && tract.grid.frames[tract.rows.indexOf(profile)]}
        lipMinimum={profile?.at(-1)} sampleRate={sampleRate} />}
      {report.glottal && <GlottalScope trace={report.glottal} frame={frame} sampleRate={sampleRate} />}
      <SpeechSpectrum pcm={pcm} sampleRate={sampleRate} frame={frame} />
    </section>
  );
}
