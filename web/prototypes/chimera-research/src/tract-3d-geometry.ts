import { Vector3 } from "three";

export const tractViews = {
  angled: new Vector3(0.78, 0.42, 1),
  side: new Vector3(0, 0, 1),
  front: new Vector3(1, 0, 0),
};

export type TractView = keyof typeof tractViews;

export const tractColors = {
  background: "#edf5f2", pharynx: "#497a69", mouth: "#176a81", highlight: "#a14420", outline: "#79938d",
};

export const tractCameraFov = 37;
export const tractCameraDistance = 1.65;

type TractRingLimits = {
  maxWidth: number; minimumGap: number; directionThreshold: number; fallbackDirection: readonly [number, number];
};

function tractSection(row: readonly number[] | Float64Array, limits?: TractRingLimits) {
  const [, innerX, innerY, outerX, outerY, , , , gap, area] = row;
  const length = Math.hypot(outerX - innerX, outerY - innerY);
  if (!row.every(Number.isFinite) || gap < 0 || area < 0
      || (!limits && ((gap === 0 && area > 0) || (length === 0 && gap > 0)))) {
    throw new Error("この測定線は正中矢状面の隙間を保つ楕円に変換できません");
  }
  const [ux, uy] = length > (limits?.directionThreshold ?? 0)
    ? [(outerX - innerX) / length, (outerY - innerY) / length]
    : limits?.fallbackDirection ?? [0, 0];
  const a = gap / 2;
  const b = gap <= (limits?.minimumGap ?? 0) ? 0 : Math.min(limits?.maxWidth ?? Infinity, area / (Math.PI * a));
  const x = outerX - a * ux;
  const y = outerY - a * uy;
  return { center: new Vector3(x, y, 0), direction: [ux, uy] as const, radius: a, width: b };
}

export function tractRingVertices(section: ReturnType<typeof tractSection>, segments: number) {
  const { center: { x, y }, direction: [ux, uy], radius, width } = section;
  const vertices = [];
  for (let j = 0; j < segments; j++) {
    const theta = 2 * Math.PI * j / segments;
    const d = Math.cos(theta) * radius;
    vertices.push(x + ux * d, y + uy * d, Math.sin(theta) * width);
  }
  return vertices;
}

export function tractRing(row: readonly number[] | Float64Array, segments: number, limits?: TractRingLimits) {
  const section = tractSection(row, limits);
  return { ...section, vertices: tractRingVertices(section, segments) };
}

export function duetTractSections(grid: readonly (readonly number[] | Float64Array)[], scale: number) {
  let fallbackDirection: readonly [number, number] = [-1, 0];
  return grid.map((row, index) => {
    const section = tractSection(row, { fallbackDirection, maxWidth: 3.5 * scale,
      minimumGap: 0.01, directionThreshold: 0.0001 });
    fallbackDirection = section.direction;
    return { index, distance: row[10], ...section };
  });
}

export type DuetTractNodeInput = { phLen: number; orLen: number; nPh: number; nOr: number };

export function duetTractNodes({ nPh, nOr, phLen, orLen }: DuetTractNodeInput) {
  const distances = new Float64Array(nPh + nOr);
  for (let i = 0; i < nPh; i++) distances[i] = ((i + 0.5) / nPh) * phLen;
  for (let i = 0; i < nOr; i++) distances[nPh + i] = phLen + ((i + 0.5) / nOr) * orLen;
  return distances;
}

export function nearestDuetNode(nodes: Float64Array, distance: number) {
  let nearest = 0;
  for (let i = 1; i < nodes.length; i++) {
    if (Math.abs(nodes[i] - distance) < Math.abs(nodes[nearest] - distance)) nearest = i;
  }
  return nearest;
}
