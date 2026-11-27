import type { LiveTractSample } from "./fixed-worklet-types";
import { warmTractScene } from "./tract-3d-scene";
import { tractColors } from "./tract-3d-geometry";
import trial from "../../../../research/experiments/chimera-rebuild/cases/worklet-tract-3d.json";

const imageRect = [56, 150, 608, 300] as const;
const codeRect = [104, 1016, 512, 22] as const;
const codeBits = 32;

export class RecordedTract {
  private readonly gl = document.createElement("canvas");
  private readonly image = document.createElement("canvas");
  private readonly imagePaint: CanvasRenderingContext2D;
  private readonly scene: ReturnType<typeof warmTractScene>;
  private readonly composed: { frame: number; contextFrame: number; composedContextFrame: number }[] = [];
  private readonly unsupported: { frame: number; reason: string }[] = [];
  private projection?: number[];
  private newest?: LiveTractSample;
  private visible?: LiveTractSample;

  constructor() {
    const [, , width, height] = imageRect;
    this.image.width = width;
    this.image.height = height;
    const paint = this.image.getContext("2d");
    if (!paint) throw new Error("録画用の声道画像を準備できません");
    this.imagePaint = paint;
    const { expected_sections, ring_segments } = trial.measurement;
    this.scene = warmTractScene(this.gl, expected_sections, ring_segments, { width: width / 2, height: height / 2 });
    // 描画と転写の準備を済ませてから、音声と動画の時計を開始する。
    try {
      this.imagePaint.drawImage(this.gl, 0, 0, width, height);
      this.imagePaint.getImageData(0, 0, 1, 1);
    } catch (failure) {
      this.scene.close();
      throw failure;
    }
  }

  receive(sample: LiveTractSample) {
    this.newest = sample;
  }

  paint(paint: CanvasRenderingContext2D, contextFrame: number, active: boolean) {
    const sample = this.newest;
    if (sample && sample.contextFrame < contextFrame) {
      this.newest = undefined;
      try {
        this.scene.replace(sample.grid.rows);
        if (!this.projection) this.scene.fit("angled");
        else this.scene.render();
        // WebGLが描いた直後に写し、次の観測までは2D画像を使う。
        this.imagePaint.drawImage(this.gl, 0, 0, this.image.width, this.image.height);
        this.drawLip(sample.grid.rows);
        this.projection ??= this.scene.projection();
        this.visible = sample;
        this.composed.push({ frame: sample.grid.frame, contextFrame: sample.contextFrame,
          composedContextFrame: contextFrame });
      } catch (failure) {
        this.unsupported.push({ frame: sample.grid.frame,
          reason: failure instanceof Error ? failure.message : String(failure) });
        this.visible = undefined;
      }
    }
    if (this.visible) paint.drawImage(this.image, imageRect[0], imageRect[1]);
    paint.fillStyle = "#e5f1e9";
    paint.font = "26px monospace";
    const frame = active ? this.visible?.grid.frame : undefined;
    const code = (frame ?? -1) + 1;
    const label = !active ? "歌唱終了" : frame === undefined ? "声道断面を待機中" : `声道断面 · 出力フレーム ${frame}`;
    paint.fillText(label, 360, 484);
    const [x, y, width, height] = codeRect;
    const cell = width / codeBits;
    for (let bit = 0; bit < codeBits; bit++) {
      paint.fillStyle = Math.floor(code / 2 ** bit) % 2 ? "#f4f7ee" : "#142620";
      paint.fillRect(x + bit * cell, y, cell, height);
    }
  }

  observation() {
    return { imageRect, codeRect, codeBits, projection: this.projection,
      ringSegments: trial.measurement.ring_segments, composed: this.composed, unsupported: this.unsupported };
  }

  private drawLip(rows: number[][]) {
    const index = rows.length - 1;
    const points = this.scene.projectSection(index).map(([x, y]) =>
      [(x + 1) * this.image.width / 2, (1 - y) * this.image.height / 2]);
    const paint = this.imagePaint;
    const [x, y] = points[0];
    // 動画の色差圧縮でも、同じ三次元頂点の輪郭を追える太さにする。
    paint.beginPath();
    if (rows[index][8] === 0) {
      paint.arc(x, y, 3.5, 0, 2 * Math.PI);
      paint.fillStyle = tractColors.highlight;
      paint.fill();
      return;
    }
    paint.moveTo(x, y);
    for (const [px, py] of points.slice(1)) paint.lineTo(px, py);
    paint.closePath();
    paint.strokeStyle = tractColors.highlight;
    paint.lineJoin = "round";
    paint.lineWidth = 4;
    paint.stroke();
  }

  close() {
    this.scene.close();
  }
}
