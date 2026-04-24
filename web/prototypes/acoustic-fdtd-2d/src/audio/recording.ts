export async function playRecording(samples: Float32Array, sampleRate: number): Promise<void> {
  if (samples.length === 0) {
    return;
  }

  const context = new AudioContext({ sampleRate });
  const buffer = context.createBuffer(1, samples.length, sampleRate);
  const channel = buffer.getChannelData(0);
  let peak = 0;

  for (const sample of samples) {
    peak = Math.max(peak, Math.abs(sample));
  }

  const gain = peak > 0 ? 0.75 / peak : 1;
  for (let i = 0; i < samples.length; i += 1) {
    channel[i] = Math.max(-1, Math.min(1, samples[i] * gain));
  }

  const source = context.createBufferSource();
  const outputGain = context.createGain();
  outputGain.gain.value = 0.35;
  source.buffer = buffer;
  source.connect(outputGain);
  outputGain.connect(context.destination);
  source.start();

  source.addEventListener("ended", () => {
    void context.close();
  });
}
