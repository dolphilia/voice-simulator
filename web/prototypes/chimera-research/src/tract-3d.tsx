import { useEffect, useRef, useState } from "react";
import trial from "../../../../research/experiments/chimera-rebuild/cases/worklet-tract-3d.json";
import { AREA_GRID_COLUMNS, FixedVoiceEngine, type FixedVoiceInput } from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/fixed-voice";
import { loadFixedModule } from "./render-fixed-voice";
import type { createTractScene, TractView } from "./tract-3d-scene";

type Model = {
  variant: string;
  rows: number[][];
  createScene: typeof createTractScene;
};

const viewLabels = { angled: "斜め", side: "側面", front: "口側" } as const;

export function Tract3DPanel({ input }: { input: FixedVoiceInput }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const scene = useRef<ReturnType<typeof createTractScene>>(undefined);
  const [selection, setSelection] = useState(trial.measurement.variants[0].id);
  const [section, setSection] = useState(0);
  const [view, setView] = useState<TractView>("angled");
  const [model, setModel] = useState<Model>();
  const [download, setDownload] = useState<string>();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  async function open(id: string) {
    const variant = trial.measurement.variants.find((item) => item.id === id);
    if (!variant) return;
    setError("");
    setPending(true);
    setModel(undefined);
    setSection(0);
    try {
      const [module, { createTractScene }] = await Promise.all([loadFixedModule(), import("./tract-3d-scene")]);
      const posture = { ...input.posture,
        lip_aperture_cm: variant.lip_aperture_cm ?? input.posture.lip_aperture_cm };
      const engine = new FixedVoiceEngine(module, { ...input, posture });
      try {
        setModel({ variant: id, rows: engine.readFixedAreaGrid(), createScene: createTractScene });
      } finally {
        engine.close();
      }
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setPending(false);
    }
  }

  useEffect(() => {
    if (!model || !canvas.current) return;
    let drawing: ReturnType<typeof createTractScene>;
    try {
      drawing = model.createScene(canvas.current, model.rows, trial.measurement.ring_segments);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
      return;
    }
    scene.current = drawing;
    const data = {
      caseId: trial.id,
      variant: model.variant,
      columns: AREA_GRID_COLUMNS,
      rows: model.rows,
      ringSegments: trial.measurement.ring_segments,
      vertices: drawing.snapshot(),
    };
    const url = URL.createObjectURL(new Blob([JSON.stringify(data) + "\n"], { type: "application/json" }));
    setDownload(url);
    return () => {
      scene.current = undefined;
      drawing.close();
      URL.revokeObjectURL(url);
      setDownload(undefined);
    };
  }, [model]);
  useEffect(() => scene.current?.move(view), [model, view]);
  useEffect(() => scene.current?.select(section), [model, section]);

  const row = model?.rows[section];
  return <section aria-labelledby="tract-3d-title" className="tract-3d">
    <h2 id="tract-3d-title">声道の三次元断面</h2>
    <div className="controls">
      <label>姿勢{" "}
        <select aria-label="姿勢" value={selection} disabled={pending} onChange={(event) => {
          const next = event.target.value;
          setSelection(next);
          if (model) void open(next);
        }}>
          {trial.measurement.variants.map(({ id, label }) => <option key={id} value={id}>{label}</option>)}
        </select>
      </label>{" "}
      {model ? <button type="button" onClick={() => { setError(""); setModel(undefined); }}>表示を閉じる</button>
        : <button type="button" onClick={() => void open(selection)} disabled={pending}>三次元表示を開く</button>}
    </div>
    {pending && <p role="status">測定線を読み込み中</p>}
    {error && <p role="alert">三次元表示を開始できませんでした。{error}</p>}
    {row && model && <>
      <canvas key={model.variant} ref={canvas} role="img" aria-label="正中矢状面に沿った声道の楕円断面" />
      <div className="controls">
        {(Object.keys(viewLabels) as TractView[]).map((id) =>
          <button type="button" key={id} aria-pressed={view === id} onClick={() => setView(id)}>{viewLabels[id]}</button>)}
        <label>測定線{" "}
          <select aria-label="測定線" value={section} onChange={(event) => setSection(Number(event.target.value))}>
            {model.rows.map((point, index) =>
              <option key={index} value={index}>{index + 1}・{point[10].toFixed(2)} cm</option>)}
          </select>
        </label>
      </div>
      <dl className="timeline-values">
        <div><dt>声門からの距離</dt><dd data-section-distance={row[10]}>{row[10].toFixed(3)} cm</dd></div>
        <div><dt>有効隙間</dt><dd data-section-gap={row[8]}>{row[8].toFixed(3)} cm</dd></div>
        <div><dt>計算面積</dt><dd data-section-area={row[9]}>{row[9].toFixed(4)} cm²</dd></div>
      </dl>
      <p>ドラッグで回転し、ホイールやピンチで拡大できます。橙色のリングが選択中の測定線です。</p>
      {download && <a href={download} download={`tract-3d-${model.variant}.json`}>三次元観測JSONを保存</a>}
    </>}
  </section>;
}
