import { BufferGeometry, DynamicDrawUsage, Float32BufferAttribute, Group, LineBasicMaterial, LineSegments } from "three";
import { duetTractNodes, nearestDuetNode, type duetTractSections, type DuetTractNodeInput } from "./tract-3d-geometry";

// 固定上流の Anatomy3D.drawParticles / airPoint（Jameson Hodge、MIT）。
const particleCount = 200;
const opacities = [0.16, 0.36, 0.56] as const;
type Point = readonly [number, number, number];
export type Particle = { s: number; u: number; v: number; life: number; previous: Point | null };
export type AirflowInput = DuetTractNodeInput & {
  phAreas: ArrayLike<number>; orAreas: ArrayLike<number>; flow: ArrayLike<number>;
};
export type AirflowTract = {
  sections: ReturnType<typeof duetTractSections>; glottis: readonly [number, number]; scale: number;
};
type Trail = { particle: number; from: Point; to: Point; band: number };

export function airwayPoint({ sections, glottis, scale }: AirflowTract, s: number, u: number, v: number): Point | null {
  if (sections.length < 2) return null;
  const first = sections[0];
  if (s <= first.distance) {
    const t = Math.max(0, s / Math.max(0.01, first.distance));
    return [glottis[0] + (first.center.x - glottis[0]) * t + u * 0.3 * scale,
      glottis[1] + (first.center.y - glottis[1]) * t, v * 0.45 * scale];
  }
  let lo = 0, hi = sections.length - 1;
  if (s >= sections[hi].distance) return null;
  while (hi - lo > 1) {
    const mid = (lo + hi) >>> 1;
    if (sections[mid].distance <= s) lo = mid;
    else hi = mid;
  }
  const a = sections[lo], b = sections[hi];
  const t = (s - a.distance) / Math.max(1e-6, b.distance - a.distance);
  const lerp = (x: number, y: number) => x + (y - x) * t;
  const across = lerp(a.radius, b.radius) * u * 0.82;
  return [lerp(a.center.x, b.center.x) + lerp(a.direction[0], b.direction[0]) * across,
    lerp(a.center.y, b.center.y) + lerp(a.direction[1], b.direction[1]) * across,
    lerp(a.width, b.width) * v * 0.82];
}

export class DuetAirflow {
  private readonly particles: Particle[];

  constructor(private readonly random: () => number, initial?: readonly Particle[]) {
    this.particles = initial?.map((particle) => ({ ...particle }))
      ?? Array.from({ length: particleCount }, () => ({ s: random() * 17, u: 2 * random() - 1,
        v: 2 * random() - 1, life: random(), previous: null }));
  }

  resetTrails() {
    for (const particle of this.particles) particle.previous = null;
  }

  step(tract: AirflowTract, input: AirflowInput, elapsed: number) {
    const dt = Math.max(0, Math.min(0.05, elapsed));
    const nodes = duetTractNodes(input);
    const trails: Trail[] = [];
    if (!nodes.length || nodes.length !== input.flow.length || input.phAreas.length !== input.nPh
        || input.orAreas.length !== input.nOr || tract.sections.length < 2) return { dt, nodes, trails };
    const lip = tract.sections[tract.sections.length - 1].distance;
    for (const [index, particle] of this.particles.entries()) {
      const node = nearestDuetNode(nodes, particle.s);
      const area = node < input.nPh ? input.phAreas[node] : input.orAreas[node - input.nPh];
      const velocity = input.flow[node] / Math.max(0.05, area);
      const speed = Math.sign(velocity) * 2.2 * Math.log1p(Math.abs(velocity) / 30);
      particle.s += speed * dt;
      particle.life -= dt * 0.25;
      const outOfRange = particle.s < 0 || particle.s > lip;
      if (particle.life <= 0 || (outOfRange && Math.abs(velocity) >= 3)) {
        particle.s = this.random() * 0.8;
        particle.u = 2 * this.random() - 1;
        particle.v = 2 * this.random() - 1;
        particle.life = 0.6 + this.random() * 0.8;
        particle.previous = null;
        continue;
      }
      const point = airwayPoint(tract, particle.s, particle.u, particle.v);
      if (!point) continue;
      if (particle.previous) {
        const band = Math.min(2, Math.floor(Math.min(1, Math.abs(speed) / 6) * Math.min(1, particle.life) * 3));
        trails.push({ particle: index, from: particle.previous, to: point, band });
      }
      particle.previous = point;
    }
    return { dt, nodes, trails };
  }

  snapshot() {
    return this.particles.map((particle) => ({ ...particle }));
  }
}

export function createDuetAirflowView(head: Group, random: () => number) {
  const model = new DuetAirflow(random);
  const batches = opacities.map((opacity) => {
    const geometry = new BufferGeometry();
    const data = new Float32BufferAttribute(6 * particleCount, 3).setUsage(DynamicDrawUsage);
    geometry.setAttribute("position", data);
    geometry.setDrawRange(0, 0);
    const mesh = new LineSegments(geometry, new LineBasicMaterial({ color: 0xa56724, transparent: true, opacity, depthWrite: false }));
    mesh.frustumCulled = false;
    head.add(mesh);
    return { mesh, data, count: 0 };
  });
  let frame: ReturnType<DuetAirflow["step"]> | undefined;
  let source: AirflowInput | null = null;
  let enabled = true;
  return {
    draw(tract: AirflowTract, visible: boolean, input: AirflowInput | null, elapsed: number | undefined, reset: boolean) {
      if (reset || enabled !== visible) model.resetTrails();
      const previous = source;
      enabled = visible;
      source = enabled ? input : null;
      if (!source) frame = undefined;
      else if (elapsed !== undefined || !previous || reset) frame = model.step(tract, source, elapsed ?? 0);
      for (const batch of batches) batch.count = 0;
      for (const trail of frame?.trails ?? []) {
        const batch = batches[trail.band];
        const offset = 6 * batch.count++;
        batch.data.array.set(trail.from, offset);
        batch.data.array.set(trail.to, offset + 3);
      }
      for (const batch of batches) {
        batch.mesh.geometry.setDrawRange(0, 2 * batch.count);
        batch.data.needsUpdate = true;
      }
    },
    read() {
      return { enabled, dt: frame?.dt ?? 0, nodes: Array.from(frame?.nodes ?? []),
        flow: Array.from(source?.flow ?? []), areas: [...Array.from(source?.phAreas ?? []), ...Array.from(source?.orAreas ?? [])],
        particles: model.snapshot(), trails: frame?.trails ?? [],
        vertices: batches.map(({ data, count }) => Array.from(data.array.subarray(0, 6 * count))) };
    },
  };
}
