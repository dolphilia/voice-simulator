import { VoiceEngine } from "../audio/engine";
import {
  VOWEL_ORDER,
  VOWEL_PROFILE_SETS,
  type VowelId,
  type VowelSetId,
} from "../audio/vowels";

const SPEAKER_PRESETS = [
  { id: "neutral", label: "Neutral", tractScale: 1 },
  { id: "maoto", label: "消臭妖精ノール", tractScale: 1.006 },
  { id: "sora-lon", label: "天羽ソラtypeLON", tractScale: 1.047 },
  { id: "fumika", label: "星野フミカ", tractScale: 0.925 },
  { id: "mitsuko", label: "みつこ", tractScale: 0.98 },
  { id: "sanane", label: "アサ音さな", tractScale: 0.951 },
  { id: "maita", label: "まいた", tractScale: 1.062 },
] as const;

function createSlider(options: {
  label: string;
  min: number;
  max: number;
  step: number;
  value: number;
  onInput: (value: number) => void;
}): { element: HTMLLabelElement; setValue: (value: number) => void } {
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
  return {
    element: wrapper,
    setValue: (value: number) => {
      input.value = String(value);
      valueText.textContent = input.value;
    },
  };
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
  const tractScaleSlider = createSlider({
    label: "Tract Scale",
    min: 0.7,
    max: 1.4,
    step: 0.01,
    value: params.tractScale,
    onInput: (value) => {
      engine.setParams({ tractScale: value });
    },
  });

  const vowelDescription = document.createElement("p");
  vowelDescription.className = "status";
  vowelDescription.textContent =
    "UTAU analysis mode adds measured vowel presets, speaker scale, smooth transitions, breath noise, and first-pass /shi/ /su/ noise.";

  controls.append(
    createSelect({
      label: "Preset Set",
      value: params.vowelSet,
      choices: [
        { value: "reference", label: "Reference" },
        { value: "utau", label: "UTAU analysis" },
      ],
      onChange: (value) => {
        engine.setParams({ vowelSet: value as VowelSetId });
      },
    }),
    createSelect({
      label: "Vowel",
      value: params.vowel,
      choices: VOWEL_ORDER.map((vowelId) => ({
        value: vowelId,
        label: VOWEL_PROFILE_SETS.reference[vowelId].label,
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
    }).element,
    createSelect({
      label: "Speaker",
      value: "neutral",
      choices: SPEAKER_PRESETS.map((preset) => ({
        value: preset.id,
        label: preset.label,
      })),
      onChange: (value) => {
        const preset = SPEAKER_PRESETS.find((candidate) => candidate.id === value);
        if (!preset) {
          return;
        }
        tractScaleSlider.setValue(preset.tractScale);
        engine.setParams({ tractScale: preset.tractScale });
      },
    }),
    tractScaleSlider.element,
    createSlider({
      label: "Gain",
      min: 0.02,
      max: 0.25,
      step: 0.01,
      value: params.gain,
      onInput: (value) => {
        engine.setParams({ gain: value });
      },
    }).element,
    createSlider({
      label: "Brightness",
      min: 0,
      max: 1,
      step: 0.01,
      value: params.brightness,
      onInput: (value) => {
        engine.setParams({ brightness: value });
      },
    }).element,
    createSlider({
      label: "Breathiness",
      min: 0,
      max: 1,
      step: 0.01,
      value: params.breathiness,
      onInput: (value) => {
        engine.setParams({ breathiness: value });
      },
    }).element,
    vowelDescription,
  );

  const consonants = document.createElement("section");
  consonants.className = "controls controls--compact";

  const consonantLabel = document.createElement("p");
  consonantLabel.className = "status";
  consonantLabel.textContent = "Sibilant noise probes";

  const consonantButtons = document.createElement("div");
  consonantButtons.className = "button-row";

  const shiButton = document.createElement("button");
  shiButton.textContent = "し";
  shiButton.addEventListener("click", () => {
    engine.triggerConsonant("shi");
  });

  const suButton = document.createElement("button");
  suButton.textContent = "す";
  suButton.addEventListener("click", () => {
    engine.triggerConsonant("su");
  });

  consonantButtons.append(shiButton, suButton);
  consonants.append(consonantLabel, consonantButtons);

  const status = document.createElement("p");
  status.className = "status";
  status.textContent =
    "Current scope: measured vowel candidates, speaker scaling, 166 ms vowel transitions, and first noise-source probes.";

  container.append(heading, intro, buttonRow, controls, consonants, status);
  return container;
}
