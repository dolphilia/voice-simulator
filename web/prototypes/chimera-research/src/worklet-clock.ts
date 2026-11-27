export const STARTUP_CONTIGUOUS_QUANTA = 8;

export class WorkletStartup {
  firstContextFrame?: number;
  contiguousFirstContextFrame?: number;
  callbacks = 0;
  discontinuities = 0;
  private nextFrame?: number;
  private consecutive = 0;

  ready(frame: number, quantum: number): boolean {
    this.firstContextFrame ??= frame;
    if (this.nextFrame !== undefined && this.nextFrame !== frame) {
      this.consecutive = 0;
      this.discontinuities++;
    }
    if (this.consecutive === STARTUP_CONTIGUOUS_QUANTA) return true;
    if (this.consecutive === 0) this.contiguousFirstContextFrame = frame;
    this.nextFrame = frame + quantum;
    this.consecutive++;
    this.callbacks++;
    return false;
  }
}
