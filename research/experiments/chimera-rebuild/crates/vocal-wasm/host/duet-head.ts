import { AREA_GRID_COLUMNS } from "./fixed-voice";

export const duetHeadAxisCount = 17;
export const duetHeadPaths = ["outer", "inner", "tongue", "velum", "upper_lip", "lower_lip",
  "upper_teeth", "lower_teeth", "jaw_bone", "epiglottis", "nasal_cavity"] as const;

type Exports = WebAssembly.Exports & {
  memory: WebAssembly.Memory;
  vocal_duet_head_init(female: number, child: number): number;
  vocal_duet_head_compute(): number;
  vocal_duet_head_points(): number;
};

export type DuetHeadPath = typeof duetHeadPaths[number];
export type DuetHeadGeometry = {
  scale: number;
  lipWidth: number;
  glottis: readonly [number, number];
  paths: Record<DuetHeadPath, Float64Array>;
  grid: Float64Array[];
};

export function createDuetHeadGeometry(module: WebAssembly.Module, body: { female: number; child: number }) {
  const wasm = new WebAssembly.Instance(module).exports as Exports;
  const input = wasm.vocal_duet_head_init(body.female, body.child);
  if (!input) throw new Error("頭部の体型を設定できません");

  return (artic: ArrayLike<number>): DuetHeadGeometry => {
    if (artic.length !== duetHeadAxisCount) throw new Error("頭部の描画には17軸の調音姿勢が必要です");
    new Float64Array(wasm.memory.buffer, input, duetHeadAxisCount).set(artic);
    const count = wasm.vocal_duet_head_compute();
    if (!count) throw new Error("有限な頭部形状を計算できません");
    const points = new Float64Array(wasm.memory.buffer, wasm.vocal_duet_head_points(), count);
    let offset = 4;
    const paths = {} as DuetHeadGeometry["paths"];
    for (const name of duetHeadPaths) {
      const length = 2 * points[offset++];
      paths[name] = points.subarray(offset, offset + length);
      offset += length;
    }
    const rows = points[offset++];
    const width = AREA_GRID_COLUMNS.length;
    if (!Number.isSafeInteger(rows) || rows < 0 || offset + rows * width !== count) {
      throw new Error("頭部の形状バッファが不正です");
    }
    const grid = Array.from({ length: rows }, (_, i) => points.subarray(offset + i * width, offset + (i + 1) * width));
    // 次の計算まで有効なビュー。描画側は呼び出し内で頂点を転写する。
    return { scale: points[0], lipWidth: points[1], glottis: [points[2], points[3]], paths, grid };
  };
}

