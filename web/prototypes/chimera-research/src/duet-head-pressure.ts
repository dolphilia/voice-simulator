import { BufferGeometry, Float32BufferAttribute, type Line, type LineBasicMaterial, type Vector3 } from "three";
import { duetTractNodes, duetTractSections, nearestDuetNode, tractRingVertices, type DuetTractNodeInput } from "./tract-3d-geometry";

// 固定上流の src/ui/render/anatomy3d.ts と src/ui/colors.ts の描画条件
// （Jameson Hodge、MIT。研究ワークスペースの LICENSE-CHIMERA）。
const segments = 24;
const neutral = 0x1f5f8c;
const palette = [[0, 0x3a2408], [0.35, 0xc9822a], [0.6, 0xffb340], [0.82, 0xffe39a], [1, 0xfff8ec]] as const;
export type PressureInput = DuetTractNodeInput & { pressureRms: ArrayLike<number> };
export { duetTractNodes as duetPressureNodes };

export function duetPressureLevel(rms: number) {
  const level = rms > 0 ? Math.min(1, Math.max(0, Math.log10(rms / 40) / 2)) : 0;
  return level ** 0.85;
}

export function duetPressureColor(level: number) {
  const i = palette.findIndex(([stop], index) => index > 0 && level <= stop);
  if (i < 0) return palette[palette.length - 1][1];
  const [lo, a] = palette[i - 1];
  const [hi, b] = palette[i];
  const t = (level - lo) / (hi - lo);
  let color = 0;
  for (const shift of [16, 8, 0]) {
    color |= Math.round(((a >> shift) & 255) * (1 - t) + ((b >> shift) & 255) * t) << shift;
  }
  return color;
}

export function duetPressureRings(grid: readonly (readonly number[] | Float64Array)[], scale: number) {
  return pressureRings(duetTractSections(grid, scale));
}

function pressureRings(sections: ReturnType<typeof duetTractSections>) {
  return sections.filter(({ index }) => index % 2 === 0).map((section) => {
    const vertices = tractRingVertices(section, segments);
    return { ...section, vertices: [...vertices, ...vertices.slice(0, 3)] };
  });
}

type Ring = ReturnType<typeof duetPressureRings>[number];

export function duetPressureStyle(ring: Ring, eye: Vector3, source: PressureInput | null, nodes: Float64Array) {
  const [ux, uy] = ring.direction;
  const x = eye.x - ring.center.x, y = eye.y - ring.center.y, z = eye.z;
  const angle = (uy * x - ux * y) / (Math.hypot(x, y, z) || 1);
  const fade = 1 - 0.65 * angle * angle;
  if (!source || !nodes.length || source.pressureRms.length !== nodes.length) {
    return { node: null, rms: null, level: null, color: neutral, opacity: 0.45 * fade };
  }
  const node = nearestDuetNode(nodes, ring.distance);
  const rms = source.pressureRms[node];
  const level = duetPressureLevel(rms);
  return { node, rms, level, color: duetPressureColor(level), opacity: (0.25 + 0.65 * level) * fade };
}

export function createDuetPressureView(add: (color: number) => Line<BufferGeometry, LineBasicMaterial>) {
  const lines: Line<BufferGeometry, LineBasicMaterial>[] = [];
  let grid: number[][] = [];
  let rings: Ring[] = [];
  let styles: ReturnType<typeof duetPressureStyle>[] = [];
  let localEye: number[] = [];
  let nodes = new Float64Array(0);
  return {
    update(rows: Float64Array[], sections: ReturnType<typeof duetTractSections>) {
      grid = rows.map((row) => Array.from(row));
      rings = pressureRings(sections);
      for (const [i, ring] of rings.entries()) {
        if (!lines[i]) {
          const line = add(neutral);
          line.material.transparent = true;
          line.material.depthWrite = false;
          line.geometry.setAttribute("position", new Float32BufferAttribute(ring.vertices.length, 3));
          lines[i] = line;
        }
        const positions = lines[i].geometry.getAttribute("position");
        positions.array.set(ring.vertices);
        positions.needsUpdate = true;
      }
    },
    paint(visible: boolean, source: PressureInput | null, eye: Vector3) {
      localEye = eye.toArray();
      nodes = source ? duetTractNodes(source) : new Float64Array(0);
      styles = [];
      for (const [i, line] of lines.entries()) {
        line.visible = visible && i < rings.length;
        if (!line.visible) continue;
        const style = duetPressureStyle(rings[i], eye, source, nodes);
        styles.push(style);
        line.material.color.setHex(style.color);
        line.material.opacity = style.opacity;
      }
    },
    read() {
      return { grid, nodes: Array.from(nodes), eye: localEye, rings: styles.map((style, i) => ({
        row: rings[i].index, ...style, color: lines[i].material.color.getHex(),
        opacity: lines[i].material.opacity, vertices: Array.from(lines[i].geometry.getAttribute("position").array),
      })) };
    },
  };
}
