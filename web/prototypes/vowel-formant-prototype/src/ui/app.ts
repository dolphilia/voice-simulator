import { VoiceEngine } from "../audio/engine";
import { SIBILANT_PROFILES, type SibilantId } from "../audio/phonemes";
import {
  VOWEL_ORDER,
  VOWEL_PROFILE_SETS,
  type VowelId,
  type VowelSetId,
} from "../audio/vowels";
import { SpectrumView } from "./spectrum-view";

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
  const spectrumCanvas = document.createElement("canvas");
  spectrumCanvas.className = "spectrum";
  spectrumCanvas.width = 720;
  spectrumCanvas.height = 220;
  const spectrumView = new SpectrumView(spectrumCanvas);

  const applyParams = (nextParams: Parameters<VoiceEngine["setParams"]>[0]) => {
    const updatedParams = engine.setParams(nextParams);
    updateFormantReadout(updatedParams);
  };

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
    const analyser = engine.analyser;
    if (analyser) {
      spectrumView.setAnalyser(analyser);
      spectrumView.start();
    }
  });

  const stopButton = document.createElement("button");
  stopButton.textContent = "Stop";
  stopButton.addEventListener("click", () => {
    engine.stop();
    spectrumView.stop();
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
      applyParams({ tractScale: value });
    },
  });

  const formantReadout = document.createElement("section");
  formantReadout.className = "formant-readout";

  const updateFormantReadout = (currentParams = engine.getParams()) => {
    const profile = VOWEL_PROFILE_SETS[currentParams.vowelSet][currentParams.vowel];
    spectrumView.setTarget({
      vowel: currentParams.vowel,
      vowelSet: currentParams.vowelSet,
      tractScale: currentParams.tractScale,
    });
    const rows = profile.formants
      .map((formant, index) => {
        const scaledFrequency = formant.frequency / currentParams.tractScale;
        return `<tr>
          <th scope="row">F${index + 1}</th>
          <td>${Math.round(scaledFrequency)} Hz</td>
          <td>${Math.round(formant.bandwidth)} Hz</td>
          <td>${formant.gain.toFixed(2)}</td>
        </tr>`;
      })
      .join("");

    formantReadout.innerHTML = `
      <h2>Current vowel target</h2>
      <p>${currentParams.vowelSet} ${profile.label}, tractScale ${currentParams.tractScale.toFixed(3)}</p>
      <table>
        <thead>
          <tr>
            <th scope="col">Band</th>
            <th scope="col">Frequency</th>
            <th scope="col">Bandwidth</th>
            <th scope="col">Gain</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    `;
  };

  updateFormantReadout(params);

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
        { value: "tuned", label: "Tuned experiment" },
      ],
      onChange: (value) => {
        applyParams({ vowelSet: value as VowelSetId });
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
        applyParams({ vowel: value as VowelId });
      },
    }),
    createSlider({
      label: "Pitch",
      min: 80,
      max: 400,
      step: 1,
      value: params.frequency,
      onInput: (value) => {
        applyParams({ frequency: value });
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
        applyParams({ tractScale: preset.tractScale });
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
        applyParams({ gain: value });
      },
    }).element,
    createSlider({
      label: "Brightness",
      min: 0,
      max: 1,
      step: 0.01,
      value: params.brightness,
      onInput: (value) => {
        applyParams({ brightness: value });
      },
    }).element,
    createSlider({
      label: "Breathiness",
      min: 0,
      max: 1,
      step: 0.01,
      value: params.breathiness,
      onInput: (value) => {
        applyParams({ breathiness: value });
      },
    }).element,
    formantReadout,
    vowelDescription,
  );

  const consonants = document.createElement("section");
  consonants.className = "controls controls--compact";

  const consonantLabel = document.createElement("p");
  consonantLabel.className = "status";
  consonantLabel.textContent = "Sibilant probes and syllable events";

  const consonantButtons = document.createElement("div");
  consonantButtons.className = "button-row";

  const shiButton = document.createElement("button");
  shiButton.textContent = "し noise";
  shiButton.addEventListener("click", () => {
    engine.triggerConsonant("shi");
  });

  const suButton = document.createElement("button");
  suButton.textContent = "す noise";
  suButton.addEventListener("click", () => {
    engine.triggerConsonant("su");
  });

  consonantButtons.append(shiButton, suButton);

  const syllableButtons = document.createElement("div");
  syllableButtons.className = "syllable-grid";

  const syllableTargets: Array<{ consonant: SibilantId; vowel: VowelId }> = [
    { consonant: "shi", vowel: "a" },
    { consonant: "shi", vowel: "i" },
    { consonant: "shi", vowel: "e" },
    { consonant: "su", vowel: "a" },
    { consonant: "su", vowel: "u" },
    { consonant: "su", vowel: "o" },
  ];

  for (const target of syllableTargets) {
    const button = document.createElement("button");
    button.textContent = `${SIBILANT_PROFILES[target.consonant].label}-${target.vowel}`;
    button.addEventListener("click", () => {
      const updatedParams = engine.triggerSyllable(target.consonant, target.vowel);
      updateFormantReadout(updatedParams);
    });
    syllableButtons.append(button);
  }

  const syllableDescription = document.createElement("p");
  syllableDescription.className = "status";
  syllableDescription.textContent =
    "Syllable buttons attenuate the current vowel, play filtered sibilant noise, then ramp into the selected vowel with a small overlap.";

  consonants.append(consonantLabel, consonantButtons, syllableButtons, syllableDescription);

  const status = document.createElement("p");
  status.className = "status";
  status.textContent =
    "Current scope: measured vowel candidates, speaker scaling, 166 ms vowel transitions, and first noise-source probes.";

  const spectrumPanel = document.createElement("section");
  spectrumPanel.className = "spectrum-panel";

  const spectrumHeading = document.createElement("h2");
  spectrumHeading.textContent = "Spectrum";

  const spectrumCaption = document.createElement("p");
  spectrumCaption.className = "status";
  spectrumCaption.textContent =
    "Solid markers show the selected preset set. Faint markers show the other preset sets for the same vowel.";

  spectrumPanel.append(spectrumHeading, spectrumCanvas, spectrumCaption);

  container.append(heading, intro, buttonRow, controls, spectrumPanel, consonants, status);
  return container;
}
