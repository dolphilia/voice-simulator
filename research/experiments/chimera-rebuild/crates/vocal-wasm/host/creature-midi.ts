export type CreatureMidiInput = { note: number | null }
  | { call: string; note: number; pressed: boolean };
