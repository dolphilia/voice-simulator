import { useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  createDuetHeadGeometry,
} from "../../../../research/experiments/chimera-rebuild/crates/vocal-wasm/host/duet-head";
import { createDuetHeadScene } from "./duet-head-scene";
import { createDuetMouthOverlay } from "./duet-mouth-words";
import {
  duetExpressionRandom, DuetHeadExpression, duetMouthPressure, neutralDuetFace, type DuetVoiceExpression,
} from "./duet-head-expression";
import type { DuetTeleTrack, NoiseBranchLayout } from "./duet-telemetry";
import type { Word } from "./duet-words";
import { loadFixedModule } from "./render-fixed-voice";

type Clock = { time: number; epoch: number; playing: boolean; motionTime: number; motionStep: number };
export type DuetHeadObservation = ReturnType<DuetTeleTrack["frame"]> & {
  name: string; track: DuetTeleTrack; word: Word | null; beatStep: number; noiseBranches?: NoiseBranchLayout;
};
type Runtime = {
  scene: ReturnType<typeof createDuetHeadScene>;
  geometry: ReturnType<typeof createDuetHeadGeometry>;
  mouth: ReturnType<typeof createDuetMouthOverlay>;
  expression: DuetHeadExpression;
  expressive: boolean;
  express: (input: DuetVoiceExpression | null, reset: boolean) => boolean;
  snapshot?: { clock: Clock; index: number; sample: number; artic: Float32Array };
};

const describeError = (error: unknown) => error instanceof Error ? error.message : String(error);

export function DuetHeads({ observations, clock, expressive, pressureVisible, airflowVisible, turbulenceVisible }: {
  observations: DuetHeadObservation[]; clock: Clock; expressive: boolean;
  pressureVisible: boolean; airflowVisible: boolean; turbulenceVisible: boolean;
}) {
  const [module, setModule] = useState<WebAssembly.Module>();
  const [error, setError] = useState("");
  useEffect(() => {
    const abort = new AbortController();
    void loadFixedModule(abort.signal).then((value) => {
      if (!abort.signal.aborted) setModule(value);
    }).catch((reason: unknown) => {
      if (!abort.signal.aborted) setError(describeError(reason));
    });
    return () => abort.abort();
  }, []);
  if (error) return <p role="status">三次元表示を準備できませんでした。{error}</p>;
  if (!module) return <p role="status">三次元頭部を準備中</p>;
  return <section className="duet-heads" aria-label="声部別の三次元頭部">
    {observations.map((observation, index) => <DuetHead key={index} module={module} observation={observation} clock={clock}
      seed={1401 + index} expressive={expressive} pressureVisible={pressureVisible} airflowVisible={airflowVisible}
      turbulenceVisible={turbulenceVisible}
      facing={index > 0 && index === observations.length - 1 ? -1 : 1} />)}
  </section>;
}

function DuetHead({ module, observation, clock, facing, seed, expressive, pressureVisible, airflowVisible, turbulenceVisible }: {
  module: WebAssembly.Module; observation: DuetHeadObservation; clock: Clock; facing: 1 | -1;
  seed: number; expressive: boolean; pressureVisible: boolean; airflowVisible: boolean; turbulenceVisible: boolean;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const layer = useRef<HTMLDivElement>(null);
  const runtime = useRef<Runtime | undefined>(undefined);
  const [error, setError] = useState("");
  const { track, name } = observation;
  useLayoutEffect(() => {
    const target = canvas.current;
    const overlay = layer.current;
    if (!target || !overlay) return;
    let player: Runtime;
    let lastUpdate = performance.now();
    let tick = 0;
    let expressionFrame: {
      elapsed: number; reset: boolean; input: DuetVoiceExpression | null; face: typeof neutralDuetFace;
    } | undefined;
    try {
      const geometry = createDuetHeadGeometry(module, track.body);
      const scene = createDuetHeadScene(target, facing, () => runtime.current?.mouth.resize(), duetExpressionRandom(seed + 308));
      const makeExpression = () => new DuetHeadExpression(duetExpressionRandom(seed));
      player = {
        geometry, scene, mouth: createDuetMouthOverlay(overlay, scene.mouthView, facing),
        expression: makeExpression(), expressive: true,
        express(input, reset) {
          const now = performance.now();
          const elapsed = Math.min(0.5, Math.max(0, (now - lastUpdate) / 1000));
          lastUpdate = now;
          if (reset) player.expression = makeExpression();
          const face = player.expressive ? player.expression.update(input, elapsed) : neutralDuetFace;
          expressionFrame = { elapsed, reset, input, face };
          target.dataset.expressionTick = String(++tick);
          return scene.setExpression(face);
        },
      };
    } catch (reason) {
      setError(describeError(reason));
      return;
    }
    runtime.current = player;
    // 観測を要求したときだけ、最後に描いた頂点と対応する時計を採取する。
    const read = (event: Event) => {
      const callback = (event as CustomEvent).detail;
      const frame = player.snapshot;
      if (frame && typeof callback === "function") {
        callback({ ...frame, body: track.body, artic: Array.from(frame.artic), geometry: player.scene.read() });
      }
    };
    const readMouth = (event: Event) => {
      const callback = (event as CustomEvent).detail;
      if (typeof callback === "function") callback(player.mouth.read());
    };
    const readEchoes = (event: Event) => {
      const callback = (event as CustomEvent).detail;
      if (player.snapshot && typeof callback === "function") {
        callback({ clock: player.snapshot.clock, ...player.scene.readEchoes() });
      }
    };
    const readExpression = (event: Event) => {
      const callback = (event as CustomEvent).detail;
      if (expressionFrame && player.snapshot && typeof callback === "function") {
        callback({ ...expressionFrame, clock: player.snapshot.clock, index: player.snapshot.index,
          expressive: player.expressive, tick, seed, state: player.expression.read(), mesh: player.scene.readExpression() });
      }
    };
    const readPressure = (event: Event) => {
      const callback = (event as CustomEvent).detail;
      if (player.snapshot && typeof callback === "function") callback({ clock: player.snapshot.clock,
        index: player.snapshot.index, sample: player.snapshot.sample, ...player.scene.readPressure() });
    };
    const readAirflow = (event: Event) => {
      const callback = (event as CustomEvent).detail;
      if (player.snapshot && typeof callback === "function") callback({ clock: player.snapshot.clock,
        index: player.snapshot.index, sample: player.snapshot.sample, ...player.scene.readAirflow() });
    };
    const readTurbulence = (event: Event) => {
      const callback = (event as CustomEvent).detail;
      if (player.snapshot && typeof callback === "function") callback({ clock: player.snapshot.clock,
        index: player.snapshot.index, sample: player.snapshot.sample, ...player.scene.readTurbulence() });
    };
    let idleFrame = 0;
    const animateIdle = () => {
      if (player.snapshot && !player.snapshot.clock.playing && player.expressive && player.express(null, false)) {
        player.scene.redraw();
        player.mouth.resize();
      }
      idleFrame = requestAnimationFrame(animateIdle);
    };
    idleFrame = requestAnimationFrame(animateIdle);
    target.addEventListener("chimera:read-duet-head", read);
    target.addEventListener("chimera:read-duet-echoes", readEchoes);
    target.addEventListener("chimera:read-duet-expression", readExpression);
    target.addEventListener("chimera:read-duet-pressure", readPressure);
    target.addEventListener("chimera:read-duet-airflow", readAirflow);
    target.addEventListener("chimera:read-duet-turbulence", readTurbulence);
    overlay.addEventListener("chimera:read-duet-mouth", readMouth);
    return () => {
      target.removeEventListener("chimera:read-duet-head", read);
      target.removeEventListener("chimera:read-duet-echoes", readEchoes);
      target.removeEventListener("chimera:read-duet-expression", readExpression);
      target.removeEventListener("chimera:read-duet-pressure", readPressure);
      target.removeEventListener("chimera:read-duet-airflow", readAirflow);
      target.removeEventListener("chimera:read-duet-turbulence", readTurbulence);
      overlay.removeEventListener("chimera:read-duet-mouth", readMouth);
      cancelAnimationFrame(idleFrame);
      player.mouth.dispose();
      player.scene.dispose();
      runtime.current = undefined;
      delete target.dataset.headEpoch;
    };
  }, [module, track, facing, seed]);

  useLayoutEffect(() => {
    const player = runtime.current;
    const target = canvas.current;
    if (!player || !target) return;
    const { index, sample, artic, word } = observation;
    const prior = player.snapshot;
    try {
      const reset = prior?.clock.epoch !== clock.epoch || clock.time < prior.clock.time;
      if (prior?.index !== index || reset) {
        player.scene.update(player.geometry(artic));
      }
      const reseed = reset || player.expressive !== expressive;
      player.expressive = expressive;
      player.express(clock.playing && expressive ? {
        pressure: duetMouthPressure(observation.pressureRms, track.nPh, track.nOr),
        f0: observation.f0, gate: observation.gate, voicing: observation.voicing,
        outRms: observation.outRms, beatStep: observation.beatStep,
      } : null, reseed);
      player.scene.setPressure(pressureVisible, pressureVisible && clock.playing ? {
        phLen: observation.phLen, orLen: observation.orLen, nPh: track.nPh, nOr: track.nOr, pressureRms: observation.pressureRms,
      } : null);
      player.scene.setAirflow(airflowVisible, clock.playing ? {
        phLen: observation.phLen, orLen: observation.orLen, nPh: track.nPh, nOr: track.nOr,
        phAreas: observation.phAreas, orAreas: observation.orAreas, flow: observation.flow,
      } : null, prior?.clock === clock ? undefined : clock.motionStep, reset);
      player.scene.setTurbulence(observation.noiseBranches, clock.playing && turbulenceVisible ? {
        phLen: observation.phLen, orLen: observation.orLen, noiseLevel: observation.noiseLevel, noiseNode: observation.noiseNode,
      } : null, prior?.clock !== clock);
      player.scene.draw(clock.motionTime, clock.playing, reset, { epoch: clock.epoch, index, sample });
      player.mouth.update(word, clock);
    } catch (reason) {
      setError(describeError(reason));
      return;
    }
    player.snapshot = { clock, index, sample, artic };
    target.dataset.headIndex = String(index);
    target.dataset.headEpoch = String(clock.epoch);
  }, [clock, observation, expressive, pressureVisible, airflowVisible, turbulenceVisible, track]);

  return <figure>
    <figcaption>{name}</figcaption>
    <canvas ref={canvas} aria-label={`${name}の三次元調音姿勢`} role="img" hidden={!!error} />
    <div className="duet-mouth-words" ref={layer} aria-hidden="true" hidden={!!error} />
    {error && <p role="status">頭部を描画できません。{error}</p>}
  </figure>;
}
