import { playRecording } from "../audio/recording";
import {
  AcousticFdtd2D,
  MATERIALS,
  type MaterialId,
  type MaterialKey,
  type SourceMode,
} from "../sim/fdtd";

type Tool = MaterialKey | "source" | "ear";

const MATERIAL_LABELS: Record<MaterialKey, string> = {
  air: "空気",
  rigid: "完全反射",
  absorber: "吸音",
  transmissive: "透過",
  scatter: "散乱",
  frequency: "高域吸音",
};

const TOOL_OPTIONS: Array<{ value: Tool; label: string }> = [
  { value: "source", label: "音源" },
  { value: "ear", label: "耳" },
  { value: "air", label: "消去" },
  { value: "rigid", label: "完全反射" },
  { value: "absorber", label: "吸音" },
  { value: "transmissive", label: "透過" },
  { value: "scatter", label: "散乱" },
  { value: "frequency", label: "高域吸音" },
];

function createButton(label: string, onClick: () => void): HTMLButtonElement {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  button.addEventListener("click", onClick);
  return button;
}

function createSlider(options: {
  label: string;
  min: number;
  max: number;
  step: number;
  value: number;
  onInput: (value: number) => void;
}): HTMLLabelElement {
  const label = document.createElement("label");
  label.className = "control";

  const header = document.createElement("span");
  header.className = "control__header";
  header.textContent = options.label;

  const valueText = document.createElement("span");
  valueText.className = "control__value";
  valueText.textContent = String(options.value);

  const input = document.createElement("input");
  input.type = "range";
  input.min = String(options.min);
  input.max = String(options.max);
  input.step = String(options.step);
  input.value = String(options.value);
  input.addEventListener("input", () => {
    const value = Number(input.value);
    valueText.textContent = input.value;
    options.onInput(value);
  });

  label.append(header, valueText, input);
  return label;
}

function createSelect<T extends string>(options: {
  label: string;
  value: T;
  choices: Array<{ value: T; label: string }>;
  onChange: (value: T) => void;
}): HTMLLabelElement {
  const label = document.createElement("label");
  label.className = "control";

  const header = document.createElement("span");
  header.className = "control__header";
  header.textContent = options.label;

  const select = document.createElement("select");
  for (const choice of options.choices) {
    const option = document.createElement("option");
    option.value = choice.value;
    option.textContent = choice.label;
    option.selected = choice.value === options.value;
    select.append(option);
  }
  select.addEventListener("change", () => {
    options.onChange(select.value as T);
  });

  label.append(header, select);
  return label;
}

function drawSimulation(canvas: HTMLCanvasElement, sim: AcousticFdtd2D, pressureScale: number): void {
  const snapshot = sim.getSnapshot();
  const context = canvas.getContext("2d");
  if (!context) {
    return;
  }

  const image = context.createImageData(snapshot.width, snapshot.height);
  for (let y = 0; y < snapshot.height; y += 1) {
    for (let x = 0; x < snapshot.width; x += 1) {
      const cell = y * snapshot.width + x;
      const pixel = cell * 4;
      const material = snapshot.material[cell] as MaterialId;
      const pressure = Math.max(-1, Math.min(1, snapshot.pressure[cell] * pressureScale));
      const magnitude = Math.sqrt(Math.abs(pressure));
      let r = 250;
      let g = 250;
      let b = 248;

      if (pressure > 0) {
        r = 255;
        g = Math.round(238 - magnitude * 210);
        b = Math.round(232 - magnitude * 222);
      } else if (pressure < 0) {
        r = Math.round(232 - magnitude * 222);
        g = Math.round(238 - magnitude * 190);
        b = 255;
      }

      if (material === MATERIALS.rigid) {
        r = 8;
        g = 10;
        b = 12;
      } else if (material === MATERIALS.absorber) {
        r = 82;
        g = 88;
        b = 90;
      } else if (material === MATERIALS.transmissive) {
        r = 142;
        g = 150;
        b = 155;
      } else if (material === MATERIALS.scatter) {
        const stripe = (x + y) % 4 < 2 ? 115 : 165;
        r = stripe;
        g = stripe;
        b = stripe;
      } else if (material === MATERIALS.frequency) {
        r = 126;
        g = 86;
        b = 168;
      }

      if (snapshot.source.x === x && snapshot.source.y === y) {
        r = 18;
        g = 176;
        b = 92;
      } else if (snapshot.ear.x === x && snapshot.ear.y === y) {
        r = 250;
        g = 207;
        b = 64;
      }

      image.data[pixel] = r;
      image.data[pixel + 1] = g;
      image.data[pixel + 2] = b;
      image.data[pixel + 3] = 255;
    }
  }
  context.putImageData(image, 0, 0);
}

function eventToCell(event: PointerEvent, canvas: HTMLCanvasElement, sim: AcousticFdtd2D) {
  const rect = canvas.getBoundingClientRect();
  const x = Math.floor(((event.clientX - rect.left) / rect.width) * sim.config.width);
  const y = Math.floor(((event.clientY - rect.top) / rect.height) * sim.config.height);
  return { x, y };
}

export function createApp(): HTMLElement {
  const sim = new AcousticFdtd2D();
  let running = false;
  let sourceMode: SourceMode = "tone";
  let brushRadius = 2;
  let playbackSpeed = 1;
  let stepAccumulator = 0;
  let pressureScale = 24;
  let activeTool: Tool = "rigid";
  let pointerDown = false;

  const container = document.createElement("main");
  container.className = "app";

  const header = document.createElement("header");
  header.className = "app__header";
  const title = document.createElement("h1");
  title.textContent = "2D Acoustic FDTD";
  const subtitle = document.createElement("p");
  subtitle.textContent =
    "音圧 p と粒子速度 vx/vy を staggered grid で更新し、耳セルの圧力を録音します。";
  header.append(title, subtitle);

  const layout = document.createElement("section");
  layout.className = "sim-layout";

  const stage = document.createElement("div");
  stage.className = "stage";
  const canvas = document.createElement("canvas");
  canvas.className = "field";
  canvas.width = sim.config.width;
  canvas.height = sim.config.height;
  stage.append(canvas);

  const panel = document.createElement("aside");
  panel.className = "panel";

  const status = document.createElement("p");
  status.className = "status";
  const updateStatus = () => {
    const seconds = (sim.getRecording().length / sim.config.sampleRate).toFixed(2);
    status.textContent = `状態: ${running ? "実行中" : "停止中"} / 録音 ${seconds}s / ツール ${
      activeTool in MATERIALS ? MATERIAL_LABELS[activeTool as MaterialKey] : activeTool
    } / 速度 ${playbackSpeed.toFixed(2)}x`;
  };

  const controls = document.createElement("div");
  controls.className = "button-grid";
  controls.append(
    createButton("開始/停止", () => {
      running = !running;
      updateStatus();
    }),
    createButton("インパルス", () => {
      sim.injectImpulse(1.2);
    }),
    createButton("場をリセット", () => {
      sim.resetField();
      sim.clearRecording();
      updateStatus();
    }),
    createButton("壁を消去", () => {
      sim.clearMaterials();
    }),
    createButton("録音再生", () => {
      void playRecording(sim.getRecording(), sim.config.sampleRate);
    }),
    createButton("録音消去", () => {
      sim.clearRecording();
      updateStatus();
    }),
  );

  panel.append(
    controls,
    createSelect<Tool>({
      label: "配置ツール",
      value: activeTool,
      choices: TOOL_OPTIONS,
      onChange: (value) => {
        activeTool = value;
        updateStatus();
      },
    }),
    createSelect<SourceMode>({
      label: "音源",
      value: sourceMode,
      choices: [
        { value: "tone", label: "連続トーン" },
        { value: "pulse", label: "手動インパルス" },
      ],
      onChange: (value) => {
        sourceMode = value;
      },
    }),
    createSlider({
      label: "音源周波数",
      min: 80,
      max: 1600,
      step: 1,
      value: sim.config.sourceFrequency,
      onInput: (value) => {
        sim.config.sourceFrequency = value;
      },
    }),
    createSlider({
      label: "ブラシ半径",
      min: 1,
      max: 6,
      step: 1,
      value: brushRadius,
      onInput: (value) => {
        brushRadius = value;
      },
    }),
    createSlider({
      label: "再生速度",
      min: 0.125,
      max: 2,
      step: 0.125,
      value: playbackSpeed,
      onInput: (value) => {
        playbackSpeed = value;
      },
    }),
    createSlider({
      label: "表示コントラスト",
      min: 6,
      max: 32,
      step: 1,
      value: pressureScale,
      onInput: (value) => {
        pressureScale = value;
      },
    }),
    createSlider({
      label: "外周吸音",
      min: 0.03,
      max: 0.22,
      step: 0.01,
      value: sim.config.edgeAbsorbStrength,
      onInput: (value) => {
        sim.config.edgeAbsorbStrength = value;
        sim.recomputeDamping();
      },
    }),
    status,
  );

  const paint = (event: PointerEvent) => {
    const point = eventToCell(event, canvas, sim);
    if (activeTool === "source") {
      sim.setSource(point);
      return;
    }
    if (activeTool === "ear") {
      sim.setEar(point);
      return;
    }
    sim.setMaterial(point, MATERIALS[activeTool], brushRadius);
  };

  canvas.addEventListener("pointerdown", (event) => {
    pointerDown = true;
    canvas.setPointerCapture(event.pointerId);
    paint(event);
  });
  canvas.addEventListener("pointermove", (event) => {
    if (pointerDown) {
      paint(event);
    }
  });
  canvas.addEventListener("pointerup", () => {
    pointerDown = false;
  });
  canvas.addEventListener("pointercancel", () => {
    pointerDown = false;
  });

  layout.append(stage, panel);
  container.append(header, layout);

  const animate = () => {
    if (running) {
      stepAccumulator += 8 * playbackSpeed;
      const steps = Math.floor(stepAccumulator);
      stepAccumulator -= steps;
      for (let i = 0; i < steps; i += 1) {
        sim.step(sourceMode);
      }
    }
    drawSimulation(canvas, sim, pressureScale);
    updateStatus();
    requestAnimationFrame(animate);
  };
  animate();

  return container;
}
