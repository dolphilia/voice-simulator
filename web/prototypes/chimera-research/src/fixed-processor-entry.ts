import { FixedProcessor } from "./fixed-processor";
import { PROCESSOR_NAME } from "./fixed-worklet-types";

declare function registerProcessor(name: string, ctor: typeof FixedProcessor): void;

registerProcessor(PROCESSOR_NAME, FixedProcessor);
