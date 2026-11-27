import processorUrl from "./song-silent-lead-processor.ts?worker&url";
import { SONG_SILENT_LEAD_PROCESSOR, type SongSilentLeadObservation, type SongSilentLeadOptions } from "./fixed-worklet-types";

export async function registerSongSilentLead(context: AudioContext, mark?: (phase: string) => void) {
  mark?.("silent_lead_module_start");
  await context.audioWorklet.addModule(processorUrl);
  mark?.("silent_lead_module_ready");
}

export async function prepareSongSilentLead(context: AudioContext, quantum: number,
  options: SongSilentLeadOptions, signal: AbortSignal) {
  signal.throwIfAborted();
  const { quanta } = options;
  const source = context.createBufferSource();
  const silence = context.createBuffer(1, quantum, context.sampleRate);
  // Firefoxでは割り当てる前にチャンネルを作り、0のPCMを音声グラフへ渡す。
  silence.getChannelData(0).fill(0);
  source.buffer = silence;
  source.loop = true;
  const node = new AudioWorkletNode(context, SONG_SILENT_LEAD_PROCESSOR, {
    outputChannelCount: [1], processorOptions: options,
  });
  const close = () => {
    source.stop();
    source.disconnect();
    node.disconnect();
    node.port.close();
  };
  source.start();
  let timer: number | undefined;
  let abort: (() => void) | undefined;
  try {
    const observation = await new Promise<SongSilentLeadObservation>((resolve, reject) => {
      abort = () => reject(signal.reason);
      signal.addEventListener("abort", abort, { once: true });
      timer = window.setTimeout(() => reject(new Error(`先行する無音の${quanta}量子を受信できませんでした`)), 5000);
      node.onprocessorerror = () => reject(new Error("無音先行のAudioWorkletが停止しました"));
      node.port.onmessage = ({ data }: MessageEvent<SongSilentLeadObservation>) => {
        if (data.quantum !== quantum) reject(new Error(`無音先行の描画量子が ${data.quantum} フレームでした`));
        else if (data.frames.length !== quanta) reject(new Error("無音先行の量子数が設定と一致しません"));
        else resolve(data);
      };
      source.connect(node);
      node.connect(context.destination);
    });
    return { observation, close };
  } catch (error) {
    close();
    throw error;
  } finally {
    window.clearTimeout(timer);
    if (abort) signal.removeEventListener("abort", abort);
    node.onprocessorerror = null;
    node.port.onmessage = null;
  }
}
