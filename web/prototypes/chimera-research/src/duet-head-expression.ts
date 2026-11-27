// 表情の係数と更新順は固定上流の src/ui/render/expression.ts を参照
// （Jameson Hodge、MIT。研究ワークスペースの LICENSE-CHIMERA）。
const limit = (value: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, value));
export function smoothFraction(value: number, lo: number, hi: number) {
  const t = limit((value - lo) / (hi - lo), 0, 1);
  return t * t * (3 - 2 * t);
}
const follow = (value: number, target: number, seconds: number, tau: number) =>
  value + (target - value) * -Math.expm1(-seconds / tau);

export function duetMouthPressure(values: ArrayLike<number>, pharyngealNodes: number, oralNodes: number) {
  const node = pharyngealNodes + oralNodes - 3;
  return node >= pharyngealNodes && node < values.length ? values[node] / 980.665 : 0;
}

export function duetBeatStep(time: number, bpm = 0, downbeat = 0) {
  const step = Math.floor((time - downbeat) * bpm * 4 / 60);
  return bpm > 0 && step >= 0 ? step % 16 : -1;
}

export function duetExpressionRandom(seed: number) {
  return () => {
    seed = (Math.imul(1664525, seed) + 1013904223) >>> 0;
    return seed / 4294967296;
  };
}

class DampedMotion {
  position = 0;
  velocity = 0;
  private readonly omega: number;

  constructor(hz: number, private readonly damping: number) {
    this.omega = 2 * Math.PI * hz;
  }

  integrate(target: number, seconds: number) {
    const n = Math.max(1, Math.ceil(seconds / 0.008));
    const step = seconds / n;
    for (let i = 0; i < n; i++) {
      const force = this.omega ** 2 * (target - this.position) - 2 * this.damping * this.omega * this.velocity;
      this.velocity += force * step;
      this.position += this.velocity * step;
    }
    return this.position;
  }
}

export type DuetFace = { puff: number; brow: number; lid: number; lookUp: number; nod: number; tilt: number };
export type DuetVoiceExpression = {
  pressure: number; f0: number; gate: number; voicing: number; outRms: number; beatStep: number;
};
export const neutralDuetFace: DuetFace = { puff: 0, brow: 0, lid: 0, lookUp: 0, nod: 0, tilt: 0 };

export class DuetHeadExpression {
  private readonly cheeks = new DampedMotion(6.5, 0.32);
  private readonly neck = new DampedMotion(2.4, 0.42);
  private readonly sway = new DampedMotion(3.2, 0.3);
  private time = 0;
  private referencePitch = NaN;
  private recentPitch = NaN;
  private heldSeconds = 0;
  private closure = 0;
  private brow = 0;
  private lastBeat = -1;
  private blinkStart = -1;
  private doubleBlink = false;
  private nextBlink: number;

  constructor(private readonly random: () => number) {
    this.nextBlink = 1.5 + 2 * random();
  }

  update(input: DuetVoiceExpression | null, elapsed: number): DuetFace {
    const dt = limit(elapsed, 0, 0.5);
    this.time += dt;
    const targetPuff = smoothFraction(input?.pressure ?? 0, 1.5, 7);
    const puff = limit(this.cheeks.integrate(targetPuff, dt), -0.35, 1.25);
    let deviation = 0;
    let wobble = 0;
    const voiced = input && input.voicing > 0.45 && input.gate > 0.3 && input.f0 > 30 && input.outRms > 0.004;
    if (voiced) {
      const pitch = Math.log2(input.f0);
      if (!Number.isFinite(this.referencePitch) || Math.abs(12 * (pitch - this.referencePitch)) > 14) {
        this.referencePitch = this.recentPitch = pitch;
      }
      this.referencePitch = follow(this.referencePitch, pitch, dt, 5);
      if (Math.abs(12 * (pitch - this.recentPitch)) > 2.5) {
        this.recentPitch = pitch;
        this.heldSeconds = 0;
      }
      this.recentPitch = follow(this.recentPitch, pitch, dt, 0.35);
      this.heldSeconds += dt;
      deviation = 12 * (pitch - this.referencePitch);
      wobble = 12 * (pitch - this.recentPitch);
    } else {
      this.heldSeconds = 0;
    }
    this.brow = follow(this.brow, limit(deviation / 6, -0.7, 1), dt, voiced ? 0.12 : 0.45);
    const closeTarget = 0.92 * smoothFraction(this.heldSeconds, 0.9, 1.9) * smoothFraction(this.brow, 0.15, 0.55);
    this.closure = follow(this.closure, closeTarget, dt, closeTarget > this.closure ? 0.35 : 0.08);
    if (this.time >= this.nextBlink && this.closure < 0.2) {
      this.blinkStart = this.time;
      this.doubleBlink = !this.doubleBlink && this.random() < 0.18;
      this.nextBlink = this.time + (this.doubleBlink ? 0.28 : 2 + 4.5 * this.random());
    }
    const phase = (this.time - this.blinkStart) / 0.17;
    const blink = this.blinkStart >= 0 && phase < 1 ? Math.sin(Math.PI * phase) ** 0.7 : 0;

    const step = input?.beatStep ?? -1;
    if (step >= 0 && this.lastBeat >= 0 && step !== this.lastBeat) {
      if (step < this.lastBeat) this.neck.velocity -= 1.3;
      else if (Math.floor(step / 4) !== Math.floor(this.lastBeat / 4)) this.neck.velocity -= 0.8;
    }
    this.lastBeat = step;
    const nod = this.neck.integrate(0.13 * this.brow, dt);
    const sway = smoothFraction(this.heldSeconds, 0.6, 2) * 0.07 * Math.sin(this.time * 1.7);
    const tilt = this.sway.integrate(sway + 0.05 * limit(wobble, -1.5, 1.5), dt);
    return { puff, brow: this.brow, lid: Math.max(this.closure, blink), lookUp: 0.32 * Math.max(0, this.brow), nod, tilt };
  }

  read() {
    return {
      time: this.time, referencePitch: this.referencePitch, recentPitch: this.recentPitch,
      heldSeconds: this.heldSeconds, closure: this.closure, lastBeat: this.lastBeat,
      motions: [this.cheeks, this.neck, this.sway].map(({ position, velocity }) => [position, velocity]),
    };
  }
}
