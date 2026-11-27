// ライブ入力で同じブロックに確実に収めにくい境界を、固定した合成時計で確かめる。
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { makeManualReplayCase } from "../src/manual-replay";

const [casePath, voicePath, output] = process.argv.slice(2);
const { measurement: { boundary, control_interval_output_frames } } = JSON.parse(readFileSync(casePath, "utf8"));
const voice = JSON.parse(readFileSync(voicePath, "utf8"));
const clock = {
  startFrame: boundary.start_frame,
  stopFrame: boundary.stop_frame,
  outputFrames: boundary.output_frames,
  controlIntervalOutputFrames: control_interval_output_frames,
};
const actions = [
  [clock.startFrame, boundary.targets_at_start_cm],
  [clock.stopFrame, boundary.targets_at_stop_cm],
].map(([frame, [x, y, lip]]) => ({
  frame, targets: { tongue_body_x_cm: x, tongue_body_y_cm: y, lip_aperture_cm: lip },
}));
function save(name: string, value: unknown) {
  writeFileSync(join(output, name), JSON.stringify(value, null, 2) + "\n");
}
save("boundary-case.json", makeManualReplayCase(voice, clock, actions));
save("no-motion-case.json", makeManualReplayCase(voice, clock, []));
let unalignedError: string | null = null;
try {
  makeManualReplayCase(voice, { ...clock, stopFrame: boundary.unaligned_stop_frame }, actions);
} catch (error) {
  unalignedError = error instanceof Error ? error.message : String(error);
}
save("export-boundary-result.json", { unalignedError });
