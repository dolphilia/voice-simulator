import { TubeVoiceEngine } from "../audio/engine";
import { VOWEL_PRESETS, VOWEL_LABELS, VOWEL_ORDER, type VowelId } from "../audio/vowel-presets";
import { TractEditor } from "./tract-editor";
import { SpectrumView } from "./spectrum-view";

export function createApp(root: HTMLElement): void {
  const engine = new TubeVoiceEngine("a");

  // ── DOM 構築 ─────────────────────────────────────────

  root.innerHTML = `
    <div class="app">
      <header class="header">
        <h1 class="title">声道チューブモデル</h1>
        <button id="toggleBtn" class="btn btn-primary">▶ スタート</button>
      </header>

      <section class="editor-section">
        <div class="section-label">声道形状エディタ
          <span class="hint">制御点（青い丸）をドラッグして形状を変えてください</span>
        </div>
        <canvas id="tractCanvas" class="tract-canvas" width="700" height="180"></canvas>
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
      </section>

      <section class="spectrum-section">
        <div class="section-label">スペクトラム
          <span id="formantInfo" class="formant-info"></span>
        </div>
        <canvas id="spectrumCanvas" class="spectrum-canvas" width="700" height="140"></canvas>
      </section>
    </div>
  `;

  // ── 要素参照 ─────────────────────────────────────────

  const toggleBtn = root.querySelector<HTMLButtonElement>("#toggleBtn")!;
  const tractCanvas = root.querySelector<HTMLCanvasElement>("#tractCanvas")!;
  const spectrumCanvas = root.querySelector<HTMLCanvasElement>("#spectrumCanvas")!;
  const pitchSlider = root.querySelector<HTMLInputElement>("#pitchSlider")!;
  const gainSlider = root.querySelector<HTMLInputElement>("#gainSlider")!;
  const pitchVal = root.querySelector<HTMLSpanElement>("#pitchVal")!;
  const gainVal = root.querySelector<HTMLSpanElement>("#gainVal")!;
  const presetBtns = root.querySelector<HTMLDivElement>("#presetBtns")!;
  const formantInfo = root.querySelector<HTMLSpanElement>("#formantInfo")!;

  // ── 声道エディタ ──────────────────────────────────────

  const tractEditor = new TractEditor(
    tractCanvas,
    VOWEL_PRESETS["a"],
    (areas) => {
      engine.setAreas(areas);
      updateFormantInfo();
    }
  );

  // ── スペクトラム表示 ───────────────────────────────────

  const spectrumView = new SpectrumView(spectrumCanvas);

  function updateFormantInfo(): void {
    const f = engine.getFormants();
    spectrumView.setFormants(f);
    formantInfo.textContent = f
      .map((freq, i) => `F${i + 1}: ${Math.round(freq)} Hz`)
      .join("  ");
  }

  updateFormantInfo();

  // ── スタート / ストップ ────────────────────────────────

  toggleBtn.addEventListener("click", async () => {
    if (!engine.isRunning) {
      toggleBtn.disabled = true;
      toggleBtn.textContent = "起動中...";
      try {
        await engine.start();
        const analyser = engine.analyser;
        if (analyser) spectrumView.setAnalyser(analyser);
        spectrumView.start();
        toggleBtn.textContent = "■ ストップ";
        toggleBtn.classList.replace("btn-primary", "btn-stop");
      } catch (e) {
        console.error(e);
        toggleBtn.textContent = "▶ スタート";
      }
      toggleBtn.disabled = false;
    } else {
      engine.stop();
      spectrumView.stop();
      toggleBtn.textContent = "▶ スタート";
      toggleBtn.classList.replace("btn-stop", "btn-primary");
    }
  });

  // ── 母音プリセット ────────────────────────────────────

  presetBtns.addEventListener("click", (e) => {
    const btn = (e.target as HTMLElement).closest<HTMLButtonElement>("[data-vowel]");
    if (!btn) return;
    const vowel = btn.dataset.vowel as VowelId;
    presetBtns.querySelectorAll(".btn-vowel").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    const areas = engine.applyVowelPreset(vowel);
    tractEditor.setAreas(areas, true);
    updateFormantInfo();
  });

  // ── スライダー ────────────────────────────────────────

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
}
