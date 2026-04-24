export const MATERIALS = {
  air: 0,
  rigid: 1,
  absorber: 2,
  transmissive: 3,
  scatter: 4,
  frequency: 5,
} as const;

export type MaterialId = (typeof MATERIALS)[keyof typeof MATERIALS];
export type MaterialKey = keyof typeof MATERIALS;
export type SourceMode = "tone" | "pulse";

export interface FdtdConfig {
  width: number;
  height: number;
  courant: number;
  edgeAbsorbCells: number;
  edgeAbsorbStrength: number;
  sourceFrequency: number;
  sampleRate: number;
}

export interface Point {
  x: number;
  y: number;
}

export interface Snapshot {
  width: number;
  height: number;
  pressure: Float32Array;
  material: Uint8Array;
  source: Point;
  ear: Point;
}

const DEFAULT_CONFIG: FdtdConfig = {
  width: 104,
  height: 64,
  courant: 0.45,
  edgeAbsorbCells: 10,
  edgeAbsorbStrength: 0.13,
  sourceFrequency: 440,
  sampleRate: 44_100,
};

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function index(x: number, y: number, width: number): number {
  return y * width + x;
}

export class AcousticFdtd2D {
  readonly config: FdtdConfig;
  readonly pressure: Float32Array;
  readonly vx: Float32Array;
  readonly vy: Float32Array;
  readonly material: Uint8Array;

  private readonly damping: Float32Array;
  private readonly frequencyMemory: Float32Array;
  private source: Point;
  private ear: Point;
  private stepIndex = 0;
  private recording: number[] = [];
  private recordingEnabled = true;

  constructor(config: Partial<FdtdConfig> = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config };
    const { width, height } = this.config;
    this.pressure = new Float32Array(width * height);
    this.vx = new Float32Array((width + 1) * height);
    this.vy = new Float32Array(width * (height + 1));
    this.material = new Uint8Array(width * height);
    this.damping = new Float32Array(width * height);
    this.frequencyMemory = new Float32Array(width * height);
    this.source = { x: Math.floor(width * 0.22), y: Math.floor(height * 0.5) };
    this.ear = { x: Math.floor(width * 0.78), y: Math.floor(height * 0.5) };
    this.computeDamping();
    this.addDefaultObstacles();
  }

  getSource(): Point {
    return { ...this.source };
  }

  getEar(): Point {
    return { ...this.ear };
  }

  setSource(point: Point): void {
    this.source = this.clampPoint(point);
  }

  setEar(point: Point): void {
    this.ear = this.clampPoint(point);
  }

  setMaterial(point: Point, material: MaterialId, radius = 1): void {
    const center = this.clampPoint(point);
    for (let dy = -radius; dy <= radius; dy += 1) {
      for (let dx = -radius; dx <= radius; dx += 1) {
        if (dx * dx + dy * dy > radius * radius) {
          continue;
        }
        const x = center.x + dx;
        const y = center.y + dy;
        if (!this.contains(x, y)) {
          continue;
        }
        this.material[index(x, y, this.config.width)] = material;
      }
    }
  }

  clearMaterials(): void {
    this.material.fill(MATERIALS.air);
  }

  resetField(): void {
    this.pressure.fill(0);
    this.vx.fill(0);
    this.vy.fill(0);
    this.frequencyMemory.fill(0);
    this.stepIndex = 0;
  }

  clearRecording(): void {
    this.recording = [];
  }

  getRecording(): Float32Array {
    return Float32Array.from(this.recording);
  }

  setRecordingEnabled(enabled: boolean): void {
    this.recordingEnabled = enabled;
  }

  recomputeDamping(): void {
    this.computeDamping();
  }

  injectImpulse(amount = 1): void {
    const sourceIndex = index(this.source.x, this.source.y, this.config.width);
    this.pressure[sourceIndex] += amount;
  }

  step(sourceMode: SourceMode): void {
    this.updateVelocityX();
    this.updateVelocityY();
    this.updatePressure(sourceMode);
    this.applyCellDamping();
    this.recordEar();
    this.stepIndex += 1;
  }

  getSnapshot(): Snapshot {
    return {
      width: this.config.width,
      height: this.config.height,
      pressure: this.pressure,
      material: this.material,
      source: this.getSource(),
      ear: this.getEar(),
    };
  }

  private addDefaultObstacles(): void {
    const cx = Math.floor(this.config.width * 0.5);
    const y0 = Math.floor(this.config.height * 0.22);
    const y1 = Math.floor(this.config.height * 0.78);
    for (let y = y0; y <= y1; y += 1) {
      if (Math.abs(y - Math.floor(this.config.height * 0.5)) < 8) {
        continue;
      }
      this.material[index(cx, y, this.config.width)] = MATERIALS.rigid;
    }
  }

  private updateVelocityX(): void {
    const { width, height, courant } = this.config;
    for (let y = 0; y < height; y += 1) {
      for (let x = 1; x < width; x += 1) {
        const left = index(x - 1, y, width);
        const right = index(x, y, width);
        const velocityIndex = y * (width + 1) + x;
        if (this.blocksFace(left, right, x, y)) {
          this.vx[velocityIndex] = 0;
          continue;
        }
        this.vx[velocityIndex] -= courant * (this.pressure[right] - this.pressure[left]);
      }
      this.vx[y * (width + 1)] = 0;
      this.vx[y * (width + 1) + width] = 0;
    }
  }

  private updateVelocityY(): void {
    const { width, height, courant } = this.config;
    for (let y = 1; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) {
        const up = index(x, y - 1, width);
        const down = index(x, y, width);
        const velocityIndex = y * width + x;
        if (this.blocksFace(up, down, x, y)) {
          this.vy[velocityIndex] = 0;
          continue;
        }
        this.vy[velocityIndex] -= courant * (this.pressure[down] - this.pressure[up]);
      }
    }
    this.vy.fill(0, 0, width);
    this.vy.fill(0, height * width, (height + 1) * width);
  }

  private updatePressure(sourceMode: SourceMode): void {
    const { width, height, courant } = this.config;
    for (let y = 0; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) {
        const cellIndex = index(x, y, width);
        if (this.material[cellIndex] === MATERIALS.rigid) {
          this.pressure[cellIndex] = 0;
          continue;
        }
        const divergence =
          this.vx[y * (width + 1) + x + 1] -
          this.vx[y * (width + 1) + x] +
          this.vy[(y + 1) * width + x] -
          this.vy[y * width + x];
        this.pressure[cellIndex] -= courant * divergence;
      }
    }

    const sourceIndex = index(this.source.x, this.source.y, width);
    if (sourceMode === "tone") {
      const t = this.stepIndex / this.config.sampleRate;
      const envelope = 0.5 + 0.5 * Math.sin(2 * Math.PI * 1.8 * t);
      this.pressure[sourceIndex] +=
        0.08 * envelope * Math.sin(2 * Math.PI * this.config.sourceFrequency * t);
    }
  }

  private applyCellDamping(): void {
    const { width, height } = this.config;
    for (let y = 0; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) {
        const cellIndex = index(x, y, width);
        const material = this.material[cellIndex];
        let factor = this.damping[cellIndex];

        if (material === MATERIALS.absorber) {
          factor *= 0.82;
        } else if (material === MATERIALS.transmissive) {
          factor *= 0.94;
        } else if (material === MATERIALS.scatter) {
          factor *= (x + y) % 2 === 0 ? 0.9 : 0.75;
          this.pressure[cellIndex] *= (x * 13 + y * 7) % 5 === 0 ? -0.35 : 1;
        } else if (material === MATERIALS.frequency) {
          const memory = this.frequencyMemory[cellIndex] * 0.86 + this.pressure[cellIndex] * 0.14;
          const high = this.pressure[cellIndex] - memory;
          this.frequencyMemory[cellIndex] = memory;
          this.pressure[cellIndex] = memory + high * 0.35;
          factor *= 0.96;
        }

        this.pressure[cellIndex] *= factor;
      }
    }

    this.dampVelocityFaces();
  }

  private dampVelocityFaces(): void {
    const { width, height } = this.config;
    for (let y = 0; y < height; y += 1) {
      for (let x = 1; x < width; x += 1) {
        const left = this.damping[index(x - 1, y, width)];
        const right = this.damping[index(x, y, width)];
        this.vx[y * (width + 1) + x] *= Math.min(left, right);
      }
    }
    for (let y = 1; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) {
        const up = this.damping[index(x, y - 1, width)];
        const down = this.damping[index(x, y, width)];
        this.vy[y * width + x] *= Math.min(up, down);
      }
    }
  }

  private blocksFace(a: number, b: number, x: number, y: number): boolean {
    const ma = this.material[a];
    const mb = this.material[b];
    if (ma === MATERIALS.rigid || mb === MATERIALS.rigid) {
      return true;
    }
    if (ma === MATERIALS.scatter || mb === MATERIALS.scatter) {
      return (x * 17 + y * 31 + this.stepIndex) % 7 === 0;
    }
    return false;
  }

  private recordEar(): void {
    if (!this.recordingEnabled) {
      return;
    }
    const earIndex = index(this.ear.x, this.ear.y, this.config.width);
    this.recording.push(this.pressure[earIndex]);
    if (this.recording.length > this.config.sampleRate * 6) {
      this.recording.splice(0, this.recording.length - this.config.sampleRate * 6);
    }
  }

  private computeDamping(): void {
    const { width, height, edgeAbsorbCells, edgeAbsorbStrength } = this.config;
    for (let y = 0; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) {
        const edgeDistance = Math.min(x, y, width - 1 - x, height - 1 - y);
        const edgeAmount = clamp((edgeAbsorbCells - edgeDistance) / edgeAbsorbCells, 0, 1);
        const damping = 1 - edgeAbsorbStrength * edgeAmount * edgeAmount;
        this.damping[index(x, y, width)] = damping;
      }
    }
  }

  private clampPoint(point: Point): Point {
    return {
      x: Math.round(clamp(point.x, 1, this.config.width - 2)),
      y: Math.round(clamp(point.y, 1, this.config.height - 2)),
    };
  }

  private contains(x: number, y: number): boolean {
    return x >= 0 && y >= 0 && x < this.config.width && y < this.config.height;
  }
}
