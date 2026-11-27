import { useEffect, useMemo, useRef, useState } from "react";
import { RADIATION_COLUMNS } from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/fixed-voice";

const WIDTH = 960;
const HEIGHT = 92;
const ZOOM_MS = 20;
const PCM = [{ index: 0, label: "PCM", color: "#255b83" }];
const FLOWS = [
  { index: 3, label: "合算", color: "#3d4758" },
  { index: 0, label: "壁", color: "#006c60" },
  { index: 1, label: "口端", color: "#985014" },
  { index: 2, label: "鼻端", color: "#704292" },
];
const DERIVATIVE = [{ index: 4, label: "放射微分", color: "#255b83" }];
const READOUT = [PCM[0], FLOWS[1], FLOWS[2], FLOWS[3], FLOWS[0], DERIVATIVE[0]];

type Series = { index: number; label: string; color: string };
type Radiation = { columns: typeof RADIATION_COLUMNS; values: number[] };

function formatValue(value: number): string {
  return value === 0 ? "0" : value.toPrecision(8);
}

function TraceLane({ values, stride, series, label, unit, first, count, cursor, selectFrame }: {
  values: ArrayLike<number>; stride: number; series: readonly Series[]; label: string; unit: string;
  first: number; count: number; cursor: number; selectFrame: (frame: number) => void;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const peak = useMemo(() => {
    let maximum = 0;
    for (let frame = first; frame < first + count; frame++) {
      for (const { index } of series) maximum = Math.max(maximum, Math.abs(values[frame * stride + index]));
    }
    return maximum || 1;
  }, [values, stride, series, first, count]);
  const divideBy = Math.max(1, count - 1);
  useEffect(() => {
    const context = canvas.current?.getContext("2d");
    if (!context) return;
    const middle = HEIGHT / 2;
    const y = (value: number) => middle - value * (middle - 3) / peak;
    context.clearRect(0, 0, WIDTH, HEIGHT);
    context.strokeStyle = "#c9d5d0";
    context.beginPath();
    context.moveTo(0, middle + 0.5);
    context.lineTo(WIDTH, middle + 0.5);
    context.stroke();
    for (const { index, color } of series) {
      const at = (offset: number) => values[(first + offset) * stride + index];
      context.strokeStyle = color;
      context.beginPath();
      if (count <= WIDTH) {
        context.moveTo(0.5, y(at(0)));
        for (let offset = 1; offset < count; offset++) {
          context.lineTo(0.5 + offset * (WIDTH - 1) / divideBy, y(at(offset)));
        }
      } else {
        // 画素に入る全標本の最小値・最大値を残す。
        for (let pixel = 0; pixel < WIDTH; pixel++) {
          const begin = Math.floor(pixel * count / WIDTH);
          const end = Math.floor((pixel + 1) * count / WIDTH);
          let low = at(begin);
          let high = low;
          for (let offset = begin + 1; offset < end; offset++) {
            const value = at(offset);
            low = Math.min(low, value);
            high = Math.max(high, value);
          }
          context.moveTo(pixel + 0.5, y(high));
          context.lineTo(pixel + (low === high ? 1.5 : 0.5), y(low));
        }
      }
      context.stroke();
    }
  }, [values, stride, series, first, count, divideBy, peak]);

  return (
    <figure className="radiation-trace">
      <figcaption>
        <strong>{label}</strong>
        <span>±{Number(peak.toPrecision(4))} {unit}</span>
      </figcaption>
      <div className="radiation-trace-data">
        <canvas width={WIDTH} height={HEIGHT} ref={canvas} role="img" aria-label={`${label}の時系列`}
          onClick={(event) => {
            const { left, width } = event.currentTarget.getBoundingClientRect();
            const position = Math.max(0, Math.min(1, (event.clientX - left) / width));
            selectFrame(first + Math.round(position * (count - 1)));
          }} />
        <span className="radiation-cursor" style={{ left: `${100 * (cursor - first) / divideBy}%` }} aria-hidden="true" />
      </div>
    </figure>
  );
}

export function RadiationScope({ pcm, sampleRate, radiation }: {
  pcm: Float32Array; sampleRate: number; radiation: Radiation;
}) {
  const [frame, setFrame] = useState(0);
  const [zoom, setZoom] = useState(false);
  const stride = radiation.columns.length;
  const zoomFrames = Math.max(1, Math.round(sampleRate * ZOOM_MS / 1000));
  const first = zoom ? Math.floor(frame / zoomFrames) * zoomFrames : 0;
  const end = zoom ? Math.min(first + zoomFrames, pcm.length) : pcm.length;
  const time = (index: number) => (index * 1000 / sampleRate).toFixed(5);
  const range = { first, count: end - first, cursor: frame, selectFrame: setFrame };

  return (
    <section className="radiation-scope" aria-labelledby="radiation-scope-title">
      <h2 id="radiation-scope-title">PCMと放射流量</h2>
      <div className="radiation-controls">
        <label htmlFor="radiation-frame">出力フレーム</label>
        <output htmlFor="radiation-frame"><data value={frame}>{frame}</data> · <span>{time(frame)} ms</span></output>
        <input id="radiation-frame" type="range" min={0} max={pcm.length - 1} step={1} value={frame}
          aria-valuetext={`${frame}フレーム、${time(frame)} ms`}
          onChange={(event) => setFrame(event.target.valueAsNumber)} />
        <label>表示範囲
          <select value={zoom ? "zoom" : "all"} onChange={(event) => setZoom(event.target.value === "zoom")}>
            <option value="all">全区間</option>
            <option value="zoom">{ZOOM_MS} ms</option>
          </select>
        </label>
      </div>
      <TraceLane values={pcm} stride={1} series={PCM} label="PCM" unit="振幅" {...range} />
      <TraceLane values={radiation.values} stride={stride} series={FLOWS} label="放射成分" unit="cm³/s" {...range} />
      <TraceLane values={radiation.values} stride={stride} series={DERIVATIVE} label="放射微分" unit="cm³/s²" {...range} />
      <div className="radiation-time-axis" aria-label="グラフの時刻範囲">
        <span>{time(first)} ms</span><span>{time(end - 1)} ms</span>
      </div>
      <dl className="radiation-readout" aria-label="選択フレームの値">
        {READOUT.map(({ label, index, color }, i) => {
          const value = i === 0 ? pcm[frame] : radiation.values[frame * stride + index];
          const unit = i === 0 ? "振幅" : i === READOUT.length - 1 ? "cm³/s²" : "cm³/s";
          return <div key={label}>
            <dt><span style={{ backgroundColor: color }} aria-hidden="true" />{label}</dt>
            <dd><data value={value}>{formatValue(value)}</data> <span>{unit}</span></dd>
          </div>;
        })}
      </dl>
    </section>
  );
}
