import { WaveguideEngine } from "../audio/engine";
import { VOWEL_PRESETS, VOWEL_LABELS, VOWEL_ORDER, type VowelId } from "../audio/vowel-presets";
import { TractEditor } from "./tract-editor";
import { SpectrumView } from "./spectrum-view";

export function createApp(root: HTMLElement): void {
  const engine = new WaveguideEngine("a");

  // ── DOM ──────────────────────────────────────────────────────────
  root.innerHTML = `
    <div class="app">
      <header class="header">
        <h1 class="title">声道波動管モデル</h1>
        <button id="toggleBtn" class="btn btn-primary">▶ スタート</button>
      </header>

      <section class="editor-section">
        <div class="section-label">
          声道形状エディタ
          <span class="hint" id="editorHint">制御点（青い丸）をドラッグして形状を変えてください</span>
        </div>
        <canvas id="tractCanvas" class="tract-canvas" width="720" height="190"></canvas>

        <div class="editor-toolbar">
          <div class="mode-toggle">
            <button id="modeManual" class="btn btn-mode active">手動編集</button>
            <button id="modeMagnet" class="btn btn-mode">マグネット</button>
          </div>
          <div class="magnet-controls" id="magnetControls">
            <div class="control-row">
              <label class="control-label">影響範囲</label>
              <input id="magnetRadiusSlider" type="range" min="20" max="300" value="100" step="5" class="slider" />
              <span id="magnetRadiusVal" class="control-value">100 px</span>
            </div>
            <div class="control-row">
              <label class="control-label">効力</label>
              <input id="magnetStrengthSlider" type="range" min="10" max="300" value="100" step="5" class="slider" />
              <span id="magnetStrengthVal" class="control-value">1.00</span>
            </div>
          </div>
        </div>
      </section>

      <section class="preset-section">
        <div class="section-label">母音プリセット</div>
        <div class="preset-btns" id="presetBtns">
          ${VOWEL_ORDER.map(v => `
            <button class="btn btn-vowel ${v === "a" ? "active" : ""}" data-vowel="${v}">
              ${VOWEL_LABELS[v]} <span class="vowel-sub">/${v}/</span>
            </button>
          `).join("")}
        </div>
      </section>

      <section class="control-section">
        <div class="control-group-label">基本パラメータ</div>
        <div class="control-row">
          <label class="control-label">ピッチ</label>
          <input id="pitchSlider" type="range" min="80" max="400" value="220" step="1" class="slider" />
          <span id="pitchVal" class="control-value">220 Hz</span>
        </div>
        <div class="control-row">
          <label class="control-label">ゲイン</label>
          <input id="gainSlider" type="range" min="1" max="25" value="12" step="1" class="slider" />
          <span id="gainVal" class="control-value">0.12</span>
        </div>
        <div class="control-group-label lf-label">声帯パラメータ（LF モデル）</div>
        <div class="control-row">
          <label class="control-label">Rg <span class="param-hint">開口比</span></label>
          <input id="rgSlider" type="range" min="50" max="200" value="100" step="1" class="slider" />
          <span id="rgVal" class="control-value">1.00</span>
        </div>
        <div class="control-row">
          <label class="control-label">Rk <span class="param-hint">非対称比</span></label>
          <input id="rkSlider" type="range" min="10" max="60" value="30" step="1" class="slider" />
          <span id="rkVal" class="control-value">0.30</span>
        </div>
      </section>

      <section class="spectrum-section">
        <div class="section-label">
          スペクトラム
          <span id="formantInfo" class="formant-info"></span>
        </div>
        <canvas id="spectrumCanvas" class="spectrum-canvas" width="720" height="150"></canvas>
      </section>
    </div>
  `;

  // ── 要素取得 ─────────────────────────────────────────────────────
  const toggleBtn          = root.querySelector<HTMLButtonElement>("#toggleBtn")!;
  const tractCanvas        = root.querySelector<HTMLCanvasElement>("#tractCanvas")!;
  const specCanvas         = root.querySelector<HTMLCanvasElement>("#spectrumCanvas")!;
  const pitchSlider        = root.querySelector<HTMLInputElement>("#pitchSlider")!;
  const gainSlider         = root.querySelector<HTMLInputElement>("#gainSlider")!;
  const rgSlider           = root.querySelector<HTMLInputElement>("#rgSlider")!;
  const rkSlider           = root.querySelector<HTMLInputElement>("#rkSlider")!;
  const pitchVal           = root.querySelector<HTMLSpanElement>("#pitchVal")!;
  const gainVal            = root.querySelector<HTMLSpanElement>("#gainVal")!;
  const rgVal              = root.querySelector<HTMLSpanElement>("#rgVal")!;
  const rkVal              = root.querySelector<HTMLSpanElement>("#rkVal")!;
  const presetBtns         = root.querySelector<HTMLDivElement>("#presetBtns")!;
  const formantInfo        = root.querySelector<HTMLSpanElement>("#formantInfo")!;
  const modeManualBtn      = root.querySelector<HTMLButtonElement>("#modeManual")!;
  const modeMagnetBtn      = root.querySelector<HTMLButtonElement>("#modeMagnet")!;
  const magnetControls     = root.querySelector<HTMLDivElement>("#magnetControls")!;
  const magnetRadiusSlider = root.querySelector<HTMLInputElement>("#magnetRadiusSlider")!;
  const magnetStrengthSlider = root.querySelector<HTMLInputElement>("#magnetStrengthSlider")!;
  const magnetRadiusVal    = root.querySelector<HTMLSpanElement>("#magnetRadiusVal")!;
  const magnetStrengthVal  = root.querySelector<HTMLSpanElement>("#magnetStrengthVal")!;
  const editorHint         = root.querySelector<HTMLSpanElement>("#editorHint")!;

  // ── 声道エディタ ─────────────────────────────────────────────────
  const tractEditor = new TractEditor(
    tractCanvas,
    VOWEL_PRESETS["a"],
    (areas) => {
      engine.setAreas(areas);
      updateFormants();
    }
  );

  // ── スペクトラム表示 ─────────────────────────────────────────────
  const specView = new SpectrumView(specCanvas);

  function updateFormants(): void {
    const f = engine.getFormants();
    specView.setFormants(f);
    formantInfo.textContent = f.map((v, i) => `F${i + 1}: ${Math.round(v)} Hz`).join("  ");
  }
  updateFormants();

  // ── スタート / ストップ ──────────────────────────────────────────
  toggleBtn.addEventListener("click", async () => {
    if (!engine.isRunning) {
      toggleBtn.disabled = true;
      toggleBtn.textContent = "起動中...";
      try {
        await engine.start();
        const an = engine.analyser;
        if (an) specView.setAnalyser(an);
        specView.start();
        toggleBtn.textContent = "■ ストップ";
        toggleBtn.classList.replace("btn-primary", "btn-stop");
      } catch (e) {
        console.error(e);
        toggleBtn.textContent = "▶ スタート";
      }
      toggleBtn.disabled = false;
    } else {
      engine.stop();
      specView.stop();
      toggleBtn.textContent = "▶ スタート";
      toggleBtn.classList.replace("btn-stop", "btn-primary");
    }
  });

  // ── 母音プリセット ───────────────────────────────────────────────
  presetBtns.addEventListener("click", (e) => {
    const btn = (e.target as HTMLElement).closest<HTMLButtonElement>("[data-vowel]");
    if (!btn) return;
    const vowel = btn.dataset.vowel as VowelId;
    presetBtns.querySelectorAll(".btn-vowel").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    const areas = engine.applyVowelPreset(vowel);
    tractEditor.setAreas(areas, true);
    updateFormants();
  });

  // ── エディタモード切替 ───────────────────────────────────────────
  modeManualBtn.addEventListener("click", () => {
    tractEditor.setMode("manual");
    modeManualBtn.classList.add("active");
    modeMagnetBtn.classList.remove("active");
    magnetControls.classList.remove("visible");
    editorHint.textContent = "制御点（青い丸）をドラッグして形状を変えてください";
  });

  modeMagnetBtn.addEventListener("click", () => {
    tractEditor.setMode("magnet");
    modeMagnetBtn.classList.add("active");
    modeManualBtn.classList.remove("active");
    magnetControls.classList.add("visible");
    editorHint.textContent = "キャンバス上をドラッグして形状を変えてください（上→断面積増加、下→減少）";
  });

  // ── マグネットスライダー ─────────────────────────────────────────
  magnetRadiusSlider.addEventListener("input", () => {
    const px = Number(magnetRadiusSlider.value);
    // canvas座標系のピクセル（canvas width=720）
    tractEditor.setMagnetRadius(px);
    magnetRadiusVal.textContent = `${px} px`;
  });

  magnetStrengthSlider.addEventListener("input", () => {
    const s = Number(magnetStrengthSlider.value) / 100;
    tractEditor.setMagnetStrength(s);
    magnetStrengthVal.textContent = s.toFixed(2);
  });

  // ── 基本スライダー ───────────────────────────────────────────────
  pitchSlider.addEventListener("input", () => {
    const hz = Number(pitchSlider.value);
    pitchVal.textContent = `${hz} Hz`;
    engine.setParams({ frequency: hz });
  });

  gainSlider.addEventListener("input", () => {
    const g = Number(gainSlider.value) / 100;
    gainVal.textContent = g.toFixed(2);
    engine.setParams({ gain: g });
  });

  // ── LF スライダー ────────────────────────────────────────────────
  rgSlider.addEventListener("input", () => {
    const rg = Number(rgSlider.value) / 100;
    rgVal.textContent = rg.toFixed(2);
    engine.setParams({ lf: { rg, rk: Number(rkSlider.value) / 100 } });
  });

  rkSlider.addEventListener("input", () => {
    const rk = Number(rkSlider.value) / 100;
    rkVal.textContent = rk.toFixed(2);
    engine.setParams({ lf: { rg: Number(rgSlider.value) / 100, rk } });
  });
}
