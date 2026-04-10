import { VoiceEngine } from "../audio/engine";
import { VOWEL_ORDER, VOWEL_PROFILES, type VowelId } from "../audio/vowels";

function createSlider(options: {
  label: string;
  min: number;
  max: number;
  step: number;
  value: number;
  onInput: (value: number) => void;
}): HTMLLabelElement {
  const wrapper = document.createElement("label");
  wrapper.className = "control";

  const title = document.createElement("span");
  title.className = "control__label";
  title.textContent = options.label;

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
    const nextValue = Number(input.value);
    valueText.textContent = input.value;
    options.onInput(nextValue);
  });

  wrapper.append(title, valueText, input);
  return wrapper;
}

function createSelect(options: {
  label: string;
  value: string;
  choices: Array<{ value: string; label: string }>;
  onChange: (value: string) => void;
}): HTMLLabelElement {
  const wrapper = document.createElement("label");
  wrapper.className = "control";

  const title = document.createElement("span");
  title.className = "control__label";
  title.textContent = options.label;

  const select = document.createElement("select");
  select.className = "control__select";

  for (const choice of options.choices) {
    const option = document.createElement("option");
    option.value = choice.value;
    option.textContent = choice.label;
    if (choice.value === options.value) {
      option.selected = true;
    }
    select.append(option);
  }

  select.addEventListener("change", () => {
    options.onChange(select.value);
  });

  wrapper.append(title, select);
  return wrapper;
}

export function createApp(): HTMLElement {
  const engine = new VoiceEngine();
  const container = document.createElement("main");
  container.className = "app";

  const heading = document.createElement("h1");
  heading.textContent = "voice-simulator";

  const intro = document.createElement("p");
  intro.className = "intro";
  intro.textContent =
    "First vowel-oriented prototype. A sawtooth-like excitation is passed through a small formant filter bank so the output can move toward vowel-like timbres.";

  const buttonRow = document.createElement("div");
  buttonRow.className = "button-row";

  const startButton = document.createElement("button");
  startButton.textContent = "Start";
  startButton.addEventListener("click", async () => {
    await engine.start();
  });

  const stopButton = document.createElement("button");
  stopButton.textContent = "Stop";
  stopButton.addEventListener("click", () => {
    engine.stop();
  });

  buttonRow.append(startButton, stopButton);

  const controls = document.createElement("section");
  controls.className = "controls";

  const params = engine.getParams();
  const vowelDescription = document.createElement("p");
  vowelDescription.className = "status";
  vowelDescription.textContent =
    "Current approach: excitation source plus three approximate formant filters.";

  controls.append(
    createSelect({
      label: "Vowel",
      value: params.vowel,
      choices: VOWEL_ORDER.map((vowelId) => ({
        value: vowelId,
        label: VOWEL_PROFILES[vowelId].label,
      })),
      onChange: (value) => {
        engine.setParams({ vowel: value as VowelId });
      },
    }),
    createSlider({
      label: "Pitch",
      min: 80,
      max: 400,
      step: 1,
      value: params.frequency,
      onInput: (value) => {
        engine.setParams({ frequency: value });
      },
    }),
    createSlider({
      label: "Tract Scale",
      min: 0.7,
      max: 1.4,
      step: 0.01,
      value: params.tractScale,
      onInput: (value) => {
        engine.setParams({ tractScale: value });
      },
    }),
    createSlider({
      label: "Gain",
      min: 0.02,
      max: 0.25,
      step: 0.01,
      value: params.gain,
      onInput: (value) => {
        engine.setParams({ gain: value });
      },
    }),
    vowelDescription,
  );

  const status = document.createElement("p");
  status.className = "status";
  status.textContent =
    "Current scope: first-pass vowel coloring, preset selection, and coarse tract scaling.";

  container.append(heading, intro, buttonRow, controls, status);
  return container;
}
