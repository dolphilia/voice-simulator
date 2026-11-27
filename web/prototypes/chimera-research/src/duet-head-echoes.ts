// 時間と不透明度は固定上流の src/ui/render/anatomy3d.ts を参照
// （Jameson Hodge、MIT。研究ワークスペースの LICENSE-CHIMERA）。
const captureInterval = 0.028;
const retention = 0.12;
const maximumOffset = 0.016;
export const echoAges = [0.09, 0.06, 0.03] as const;

export function advanceDuetMotionTime(time: number, elapsedMs: number) {
  return time + Math.min(0.05, Math.max(0, elapsedMs / 1000));
}

export class DuetHeadEchoes<T> {
  private readonly history: { time: number; pose: T }[] = [];
  private lastCapture = -1;

  update(time: number, playing: boolean, reset: boolean, capture: () => T) {
    if (reset) {
      this.history.length = 0;
      this.lastCapture = -1;
    }
    if (!playing) return echoAges.map(() => undefined);

    if (time - this.lastCapture >= captureInterval) {
      this.lastCapture = time;
      this.history.push({ time, pose: capture() });
      while (time - this.history[0].time > retention) this.history.shift();
    }

    return echoAges.map((age, index) => {
      let offset = maximumOffset;
      let nearest: typeof this.history[number] | undefined;
      for (const candidate of this.history) {
        const distance = Math.abs(candidate.time - (time - age));
        if (distance < offset) {
          nearest = candidate;
          offset = distance;
        }
      }
      return nearest && { ...nearest, opacity: 0.10 + 0.07 * index };
    });
  }
}
