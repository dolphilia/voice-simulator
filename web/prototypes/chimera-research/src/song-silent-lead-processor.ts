import { SONG_SILENT_LEAD_PROCESSOR, type SongSilentLeadObservation, type SongSilentLeadOptions,
  type SongSilentLeadQuanta } from "./fixed-worklet-types";

declare const currentFrame: number;
declare class AudioWorkletProcessor {
  readonly port: MessagePort;
}
declare function registerProcessor(name: string, ctor: typeof SongSilentLeadProcessor): void;

const traceColumns = ["context_frame", "output_frames", "input_channels", "input_frames", "has_nonzero_input"];
const traceCapacity = 128;

class SongSilentLeadProcessor extends AudioWorkletProcessor {
  private frames: number[] = [];
  private firstValidInputFrame?: number;
  private validInputQuanta = 0;
  private ready = false;
  private readonly quanta: SongSilentLeadQuanta;
  private readonly inputTrace?: number[];
  private readonly traceNative: boolean;
  private tracedCallbacks = 0;

  constructor({ processorOptions }: { processorOptions: SongSilentLeadOptions }) {
    super();
    this.quanta = processorOptions.quanta;
    this.traceNative = processorOptions.traceNative === true;
    if (processorOptions.traceInput) this.inputTrace = new Array<number>(traceCapacity * traceColumns.length);
  }

  process(inputs: Float32Array[][], outputs: Float32Array[][]): boolean {
    if (this.ready) return true;
    if (this.traceNative) console.timeStamp(`chimera-lead-frame:${currentFrame}`);
    const quantum = outputs[0]?.[0]?.length ?? 0;
    const channels = inputs[0];
    const input = channels?.[0];
    const matchingInput = quantum > 0 && input?.length === quantum;
    const hasNonzeroInput = (matchingInput || this.inputTrace !== undefined) && input !== undefined
      && input.some((sample) => sample !== 0);
    if (this.inputTrace) {
      const offset = this.tracedCallbacks * traceColumns.length;
      this.tracedCallbacks++;
      if (offset < this.inputTrace.length) {
        this.inputTrace[offset] = currentFrame;
        this.inputTrace[offset + 1] = quantum;
        this.inputTrace[offset + 2] = channels?.length ?? 0;
        this.inputTrace[offset + 3] = input?.length ?? 0;
        this.inputTrace[offset + 4] = Number(hasNonzeroInput);
      }
    }
    if (!matchingInput || hasNonzeroInput) {
      this.frames.length = 0;
      return true;
    }
    const previous = this.frames.at(-1);
    if (previous !== undefined && currentFrame !== previous + quantum) this.frames.length = 0;
    this.firstValidInputFrame ??= currentFrame;
    this.validInputQuanta++;
    this.frames.push(currentFrame);
    if (this.frames.length === this.quanta) {
      const observation: SongSilentLeadObservation = {
        quantum, frames: this.frames, firstValidInputFrame: this.firstValidInputFrame,
        validInputQuanta: this.validInputQuanta, readyContextFrame: currentFrame + quantum,
      };
      if (this.inputTrace) {
        observation.inputTrace = {
          columns: traceColumns,
          values: this.inputTrace.slice(0, this.tracedCallbacks * traceColumns.length),
          omittedCallbacks: Math.max(0, this.tracedCallbacks - traceCapacity),
        };
      }
      this.port.postMessage(observation);
      this.ready = true;
    }
    return true;
  }
}

registerProcessor(SONG_SILENT_LEAD_PROCESSOR, SongSilentLeadProcessor);
