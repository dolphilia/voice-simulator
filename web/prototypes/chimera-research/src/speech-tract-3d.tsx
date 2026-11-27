import { useEffect, useId, useRef, useState } from "react";
import { AREA_GRID_COLUMNS } from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/fixed-voice";
import trial from "../../../../research/experiments/chimera-rebuild/cases/worklet-tract-3d.json";
import type { TractGridSample } from "./fixed-worklet-types";
import type { createTractScene, TractView } from "./tract-3d-scene";

const ringSegments = trial.measurement.ring_segments;
const viewLabels = { angled: "斜め", side: "側面", front: "口側" } as const;

export function SpeechTract3D({ sample, lipMinimum, sampleRate, live = false, contextFrame, onPrepared }: {
  sample?: TractGridSample;
  lipMinimum?: number;
  sampleRate: number;
  live?: boolean;
  contextFrame?: number;
  onPrepared?: (ready: boolean) => void;
}) {
  const title = useId();
  const canvas = useRef<HTMLCanvasElement>(null);
  const scene = useRef<ReturnType<typeof createTractScene>>(undefined);
  const needsFit = useRef(false);
  const drawnFrame = useRef<number | undefined>(undefined);
  const currentView = useRef<TractView>("angled");
  const [create, setCreate] = useState<typeof createTractScene>();
  const [view, setView] = useState<TractView>("angled");
  const [drawn, setDrawn] = useState<{ sample: TractGridSample; url?: string }>();
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    const target = canvas.current;
    // 比較器から要求されたときに、最後に描画した断面の頂点を読む。
    const read = (event: Event) => {
      const reply = (event as CustomEvent).detail;
      if (drawnFrame.current === undefined || !scene.current || typeof reply !== "function") return;
      reply({ frame: drawnFrame.current, ringSegments, vertices: scene.current.snapshot(), marker: scene.current.selectedMarker() });
    };
    if (live) target?.addEventListener("chimera:read-live-tract", read);
    import("./tract-3d-scene").then(({ createTractScene, warmTractScene }) => {
      if (!active) return;
      if (live && canvas.current) {
        scene.current = warmTractScene(canvas.current, trial.measurement.expected_sections, ringSegments);
        needsFit.current = true;
      }
      setCreate(() => createTractScene);
      onPrepared?.(true);
    }).catch((failure) => {
      if (!active) return;
      scene.current?.close();
      scene.current = undefined;
      setError(String(failure));
      onPrepared?.(true);
    });
    return () => {
      active = false;
      target?.removeEventListener("chimera:read-live-tract", read);
      scene.current?.close();
      scene.current = undefined;
      drawnFrame.current = undefined;
      needsFit.current = false;
    };
  }, [live, onPrepared]);

  useEffect(() => {
    if (!sample) {
      needsFit.current = live;
      drawnFrame.current = undefined;
      return;
    }
    if (!create || !canvas.current) return;
    drawnFrame.current = undefined;
    setError("");
    try {
      const existing = scene.current;
      const drawing = existing ?? create(canvas.current, sample.rows, ringSegments);
      if (existing) {
        drawing.replace(sample.rows);
        if (needsFit.current) {
          drawing.fit(currentView.current);
          needsFit.current = false;
        }
      }
      else drawing.move(currentView.current);
      scene.current = drawing;
      drawing.select(sample.rows.length - 1);
      if (live) {
        drawnFrame.current = sample.frame;
        setDrawn({ sample });
        return;
      }
      const data = {
        frame: sample.frame,
        elapsedSeconds: (sample.frame + 1) / sampleRate,
        columns: AREA_GRID_COLUMNS,
        rows: sample.rows,
        lipMinimumAcousticAreaCm2: lipMinimum,
        ringSegments,
        vertices: drawing.snapshot(),
      };
      const url = URL.createObjectURL(new Blob([JSON.stringify(data) + "\n"], { type: "application/json" }));
      setDrawn({ sample, url });
      return () => URL.revokeObjectURL(url);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  }, [create, sample, lipMinimum, sampleRate, live]);

  const last = sample?.rows.at(-1);
  const active = Boolean(sample && !error);
  return <section aria-labelledby={title} className="tract-3d">
    <h3 id={title}>{live ? "実時間の三次元断面" : "発話の三次元断面"}</h3>
    {!sample && !error && <p data-speech-grid-missing="">{live ? (create
      ? "実時間発声の観測を待っています。" : "三次元表示を準備しています。")
      : "この出力フレーム以前に三次元断面の観測がありません。"}</p>}
    {sample && !create && !error && <p role="status">三次元表示を準備中</p>}
    {(sample || live) && error && <p role="alert">三次元断面を描画できませんでした。{error}</p>}
    <div hidden={!live && !active} style={live && !active ? { visibility: "hidden" } : undefined}>
      <canvas ref={canvas} role="img" aria-label="観測時刻の声道の楕円断面" />
    </div>
    {active && last && drawn && drawn.sample === sample && <>
      <div className="controls">
        {(Object.keys(viewLabels) as TractView[]).map((id) =>
          <button type="button" key={id} aria-pressed={view === id} onClick={() => {
            currentView.current = id;
            setView(id);
            scene.current?.move(id);
          }}>{viewLabels[id]}</button>)}
      </div>
      <dl className="timeline-values">
        <div><dt>観測フレーム</dt><dd data-speech-grid-frame={sample.frame}
          data-live-context-frame={live ? contextFrame : undefined}
          data-live-lip-area={live ? lipMinimum : undefined}>{sample.frame}</dd></div>
        <div><dt>測定線末端の隙間</dt><dd>{last[8].toFixed(4)} cm</dd></div>
        <div><dt>測定線末端の面積</dt><dd>{last[9].toFixed(6)} cm²</dd></div>
        <div><dt>唇端音響セルの最小面積</dt><dd>{lipMinimum?.toFixed(6)} cm²</dd></div>
      </dl>
      <p>橙色は末端の測定線です。完全に閉じると点で示します。音響セルの値は同じ出力時刻での補間後の状態です。</p>
      {drawn.url && <a href={drawn.url} download={`tract-3d-frame-${sample.frame}.json`}>発話の三次元観測JSONを保存</a>}
    </>}
  </section>;
}
