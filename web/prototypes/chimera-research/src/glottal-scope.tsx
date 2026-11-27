import { useId, useMemo } from "react";
import experiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-glottal-scope.json";
import { GLOTTAL_COLUMNS } from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/fixed-voice";
import type { GlottalTrace } from "./fixed-worklet-types";

const LEFT = 27;
const RIGHT = 553;
const WIDTH = GLOTTAL_COLUMNS.length;

function range(values: number[]) {
  let area = 0.01;
  let flow = 1;
  for (let i = 0; i < values.length; i += WIDTH) {
    area = Math.max(area, values[i]);
    flow = Math.max(flow, Math.abs(values[i + 1]));
  }
  return [area, flow];
}

function format(value: number) {
  return value === 0 ? "0" : value.toPrecision(5);
}

export function GlottalScope({ trace, frame, sampleRate }: {
  trace: GlottalTrace; frame: number; sampleRate: number;
}) {
  const title = useId();
  const [areaLimit, flowLimit] = useMemo(() => range(trace.values), [trace]);
  const half = Math.round(experiment.measurement.half_window_seconds * sampleRate);
  const first = Math.max(0, frame - half);
  const last = Math.min(trace.values.length / WIDTH - 1, frame + half);
  const x = (index: number) => LEFT + (index - frame + half) * (RIGHT - LEFT) / (2 * half);
  const tracks = [
    { id: "area", label: "声門面積", unit: "cm²", top: 25, baseline: 70, limit: areaLimit },
    { id: "flow", label: "声門流量", unit: "cm³/s", top: 100, baseline: 125, limit: flowLimit },
  ] as const;
  const halfMs = (half * 1000 / sampleRate).toFixed(0);
  return (
    <section className="glottal-scope" aria-labelledby={title}
      data-glottal-frame={frame} data-glottal-first={first} data-glottal-last={last}>
      <h2 id={title}>声門波形</h2>
      <svg viewBox="0 0 580 181" role="img" aria-label="選択時刻の前後の声門面積と流量">
        {tracks.map(({ id, label, unit, top, baseline, limit }, column) => {
          const points = [];
          for (let i = first; i <= last; i++) {
            const y = baseline - (baseline - top) * trace.values[i * WIDTH + column] / limit;
            points.push(`${x(i)},${y}`);
          }
          const bottom = id === "area" ? baseline : 2 * baseline - top;
          return <g key={id}>
            <text className="tract-label" x={LEFT} y={top - 7}>{label} ({unit})</text>
            <text className="tract-label" x={RIGHT} y={top - 7} textAnchor="end">
              {id === "flow" ? "±" : "0–"}{format(limit)}
            </text>
            <line data-scope-axis={id} className="tract-axis" x1={LEFT} x2={RIGHT}
              y1={baseline} y2={baseline} />
            <line data-scope-range={id} className="tract-axis" x1={LEFT} x2={LEFT}
              y1={top} y2={bottom} />
            <polyline data-scope-wave={id} className={`glottal-${id}`} points={points.join(" ")} />
          </g>;
        })}
        <line data-scope-cursor="" className="tract-axis" x1={x(frame)} x2={x(frame)} y1={25} y2={150} />
        <text className="tract-label" x={LEFT} y={170}>−{halfMs} ms</text>
        <text className="tract-label" x={x(frame)} y={170} textAnchor="middle">0 ms</text>
        <text className="tract-label" x={RIGHT} y={170} textAnchor="end">+{halfMs} ms</text>
      </svg>
      <dl className="timeline-values tract-readout">
        <div><dt>選択時刻の面積</dt><dd data-scope-value="area">{format(trace.values[frame * WIDTH])} cm²</dd></div>
        <div><dt>選択時刻の流量</dt><dd data-scope-value="flow">{format(trace.values[frame * WIDTH + 1])} cm³/s</dd></div>
      </dl>
      <p className="timeline-key">0 msは選択時刻です。流量は気管から咽頭へ向かう方向が正です。</p>
    </section>
  );
}
