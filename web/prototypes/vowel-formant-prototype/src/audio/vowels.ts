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

export type VowelSetId = "reference" | "utau";

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

export const UTAU_VOWEL_PROFILES: Record<VowelId, VowelProfile> = {
  a: {
    id: "a",
    label: "/a/",
    formants: [
      { frequency: 962, bandwidth: 123, gain: 0.46 },
      { frequency: 1405, bandwidth: 74, gain: 1.0 },
      { frequency: 2378, bandwidth: 102, gain: 0.23 },
    ],
  },
  i: {
    id: "i",
    label: "/i/",
    formants: [
      { frequency: 376, bandwidth: 52, gain: 0.31 },
      { frequency: 2831, bandwidth: 195, gain: 0.28 },
      { frequency: 3725, bandwidth: 85, gain: 0.96 },
    ],
  },
  u: {
    id: "u",
    label: "/u/",
    formants: [
      { frequency: 498, bandwidth: 80, gain: 0.5 },
      { frequency: 1326, bandwidth: 98, gain: 0.45 },
      { frequency: 1762, bandwidth: 75, gain: 1.0 },
    ],
  },
  e: {
    id: "e",
    label: "/e/",
    formants: [
      { frequency: 665, bandwidth: 60, gain: 0.5 },
      { frequency: 2354, bandwidth: 128, gain: 0.12 },
      { frequency: 3270, bandwidth: 128, gain: 0.29 },
    ],
  },
  o: {
    id: "o",
    label: "/o/",
    formants: [
      { frequency: 717, bandwidth: 67, gain: 0.18 },
      { frequency: 1048, bandwidth: 68, gain: 1.0 },
      { frequency: 3171, bandwidth: 229, gain: 0.12 },
    ],
  },
};

export const VOWEL_PROFILE_SETS: Record<VowelSetId, Record<VowelId, VowelProfile>> = {
  reference: VOWEL_PROFILES,
  utau: UTAU_VOWEL_PROFILES,
};

export const VOWEL_ORDER: VowelId[] = ["a", "i", "u", "e", "o"];
