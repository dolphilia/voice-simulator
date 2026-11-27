import { useMemo, useState } from "react";
import { TRACT_ACOUSTIC_WORDS } from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/fixed-voice";

type CellBounds = { start: number; end: number };

function limits(rows: number[][]): [number, number] {
  let pressure = 1;
  let flow = 1;
  for (const row of rows) {
    for (let i = 1; i < row.length; i += TRACT_ACOUSTIC_WORDS) {
      pressure = Math.max(pressure, Math.abs(row[i]));
      flow = Math.max(flow, Math.abs(row[i + 1]));
    }
  }
  return [pressure, flow];
}

function format(value: number) {
  return value === 0 ? "0" : value.toPrecision(5);
}

export function TractAcoustics({ rows, row, cells, pharynxCount, axisRight }: {
  rows: number[][];
  row: number[];
  cells: CellBounds[];
  pharynxCount: number;
  axisRight: number;
}) {
  const [pressureLimit, flowLimit] = useMemo(() => limits(rows), [rows]);
  const [selected, setSelected] = useState(cells.length - 1);
  const cellIndex = Math.min(selected, cells.length - 1);
  const index = 1 + TRACT_ACOUSTIC_WORDS * cellIndex;
  const tracks = [
    { id: "pressure", label: "節点圧力", unit: "dyn/cm²", limit: pressureLimit, center: 50 },
    { id: "flow", label: "口側境界の流量", unit: "cm³/s", limit: flowLimit, center: 127 },
  ] as const;
  const span = 24;
  const axisLeft = cells[0].start;
  return (
    <>
      <svg className="tract-signed-plots" viewBox="0 0 580 158" role="img"
        aria-label="声道セルの節点圧力と口側境界の符号付き流量">
        {tracks.map(({ id, label, unit, limit, center }, column) => (
          <g key={id} className={`tract-${id}`}>
            <text className="tract-label" x={axisLeft} y={center - 32}>{label} ({unit})</text>
            <text className="tract-label" x={axisRight} y={center - 32} textAnchor="end">±{format(limit)}</text>
            <line data-acoustic-zero={id} className="tract-axis" x1={axisLeft} x2={axisRight}
              y1={center} y2={center} />
            <line data-acoustic-range={id} className="tract-axis" x1={axisLeft} x2={axisLeft}
              y1={center - span} y2={center + span} />
            {cells.map(({ start, end }, i) => {
              const x = id === "pressure" ? (start + end) / 2 : end;
              const value = row[1 + TRACT_ACOUSTIC_WORDS * i + column];
              const y = center - span * value / limit;
              return <g key={i}>
                <line x1={x} x2={x} y1={center} y2={y} className="tract-acoustic-stem" />
                <circle data-acoustic-point={id} cx={x} cy={y} r={i === cellIndex ? 3.6 : 2.2} />
              </g>;
            })}
          </g>
        ))}
      </svg>
      <label className="tract-cell-choice">
        観測セル
        <select value={cellIndex} onChange={(event) => setSelected(Number(event.currentTarget.value))}>
          {cells.map((_, i) => (
            <option key={i} value={i}>
              {i < pharynxCount ? `咽頭 ${i + 1}` : `口腔 ${i - pharynxCount + 1}`}
              {i === cells.length - 1 ? "（口端）" : ""}
            </option>
          ))}
        </select>
      </label>
      <dl className="timeline-values tract-readout">
        <div><dt>節点圧力</dt><dd data-acoustic-value="pressure">{format(row[index])} dyn/cm²</dd></div>
        <div><dt>口側境界の流量</dt><dd data-acoustic-value="flow">{format(row[index + 1])} cm³/s</dd></div>
      </dl>
      <p className="timeline-key">流量の正方向は口端側です。</p>
    </>
  );
}
