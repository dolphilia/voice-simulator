export type SibilantId = "shi" | "su";

export type SibilantProfile = {
  id: SibilantId;
  label: string;
  centerFrequency: number;
  q: number;
  durationSeconds: number;
  attackSeconds: number;
  overlapSeconds: number;
  peakGain: number;
};

export const SIBILANT_PROFILES: Record<SibilantId, SibilantProfile> = {
  shi: {
    id: "shi",
    label: "し",
    centerFrequency: 6100,
    q: 1.4,
    durationSeconds: 0.145,
    attackSeconds: 0.015,
    overlapSeconds: 0.045,
    peakGain: 0.08,
  },
  su: {
    id: "su",
    label: "す",
    centerFrequency: 6000,
    q: 1.0,
    durationSeconds: 0.155,
    attackSeconds: 0.015,
    overlapSeconds: 0.05,
    peakGain: 0.07,
  },
};
