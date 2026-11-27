import {
  Box3, BufferGeometry, Color, DynamicDrawUsage, Float32BufferAttribute, Group, Line, LineBasicMaterial,
  LineLoop, LineSegments, Matrix4, PerspectiveCamera, Points, PointsMaterial, Scene, Vector3, WebGLRenderer,
} from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { tractCameraDistance, tractCameraFov, tractColors, tractRing, tractViews, type TractView } from "./tract-3d-geometry";
export type { TractView } from "./tract-3d-geometry";

export function createTractScene(
  canvas: HTMLCanvasElement, rows: number[][], segments: number, viewport?: { width: number; height: number },
) {
  const initialRings = rows.map((row) => tractRing(row, segments));
  const renderer = new WebGLRenderer({ canvas, antialias: !viewport });
  const scene = new Scene();
  scene.background = new Color(tractColors.background);
  const group = new Group();
  scene.add(group);
  const pharynx = new LineBasicMaterial({ color: tractColors.pharynx });
  const mouth = new LineBasicMaterial({ color: tractColors.mouth });
  const highlight = new LineBasicMaterial({ color: tractColors.highlight });
  const outline = new LineBasicMaterial({ color: tractColors.outline });
  const marker = new Points(
    new BufferGeometry().setFromPoints([new Vector3()]),
    new PointsMaterial({ color: highlight.color, size: 7, sizeAttenuation: false, depthTest: false }),
  );
  marker.visible = false;
  marker.frustumCulled = false;
  scene.add(marker);
  let loops: LineLoop[] = [];
  let guides: Line[] = [];
  let recordingLines: LineSegments[] = [];
  let materials: LineBasicMaterial[] = [];
  let closed: boolean[] = [];
  let selected = -1;
  function clear() {
    group.children.forEach((item) => {
      if (item instanceof Line) item.geometry.dispose();
    });
    group.clear();
  }
  function update(next: number[][], rings: typeof initialRings) {
    selected = -1;
    marker.visible = false;
    if (loops.length !== next.length) {
      clear();
      const geometry = (points: number) => new BufferGeometry().setAttribute(
        "position", new Float32BufferAttribute(points * 3, 3).setUsage(DynamicDrawUsage),
      );
      loops = next.map(() => new LineLoop(geometry(segments), mouth));
      guides = Array.from({ length: 3 }, () => new Line(geometry(next.length), outline));
      // 録画時は選択操作がないため、断面を色ごとにまとめて描く。
      recordingLines = viewport ? [mouth, pharynx].map((material) =>
        new LineSegments(geometry(next.length * segments * 2), material)) : [];
      for (const line of [...loops, ...guides, ...recordingLines]) {
        line.frustumCulled = false;
        group.add(line);
      }
      for (const loop of loops) loop.visible = !viewport;
      materials = new Array(next.length);
      closed = new Array(next.length);
    }
    const centerLine = guides[0].geometry.getAttribute("position");
    const leftLine = guides[1].geometry.getAttribute("position");
    const rightLine = guides[2].geometry.getAttribute("position");
    const leftVertex = segments * 3 / 4;
    const rightVertex = leftVertex * 3;
    for (const [i, { center, vertices }] of rings.entries()) {
      closed[i] = next[i][8] === 0;
      const material = next[i][0] === 1 ? pharynx : mouth;
      materials[i] = material;
      loops[i].material = material;
      const positions = loops[i].geometry.getAttribute("position");
      positions.array.set(vertices);
      positions.needsUpdate = true;
      centerLine.setXYZ(i, center.x, center.y, center.z);
      leftLine.setXYZ(i, vertices[leftVertex], vertices[leftVertex + 1], vertices[leftVertex + 2]);
      rightLine.setXYZ(i, vertices[rightVertex], vertices[rightVertex + 1], vertices[rightVertex + 2]);
    }
    centerLine.needsUpdate = leftLine.needsUpdate = rightLine.needsUpdate = true;
    for (const line of recordingLines) {
      const attr = line.geometry.getAttribute("position");
      let write = 0;
      for (const [i, { vertices }] of rings.entries()) {
        if (materials[i] !== line.material) continue;
        for (let j = 0; j < vertices.length; j += 3) {
          const k = (j + 3) % vertices.length;
          attr.setXYZ(write++, vertices[j], vertices[j + 1], vertices[j + 2]);
          attr.setXYZ(write++, vertices[k], vertices[k + 1], vertices[k + 2]);
        }
      }
      line.geometry.setDrawRange(0, write);
      attr.needsUpdate = true;
    }
  }

  update(rows, initialRings);
  function bounds() {
    const box = new Box3();
    for (const line of [...loops, ...guides]) {
      line.geometry.computeBoundingBox();
      box.expandByObject(line);
    }
    return box;
  }
  const box = bounds();
  const target = box.getCenter(new Vector3());
  let span = box.getSize(new Vector3()).length();
  const camera = new PerspectiveCamera(tractCameraFov, 1, 0.05, span * 12);
  const orbit = new OrbitControls(camera, canvas);
  orbit.target.copy(target);
  orbit.minDistance = 3;
  orbit.maxDistance = span * 6;
  const draw = () => renderer.render(scene, camera);
  const move = (view: TractView) => {
    orbit.target.copy(target);
    camera.position.copy(tractViews[view]).normalize().multiplyScalar(span * tractCameraDistance).add(target);
    orbit.update();
    draw();
  };
  let lastWidth = 0;
  let lastHeight = 0;
  let lastRatio = 0;
  const resize = () => {
    const { clientWidth: w, clientHeight: h } = canvas;
    if (w < 1 || h < 1) return;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    if (w === lastWidth && h === lastHeight && ratio === lastRatio) return;
    lastWidth = w;
    lastHeight = h;
    lastRatio = ratio;
    renderer.setPixelRatio(ratio);
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    draw();
  };
  const observer = viewport ? undefined : new ResizeObserver(resize);
  observer?.observe(canvas);
  if (viewport) {
    renderer.setSize(viewport.width, viewport.height, false);
    camera.aspect = viewport.width / viewport.height;
    camera.updateProjectionMatrix();
  }
  orbit.addEventListener("change", draw);

  return {
    replace(next: number[][]) {
      update(next, next.map((row) => tractRing(row, segments)));
    },
    select(index: number) {
      if (selected >= 0) loops[selected].material = materials[selected];
      selected = index;
      loops[index].material = highlight;
      marker.visible = closed[index];
      if (marker.visible) marker.position.fromBufferAttribute(loops[index].geometry.getAttribute("position"), 0);
      draw();
    },
    warmup() {
      if (!viewport) resize();
      move("angled");
      marker.visible = true;
      draw();
      renderer.getContext().finish();
      marker.visible = false;
    },
    fit(view: TractView) {
      const box = bounds();
      box.getCenter(target);
      span = box.getSize(new Vector3()).length();
      camera.far = span * 12;
      camera.updateProjectionMatrix();
      orbit.maxDistance = span * 6;
      move(view);
    },
    move,
    snapshot() {
      return loops.map(({ geometry }) => Array.from(geometry.getAttribute("position").array));
    },
    selectedMarker() {
      return marker.visible ? marker.position.toArray() : null;
    },
    projection() {
      return new Matrix4().multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse).toArray();
    },
    projectSection(index: number) {
      const positions = loops[index].geometry.getAttribute("position");
      const point = new Vector3();
      return Array.from({ length: positions.count }, (_, i) => {
        point.fromBufferAttribute(positions, i).project(camera);
        return [point.x, point.y];
      });
    },
    render: draw,
    close() {
      observer?.disconnect();
      orbit.removeEventListener("change", draw);
      orbit.dispose();
      clear();
      for (const material of [pharynx, mouth, outline, highlight]) material.dispose();
      marker.geometry.dispose();
      marker.material.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
    },
  };
}

export function warmTractScene(
  canvas: HTMLCanvasElement, sections: number, segments: number, viewport?: { width: number; height: number },
) {
  // 計測結果を受け取る前に線と閉鎖マーカーの描画資源を確保する。
  const rows = Array.from({ length: sections }, (_, i) => {
    const y = i / 12;
    return [1, 0, y, 1, y, 0.5, y, 1, 1, 0.75, y];
  });
  const scene = createTractScene(canvas, rows, segments, viewport);
  try {
    scene.warmup();
    return scene;
  } catch (failure) {
    scene.close();
    throw failure;
  }
}
