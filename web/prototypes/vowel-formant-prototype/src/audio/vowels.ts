export type VowelId = "a" | "i" | "u" | "e" | "o";

export type Formant = {
  frequency: number;
  bandwidth: number;
  gain: number;
};

export type VowelProfile = {
  id: VowelId;
  label: string;
  formants: [Formant, Formant, Formant];
};

export const VOWEL_PROFILES: Record<VowelId, VowelProfile> = {
  a: {
    id: "a",
    label: "/a/",
    formants: [
      { frequency: 730, bandwidth: 90, gain: 1.0 },
      { frequency: 1090, bandwidth: 110, gain: 0.55 },
      { frequency: 2440, bandwidth: 160, gain: 0.35 },
    ],
  },
  i: {
    id: "i",
    label: "/i/",
    formants: [
      { frequency: 270, bandwidth: 60, gain: 1.0 },
      { frequency: 2290, bandwidth: 100, gain: 0.5 },
      { frequency: 3010, bandwidth: 120, gain: 0.3 },
    ],
  },
  u: {
    id: "u",
    label: "/u/",
    formants: [
      { frequency: 300, bandwidth: 70, gain: 1.0 },
      { frequency: 870, bandwidth: 90, gain: 0.6 },
      { frequency: 2240, bandwidth: 140, gain: 0.3 },
    ],
  },
  e: {
    id: "e",
    label: "/e/",
    formants: [
      { frequency: 530, bandwidth: 80, gain: 1.0 },
      { frequency: 1840, bandwidth: 100, gain: 0.55 },
      { frequency: 2480, bandwidth: 150, gain: 0.35 },
    ],
  },
  o: {
    id: "o",
    label: "/o/",
    formants: [
      { frequency: 570, bandwidth: 80, gain: 1.0 },
      { frequency: 840, bandwidth: 90, gain: 0.6 },
      { frequency: 2410, bandwidth: 150, gain: 0.3 },
    ],
  },
};

export const VOWEL_ORDER: VowelId[] = ["a", "i", "u", "e", "o"];
