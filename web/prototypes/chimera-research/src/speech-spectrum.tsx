import { useEffect, useId, useMemo, useState } from "react";
import experiment from "../../../../research/experiments/chimera-rebuild/cases/worklet-pcm-spectrum.json";
import { pcmSpectrum } from "./pcm-spectrum";

const LEFT = 45;
const RIGHT = 553;
const TOP = 20;
const BOTTOM = 155;
const [MIN_HZ, MAX_HZ] = experiment.measurement.frequency_range_hz;
const MIN_DB = experiment.measurement.display_min_dbfs;

export function SpeechSpectrum({ pcm, sampleRate, frame }: {
  pcm: Float32Array; sampleRate: number; frame: number;
}) {
  const title = useId();
  const spectrum = useMemo(() => pcmSpectrum(pcm, sampleRate, frame), [pcm, sampleRate, frame]);
  const [download, setDownload] = useState<{ spectrum: typeof spectrum; url: string }>();
  useEffect(() => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(spectrum) + "\n"], { type: "application/json" }));
    setDownload({ spectrum, url });
    return () => URL.revokeObjectURL(url);
  }, [spectrum]);
  const { amplitudes, fftSize, sourceFirstFrame, sourceEndFrame } = spectrum;
  const binHz = sampleRate / fftSize;
  const maxHz = Math.min(MAX_HZ, sampleRate / 2);
  const x = (hz: number) => LEFT + (RIGHT - LEFT) * Math.log(hz / MIN_HZ) / Math.log(maxHz / MIN_HZ);
  const y = (db: number) => TOP + (BOTTOM - TOP) * Math.max(MIN_DB, Math.min(0, db)) / MIN_DB;
  const points: string[] = [];
  let peak = 0;
  let peakBin = 0;
  const last = Math.floor(maxHz / binHz);
  for (let k = Math.ceil(MIN_HZ / binHz); k <= last; k++) {
    const amplitude = amplitudes[k];
    points.push(`${x(k * binHz)},${y(20 * Math.log10(amplitude))}`);
    if (amplitude > peak) {
      peak = amplitude;
      peakBin = k;
    }
  }
  const peakHz = peakBin * binHz;
  const peakDb = 20 * Math.log10(peak);

  return (
    <section className="speech-spectrum" aria-labelledby={title} data-spectrum-frame={frame}>
      <h2 id={title}>PCMスペクトル</h2>
      <svg viewBox="0 0 580 185" role="img" aria-label="選択時刻の周波数別PCM振幅">
        <rect data-spectrum-axis="" x={LEFT} y={TOP} width={RIGHT - LEFT} height={BOTTOM - TOP}
          fill="none" stroke="none" />
        {[MIN_DB, -90, -60, -30, 0].map((db) => (
          <g key={db}>
            <line className="tract-axis" x1={LEFT} x2={RIGHT} y1={y(db)} y2={y(db)} />
            <text className="tract-label" x={LEFT - 4} y={y(db) + 4} textAnchor="end">{db}</text>
          </g>
        ))}
        <text className="tract-label" x={LEFT} y={15}>dBFS</text>
        {[100, 200, 500, 1000, 2000, 5000].filter((hz) => hz <= maxHz).map((hz) => (
          <g key={hz}>
            <line className="tract-axis" x1={x(hz)} x2={x(hz)} y1={TOP} y2={BOTTOM} />
            <text className="tract-label" x={x(hz)} y={176} textAnchor="middle">
              {hz >= 1000 ? `${hz / 1000}k` : hz}
            </text>
          </g>
        ))}
        <text className="tract-label" x={RIGHT} y={176} textAnchor="end">Hz</text>
        <polyline data-spectrum-line="" className="spectrum-line" points={points.join(" ")} />
        {peak && peakDb >= MIN_DB ? <circle className="spectrum-peak" cx={x(peakHz)} cy={y(peakDb)} r={3} /> : null}
      </svg>
      <dl className="timeline-values tract-readout">
        <div><dt>入力</dt><dd data-spectrum-source="">保存WAVと同じPCM</dd></div>
        <div><dt>窓の長さ</dt><dd>{(1000 * fftSize / sampleRate).toFixed(2)} ms</dd></div>
        <div><dt>取得フレーム数</dt><dd data-spectrum-samples="">{sourceEndFrame - sourceFirstFrame} / {fftSize}</dd></div>
        <div><dt>表示帯域の最大値</dt><dd data-spectrum-peak="">
          {peak ? `${peakHz.toFixed(2)} Hz · ${peakDb.toFixed(2)} dBFS` : "—"}
        </dd></div>
      </dl>
      {download?.spectrum === spectrum &&
        <a href={download.url} download={`pcm-spectrum-${frame}.json`}>スペクトルJSONを保存</a>}
    </section>
  );
}
