import {
  BufferGeometry, Color, Float32BufferAttribute, Group, Line, LineBasicMaterial, OrthographicCamera, Scene,
  Vector3, WebGLRenderer,
} from "three";
import {
  duetHeadPaths, type DuetHeadGeometry,
} from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/duet-head";
import { DuetHeadEchoes, echoAges } from "./duet-head-echoes";
import { smoothFraction, type DuetFace } from "./duet-head-expression";
import { createDuetPressureView, type PressureInput } from "./duet-head-pressure";
import { createDuetAirflowView, type AirflowInput, type AirflowTract } from "./duet-head-airflow";
import { createDuetTurbulenceView, type TurbulenceInput } from "./duet-head-turbulence";
import type { NoiseBranchLayout } from "./duet-telemetry";
import { duetTractSections } from "./tract-3d-geometry";

const ink = {
  outer: 0x647e80, inner: 0x647e80, tongue: 0xc04a66, velum: 0xae662e,
  upper_lip: 0xaf385a, lower_lip: 0xaf385a, upper_teeth: 0x536871, lower_teeth: 0x536871,
  jaw_bone: 0x627577, epiglottis: 0xae662e, nasal_cavity: 0x2e7779,
  shell: 0x8ba4a3, skin: 0x506e70,
};

type Position = readonly [number, number, number];
const echoParts = ["tongue", "jaw_bone", "upper_lip", "lower_lip", "opening"] as const;
type PosePosition = { epoch: number; index: number; sample: number };
type EchoShape = (Float32Array | null)[];
type CapturedPose = PosePosition & { contours: EchoShape };

/** 調音座標はcmのまま置き、視点だけを声部ごとに反転する。 */
export function createDuetHeadScene(canvas: HTMLCanvasElement, facing: 1 | -1, onResize: () => void, airflowRandom: () => number) {
  const renderer = new WebGLRenderer({ canvas, antialias: true });
  const scene = new Scene();
  scene.background = new Color(0xf7faf7);
  const mirror = new Group();
  mirror.scale.x = facing;
  const head = new Group();
  mirror.add(head);
  scene.add(mirror);
  const pivot = new Vector3();
  let lastFace: DuetFace | undefined;
  const camera = new OrthographicCamera(-1, 1, 1, -1, 0.1, 100);
  camera.position.set(13 * facing, 12.5, 30);
  camera.lookAt(new Vector3(1.25 * facing, 8.2, 0));

  const add = (color: number) => {
    const line = new Line(new BufferGeometry(), new LineBasicMaterial({ color }));
    line.frustumCulled = false;
    head.add(line);
    return line;
  };
  const paths = duetHeadPaths.map((name) => [name, add(ink[name])] as const);
  const livePaths = new Map(paths);
  const lips = [add(ink.upper_lip), add(ink.lower_lip)];
  const lowerSkin = add(ink.skin);
  const pressureView = createDuetPressureView(add);
  const airflow = createDuetAirflowView(head, airflowRandom);
  const turbulence = createDuetTurbulenceView(head);
  let airway: AirflowTract = { sections: [], glottis: [0, 0], scale: 1 };
  const localEye = new Vector3();
  let pressureVisible = false;
  let pressureInput: PressureInput | null = null;
  const render = () => {
    if (pressureVisible) head.worldToLocal(localEye.copy(camera.position));
    pressureView.paint(pressureVisible, pressureInput, localEye);
    renderer.render(scene, camera);
  };
  const faceLines = createFaceLines(add);
  const history = new DuetHeadEchoes<CapturedPose>();
  const slots = echoAges.map(() => ({
    drawn: undefined as ReturnType<typeof history.update>[number],
    lines: echoParts.map((part) => {
      const line = add(ink[part === "opening" ? "upper_lip" : part]);
      line.material.transparent = true;
      line.material.depthTest = false;
      line.material.depthWrite = false;
      line.visible = false;
      return line;
    }),
  }));
  let scale = 0;
  let ready = false;
  let width = 0;
  let height = 0;

  const fit = () => {
    const { clientWidth: w, clientHeight: h } = canvas;
    if (!w || !h) return;
    width = w;
    height = h;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
    renderer.setSize(w, h, false);
    const halfHeight = Math.max(11.7, 8.8 * h / w);
    camera.left = -halfHeight * w / h;
    camera.right = -camera.left;
    camera.top = halfHeight;
    camera.bottom = -halfHeight;
    camera.updateProjectionMatrix();
    if (ready) {
      render();
      onResize();
    }
  };
  const resize = new ResizeObserver(fit);
  resize.observe(canvas);
  fit();

  function captureContours(): EchoShape {
    const [upper, lower] = lips.map((line) => line.geometry.getAttribute("position"));
    const middle = (upper.count - 1) / 2;
    let opening: Float32Array | null = null;
    if (upper.getY(middle) - lower.getY(middle) > 0.02 * scale) {
      // 現在描いている上下の縁を、左右の口角でつないで閉じる。
      opening = new Float32Array(3 * (upper.count + lower.count + 1));
      opening.set(upper.array);
      for (let i = 0; i < lower.count; i++) {
        const end = 3 * (lower.count - i);
        opening.set(lower.array.subarray(end - 3, end), 3 * (upper.count + i));
      }
      opening.set(upper.array.subarray(0, 3), opening.length - 3);
    }
    return echoParts.map((part) => part === "opening" ? opening
      : Float32Array.from(livePaths.get(part)!.geometry.getAttribute("position").array));
  }

  return {
    update({ paths: shape, scale: k, lipWidth, glottis, grid }: DuetHeadGeometry) {
      if (scale !== k) {
        scale = k;
        pivot.set(-2.4 * k, (-1.8 + 0.42 * (10.5 + 1.8)) * k, 0);
        lastFace = undefined;
        drawShell(add, scale);
      }
      for (const [name, line] of paths) {
        const xy = shape[name];
        writeLine(line, xy.length / 2, (i) => [xy[2 * i], xy[2 * i + 1], 0]);
      }
      for (const [index, name] of (["upper_lip", "lower_lip"] as const).entries()) {
        // 矢状面の内唇の終点を中心に、左右の口角までの曲線を描く。
        const [x, y] = shape[name].subarray(12, 14);
        writeLine(lips[index], 33, (i) => {
          const t = (i - 16) / 16;
          return [x - 0.85 * scale * t * t, y + 0.18 * scale * t * t, t * lipWidth * 0.5];
        });
      }
      const lower = shape.lower_lip;
      const jaw = shape.jaw_bone;
      const outline: Position[] = [
        [lower[lower.length - 2], lower[lower.length - 1], 0],
        [jaw[jaw.length - 2], jaw[jaw.length - 1], 0],
        [2.6 * scale, 2.6 * scale, 0], [0.8 * scale, 0.4 * scale, 0], [0, -1.8 * scale, 0],
      ];
      writeLine(lowerSkin, outline.length, (i) => outline[i]);
      airway = { sections: duetTractSections(grid, k), glottis, scale: k };
      pressureView.update(grid, airway.sections);
      ready = true;
    },
    setExpression(face: DuetFace) {
      if (!ready || (lastFace && face.puff === lastFace.puff && face.brow === lastFace.brow && face.lid === lastFace.lid
          && face.lookUp === lastFace.lookUp && face.nod === lastFace.nod && face.tilt === lastFace.tilt)) return false;
      lastFace = face;
      head.rotation.set(face.tilt, 0, face.nod);
      head.position.copy(pivot).sub(pivot.clone().applyQuaternion(head.quaternion));
      faceLines.update(face, scale);
      return true;
    },
    redraw() {
      if (ready) render();
    },
    setPressure(visible: boolean, input: PressureInput | null) {
      pressureVisible = visible;
      pressureInput = input;
    },
    readPressure() {
      return { scale, ...pressureView.read() };
    },
    setAirflow(visible: boolean, input: AirflowInput | null, elapsed: number | undefined, reset: boolean) {
      airflow.draw(airway, visible, input, elapsed, reset);
    },
    readAirflow() {
      return { glottis: airway.glottis, scale, ...airflow.read() };
    },
    setTurbulence(layout: NoiseBranchLayout | undefined, input: TurbulenceInput | null, refresh: boolean) {
      turbulence.draw(airway, layout, input, refresh);
    },
    readTurbulence() {
      return { glottis: airway.glottis, scale, ...turbulence.read() };
    },
    draw(time: number, playing: boolean, reset: boolean, pose: PosePosition) {
      const selected = history.update(time, playing, reset, () => ({ ...pose, contours: captureContours() }));
      for (const [i, slot] of slots.entries()) {
        const next = selected[i];
        for (const [part, line] of slot.lines.entries()) {
          const points = next?.pose.contours[part];
          line.visible = !!points;
          if (!points || !next) continue;
          line.material.opacity = next.opacity;
          if (slot.drawn?.pose !== next.pose) {
            writeLine(line, points.length / 3, (j) => [points[3 * j], points[3 * j + 1], points[3 * j + 2]]);
          }
        }
        slot.drawn = next;
      }
      render();
    },
    readEchoes() {
      const rims = lips.map(vertices);
      return {
        parts: echoParts,
        scale,
        lipRims: rims,
        base: captureContours().map((points) => points && Array.from(points)),
        slots: slots.map((slot) => slot.drawn && {
          time: slot.drawn.time,
          epoch: slot.drawn.pose.epoch,
          index: slot.drawn.pose.index,
          sample: slot.drawn.pose.sample,
          opacities: slot.lines.map((line) => line.visible ? line.material.opacity : null),
          contours: slot.lines.map((line) => line.visible ? vertices(line) : null),
        }),
      };
    },
    readExpression() {
      return { scale, facing, pivot: pivot.toArray(), model: head.matrixWorld.toArray(), ...faceLines.read() };
    },
    mouthView() {
      const [upper, lower] = lips.map((line) => line.geometry.getAttribute("position"));
      const i = (upper.count - 1) / 2;
      const lipCenter = new Vector3((upper.getX(i) + lower.getX(i)) / 2 + 0.15,
        (upper.getY(i) + lower.getY(i)) / 2, 0);
      const projected = head.localToWorld(lipCenter).project(camera);
      return { x: (projected.x + 1) * width / 2, y: (1 - projected.y) * height / 2,
        width, height, pxPerCm: width / (camera.right - camera.left) };
    },
    read() {
      return {
        paths: Object.fromEntries(paths.map(([name, line]) => [name, vertices(line)])),
        lipRims: lips.map(vertices),
        facing,
        viewport: [canvas.width, canvas.height],
        projection: camera.projectionMatrix.toArray(),
        view: camera.matrixWorldInverse.toArray(),
      };
    },
    dispose() {
      resize.disconnect();
      for (const line of head.children as Line<BufferGeometry, LineBasicMaterial>[]) {
        line.geometry.dispose();
        line.material.dispose();
      }
      renderer.dispose();
      renderer.forceContextLoss();
    },
  };
}

function vertices(line: Line) {
  return Array.from(line.geometry.getAttribute("position").array);
}

function writeLine(line: Line, count: number, at: (i: number) => Position) {
  let position = line.geometry.getAttribute("position");
  if (position?.count !== count) {
    line.geometry.dispose();
    line.geometry = new BufferGeometry();
    position = new Float32BufferAttribute(new Float32Array(3 * count), 3);
    line.geometry.setAttribute("position", position);
  }
  for (let i = 0; i < count; i++) position.setXYZ(i, ...at(i));
  position.needsUpdate = true;
}

/** 線画の頬と目。固定上流の表情値を、研究画面の頭部の寸法に当てはめる。 */
function createFaceLines(add: (color: number) => Line<BufferGeometry, LineBasicMaterial>) {
  const sides = [-1, 1].map((side) => {
    const cheek = add(0x9a7878);
    cheek.material.transparent = true;
    return {
      side, cheek, brow: add(ink.skin),
      upperLid: add(ink.skin), lowerLid: add(ink.skin), pupil: add(ink.skin),
    };
  });
  return {
    update(face: DuetFace, k: number) {
      const open = (0.5 + 0.2 * Math.max(0, face.brow)) * (1 - face.lid) - 0.27 * face.lid;
      for (const { side, cheek, brow, upperLid, lowerLid, pupil } of sides) {
        writeLine(cheek, 21, (i) => {
          const angle = Math.PI * 2 * i / 20;
          const x = 5.2 + 0.94 * Math.cos(angle);
          const y = 8.3 + 0.61 * Math.sin(angle);
          const r2 = ((x - 5.2) / 2.3) ** 2 + ((y - 8.3) / 2.4) ** 2;
          const puff = face.puff * (1 - r2) ** 2;
          return [k * (x + 0.55 * puff), y * k, side * k * (3.4 + 1.7 * puff)];
        });
        const eye = (t: number, rise: number): Position =>
          [k * (6.2 + 0.73 * t), k * (12 + rise * (1 - t * t)), side * k * (2.55 - 0.22 * t)];
        writeLine(upperLid, 17, (i) => eye(i / 8 - 1, open));
        writeLine(lowerLid, 17, (i) => eye(i / 8 - 1, -0.30));
        writeLine(brow, 17, (i) => {
          const t = i / 8 - 1;
          const inner = (t + 1) * 0.5;
          const mood = 0.3 * face.brow + inner * (0.22 * face.lid * Math.max(0, face.brow) - 0.28 * Math.max(0, -face.brow));
          return [k * (6.2 + 0.88 * t), k * (12.83 + mood + 0.17 * (1 - t * t)), side * 2.58 * k];
        });
        pupil.visible = face.lid < 0.66;
        writeLine(pupil, 17, (i) => {
          const angle = i * Math.PI / 8;
          const y = Math.min(open - 0.09, face.lookUp * 0.44 + 0.09);
          return [k * (6.31 + 0.12 * Math.cos(angle)), k * (12 + y + 0.11 * Math.sin(angle)), side * 2.58 * k];
        });
        cheek.material.opacity = 0.22 + 0.48 * smoothFraction(face.puff, 0, 1);
      }
    },
    read() {
      return { features: sides.map(({ cheek, brow, upperLid, lowerLid }) =>
        [vertices(cheek).slice(0, 3), ...[brow, upperLid, lowerLid].map((line) => vertices(line).slice(24, 27))]) };
    },
  };
}

/** 頭蓋と耳の輪郭は観察の向きを示す模式図。矢状面の各器官は Rust 側で求める。 */
function drawShell(add: (color: number) => Line, k: number) {
  const contour = (points: Position[]) => {
    writeLine(add(ink.skin), points.length, (i) => {
      const [x, y, z] = points[i];
      return [k * x, k * y, k * z];
    });
  };
  contour([[7.0, 9.5, 0], [8.6, 10.05, 0], [7.25, 12.25, 0], [6.9, 14.4, 0], [5.9, 16.1, 0],
    [3.4, 17.9, 0], [0.2, 18.6, 0], [-2.9, 18.0, 0], [-5.1, 16.5, 0], [-6.3, 13.8, 0],
    [-6.5, 11.2, 0], [-5.35, 8.0, 0], [-3.85, 6.3, 0], [-3.1, 2.0, 0], [-3.05, -1.8, 0]]);
  for (const azimuth of [-0.95, -0.55, 0.55, 0.95]) {
    writeLine(add(ink.shell), 41, (i) => {
      const t = Math.PI * i / 40;
      return [k * (0.15 + 6.25 * Math.cos(azimuth) * Math.cos(t)),
        k * (11.1 + 7.4 * Math.sin(t)), k * 5.75 * Math.sin(azimuth) * Math.cos(t)];
    });
  }
  for (const side of [-1, 1]) {
    writeLine(add(ink.skin), 29, (i) => {
      const t = 2 * Math.PI * i / 28;
      return [k * (-0.9 + 0.95 * Math.cos(t)), k * (9.75 + 1.64 * Math.sin(t)), side * 5.2 * k];
    });
  }
}
