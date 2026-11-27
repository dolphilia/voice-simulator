import { BufferGeometry, DynamicDrawUsage, Float32BufferAttribute, Group, LineBasicMaterial, LineSegments } from "three";
import { airwayPoint, type AirflowTract } from "./duet-head-airflow";
import type { NoiseBranchLayout } from "./duet-telemetry";

// 固定上流の VoiceModel.branchS と Anatomy3D.drawTurbulence（Jameson Hodge、MIT）。
const initialSeed = 7;
const segmentCount = 40;
const modulus = 2147483647;
export type TurbulenceInput = { phLen: number; orLen: number; noiseLevel: number; noiseNode: number };

export function noiseBranchPosition(layout: NoiseBranchLayout, { phLen, orLen, noiseNode }: TurbulenceInput) {
  if (!Number.isSafeInteger(noiseNode)) return null;
  const { pharynx, oral } = layout;
  const ph = noiseNode - pharynx.base;
  if (ph >= 0 && ph < pharynx.cells - 1) return ((ph + 1) / pharynx.cells) * phLen;
  const or = noiseNode - oral.base;
  if (or >= 0 && or < oral.cells - 1) return phLen + ((or + 1) / oral.cells) * orLen;
  return noiseNode === layout.glottis_port ? 0.2 : null;
}

export class DuetTurbulence {
  private seed = initialSeed;

  step(tract: AirflowTract, layout: NoiseBranchLayout, source: TurbulenceInput) {
    const seedBefore = this.seed;
    const s = noiseBranchPosition(layout, source);
    const intensity = source.noiseLevel > 1 ? Math.min(1, Math.log10(source.noiseLevel) / 3.2) : 0;
    const segments: { from: number[]; to: number[]; alpha: number }[] = [];
    if (s !== null && s >= 0 && intensity > 0.05) {
      let seed = this.seed = (this.seed * 16807) % modulus;
      const random = () => (seed = (seed * 16807) % modulus) / modulus;
      for (let i = 0; i < segmentCount; i++) {
        const point = airwayPoint(tract, s + 0.2 + 1.2 * random(), 2 * random() - 1, 2 * random() - 1);
        if (!point) continue;
        const half = 0.02 + 0.05 * random();
        const [x, y, z] = point;
        segments.push({ from: [x - half, y, z], to: [x + half, y, z], alpha: 0.15 + 0.7 * intensity * random() });
      }
    }
    return { s, intensity, seedBefore, seedAfter: this.seed, segments };
  }
}

export function createDuetTurbulenceView(head: Group) {
  const model = new DuetTurbulence();
  const geometry = new BufferGeometry();
  const position = new Float32BufferAttribute(6 * segmentCount, 3).setUsage(DynamicDrawUsage);
  const color = new Float32BufferAttribute(8 * segmentCount, 4).setUsage(DynamicDrawUsage);
  geometry.setAttribute("position", position);
  geometry.setAttribute("color", color);
  geometry.setDrawRange(0, 0);
  // 淡い背景で見える線色を使い、不透明度は固定上流の計算を保つ。
  const mesh = new LineSegments(geometry, new LineBasicMaterial({ color: 0x365574, vertexColors: true,
    transparent: true, depthWrite: false }));
  mesh.frustumCulled = false;
  head.add(mesh);
  let frame: ReturnType<DuetTurbulence["step"]> | null = null;
  let lastSource: TurbulenceInput | null = null;

  return {
    draw(tract: AirflowTract, layout: NoiseBranchLayout | undefined, source: TurbulenceInput | null, refresh: boolean) {
      if (!layout || !source) frame = null;
      else if (refresh || !lastSource) frame = model.step(tract, layout, source);
      else return;
      lastSource = layout ? source : null;
      const lines = frame?.segments ?? [];
      for (const [index, line] of lines.entries()) {
        position.array.set(line.from, 6 * index);
        position.array.set(line.to, 6 * index + 3);
        color.setXYZW(2 * index, 1, 1, 1, line.alpha);
        color.setXYZW(2 * index + 1, 1, 1, 1, line.alpha);
      }
      geometry.setDrawRange(0, 2 * lines.length);
      position.needsUpdate = true;
      color.needsUpdate = true;
    },
    read() {
      const count = geometry.drawRange.count;
      return { source: lastSource, frame, vertices: Array.from(position.array.subarray(0, count * 3)),
        alpha: Array.from({ length: count }, (_, i) => color.getW(i)) };
    },
  };
}
