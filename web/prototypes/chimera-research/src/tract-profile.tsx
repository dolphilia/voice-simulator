import { useId, useMemo } from "react";
import type { TractProfile } from "./fixed-worklet-types";
import { TractAcoustics } from "./tract-acoustics";

const AXIS_LEFT = 27;
const AXIS_RIGHT = 553;
const CENTER = 74;
const HALF_HEIGHT = 48;

function bounds(profile: TractProfile) {
  let length = 0;
  let area = 0;
  for (const row of profile.rows) {
    let end = 0;
    for (let i = 1; i < row.length; i += 3) {
      end += row[i];
      area = Math.max(area, row[i + 1]);
    }
    length = Math.max(length, end);
  }
  return { length, area };
}

export function TractProfileView({ profile, row, sampleRate }: {
  profile: TractProfile; row?: number[]; sampleRate: number;
}) {
  const title = useId();
  const limits = useMemo(() => bounds(profile), [profile]);
  const [pharynxCount, oralCount] = profile.counts;
  const x = (cm: number) => AXIS_LEFT + cm / limits.length * (AXIS_RIGHT - AXIS_LEFT);
  // 円形としたときの相当直径に比例する。面積の参照値は録音全体で共通。
  const radius = (cm2: number) => HALF_HEIGHT * Math.sqrt(cm2 / limits.area);
  const acoustics = profile.acoustics;
  const acousticRow = row && acoustics?.rows[profile.rows.indexOf(row)];
  let length = 0;
  const cells = row && Array.from({ length: pharynxCount + oralCount }, (_, i) => {
    const offset = 1 + 3 * i;
    const dx = row[offset];
    const area = row[offset + 1];
    const minimum = row[offset + 2];
    const start = x(length);
    length += dx;
    return { start, end: x(length), area, minimum };
  });
  return (
    <section className="tract-profile" aria-labelledby={title}>
      <h2 id={title}>声道断面</h2>
      {cells && row ? <>
        <dl className="timeline-values tract-readout">
          <div><dt>観測フレーム</dt><dd data-tract-frame="">{row[0]}</dd></div>
          <div><dt>観測時刻</dt><dd>{((row[0] + 1) / sampleRate).toFixed(6)} s</dd></div>
          <div><dt>声門から口端まで</dt><dd>{length.toFixed(3)} cm</dd></div>
        </dl>
        <svg viewBox="0 0 580 155" role="img" aria-label="声門から口端までの音響格子の断面">
          <line data-tract-x-axis="" className="tract-axis" x1={AXIS_LEFT} x2={AXIS_RIGHT}
            y1={CENTER} y2={CENTER} />
          <line data-tract-y-axis="" className="tract-axis" x1={AXIS_LEFT} x2={AXIS_LEFT}
            y1={CENTER - HALF_HEIGHT} y2={CENTER + HALF_HEIGHT} />
          <text className="tract-label" x={(AXIS_LEFT + cells[pharynxCount].start) / 2}
            y={17} textAnchor="middle">咽頭</text>
          <text className="tract-label" x={(cells[pharynxCount].start + x(length)) / 2}
            y={17} textAnchor="middle">口腔</text>
          {cells.map(({ start, end, area, minimum }, i) => (
            <g key={i}>
              <rect data-tract-average="" className="tract-average" x={start} width={end - start}
                y={CENTER - radius(area)} height={2 * radius(area)}>
                <title>{i < pharynxCount ? "咽頭" : "口腔"} {i < pharynxCount ? i + 1 : i - pharynxCount + 1}
                  { ` 平均 ${area.toFixed(5)} cm²・最小 ${minimum.toFixed(5)} cm²` }</title>
              </rect>
              <rect data-tract-minimum="" className="tract-minimum" x={start} width={end - start}
                y={CENTER - radius(minimum)} height={2 * radius(minimum)} />
            </g>
          ))}
          <line className="tract-junction" x1={cells[pharynxCount].start} x2={cells[pharynxCount].start}
            y1={CENTER - HALF_HEIGHT} y2={CENTER + HALF_HEIGHT} />
          <text className="tract-label" x={AXIS_LEFT} y={142}>声門</text>
          <text className="tract-label" x={x(length)} y={142} textAnchor="end">口端</text>
        </svg>
        <p className="tract-legend"><span>平均断面</span><span>最小断面</span><span>高さは相当直径</span></p>
        {acoustics && acousticRow && acousticRow[0] === row[0] &&
          <TractAcoustics rows={acoustics.rows} row={acousticRow} cells={cells}
            pharynxCount={pharynxCount} axisRight={AXIS_RIGHT} />}
      </> : <p data-tract-missing="">選択したフレームまでに断面の観測はありません。</p>}
    </section>
  );
}
