import { evaluationStartedAtEpochMs } from "./fixed-processor-evaluation-clock";
import { FixedProcessor } from "./fixed-processor";
import { PROCESSOR_NAME, type ProcessorOptions } from "./fixed-worklet-types";

class MeasuredFixedProcessor extends FixedProcessor {
  constructor(options: { processorOptions: ProcessorOptions }) {
    super(options, { evaluationStartedAtEpochMs, registrationStartedAtEpochMs, registeredAtEpochMs });
  }
}

declare function registerProcessor(name: string, ctor: typeof MeasuredFixedProcessor): void;

const registrationStartedAtEpochMs = Date.now();
registerProcessor(PROCESSOR_NAME, MeasuredFixedProcessor);
const registeredAtEpochMs = Date.now();
