// CHTL v1 の形式と時刻の換算は固定上流の src/show/tele.ts に対応する（Jameson Hodge、MIT）。

const headerBytes = 48;
const scalarCount = 11;
export const duetTelemetryScalars = ["phLen", "orLen", "velumPort", "f0", "voicing", "pLung",
  "outRms", "noiseLevel", "noiseNode", "gate", "clock"] as const;

type NoiseBranchRange = { base: number; cells: number };
export type NoiseBranchLayout = {
  pharynx: NoiseBranchRange; oral: NoiseBranchRange; glottis_port: number; sample_rate_hz: number;
};

export function readNoiseBranches(value: unknown, track: DuetTeleTrack): NoiseBranchLayout {
  const layout = value as Partial<NoiseBranchLayout> | null;
  const matches = (range: NoiseBranchRange | undefined, cells: number): range is NoiseBranchRange =>
    !!range && Number.isSafeInteger(range.base) && range.base >= 0 && range.cells === cells && cells > 0
      && Number.isSafeInteger(range.base + cells - 1);
  if (!layout || layout.sample_rate_hz !== track.sampleRate || !matches(layout.pharynx, track.nPh)
      || !matches(layout.oral, track.nOr) || layout.glottis_port === undefined
      || !Number.isSafeInteger(layout.glottis_port) || layout.glottis_port < 0) {
    throw new Error("乱流源の枝情報がテレメトリの形式と一致しません");
  }
  const { pharynx, oral, glottis_port, sample_rate_hz } = layout;
  const end = (range: NoiseBranchRange) => range.base + range.cells - 1;
  const contains = (range: NoiseBranchRange, branch: number) => range.base <= branch && branch < end(range);
  if ((pharynx.cells > 1 && oral.cells > 1 && end(pharynx) > oral.base && end(oral) > pharynx.base)
      || contains(pharynx, glottis_port) || contains(oral, glottis_port)) {
    throw new Error("乱流源の枝範囲が重複しています");
  }
  return { pharynx, oral, glottis_port, sample_rate_hz };
}

export class DuetTeleTrack {
  readonly sampleRate: number;
  readonly hop: number;
  readonly frames: number;
  readonly nPh: number;
  readonly nOr: number;
  readonly nArtic: number;
  readonly nScope: number;
  readonly body: { female: number; child: number };
  private readonly width: number;
  private readonly data: Float32Array;

  constructor(buffer: ArrayBuffer) {
    if (buffer.byteLength < headerBytes) throw new Error("テレメトリのヘッダーが途中で終わっています");
    if (new TextDecoder().decode(new Uint8Array(buffer, 0, 4)) !== "CHTL") {
      throw new Error("CHTLのテレメトリではありません");
    }
    const view = new DataView(buffer);
    const [version, rate, hop, frames, width, nArtic, nPh, nOr, nScope] = Array.from({ length: 9 },
      (_, index) => view.getUint32(4 + 4 * index, true));
    if (version !== 1) throw new Error(`テレメトリのバージョン${version}には対応していません`);
    if (!rate || !hop || !frames || width !== scalarCount + nArtic + 3 * (nPh + nOr) + 2 * nScope) {
      throw new Error("テレメトリの時刻または行の構成が不正です");
    }
    const items = frames * width;
    if (!Number.isSafeInteger(items) || buffer.byteLength !== headerBytes + 4 * items) {
      throw new Error("テレメトリのバイト数がヘッダーと一致しません");
    }
    const female = view.getFloat32(40, true);
    const child = view.getFloat32(44, true);
    if (![female, child].every((value) => value >= 0 && value <= 1)) throw new Error("体型の混合係数が範囲外です");
    this.data = new Float32Array(items);
    for (let index = 0; index < items; index++) {
      const value = view.getFloat32(headerBytes + 4 * index, true);
      if (!Number.isFinite(value)) throw new Error("テレメトリに非有限値があります");
      this.data[index] = value;
    }
    this.sampleRate = rate;
    this.hop = hop;
    this.frames = frames;
    this.width = width;
    this.nArtic = nArtic;
    this.nPh = nPh;
    this.nOr = nOr;
    this.nScope = nScope;
    this.body = { female, child };
  }

  indexAt(seconds: number) {
    const index = Math.floor(seconds * this.sampleRate / this.hop + 1e-6);
    return Number.isFinite(index) ? Math.max(0, Math.min(index, this.frames - 1)) : 0;
  }

  frame(index: number) {
    if (!Number.isInteger(index) || index < 0 || index >= this.frames) throw new RangeError("テレメトリの行が範囲外です");
    let position = index * this.width;
    const take = (length: number) => {
      const start = position;
      position += length;
      return this.data.subarray(start, position);
    };
    const [phLen, orLen, velumPort, f0, voicing, pLung, outRms, noiseLevel, noiseNode, gate, clock] = take(scalarCount);
    const tractCells = this.nPh + this.nOr;
    return { index, sample: index * this.hop, phLen, orLen, velumPort, f0, voicing, pLung, outRms, noiseLevel,
      noiseNode, gate, clock, artic: take(this.nArtic), phAreas: take(this.nPh), orAreas: take(this.nOr),
      pressureRms: take(tractCells), flow: take(tractCells), glottalArea: take(this.nScope), glottalFlow: take(this.nScope) };
  }
}
