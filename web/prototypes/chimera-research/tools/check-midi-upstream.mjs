import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { installMidi } from "./fake-midi.mjs";

const [upstream, fixture] = process.argv.slice(2);
const { measurement } = JSON.parse(readFileSync(fixture, "utf8"));
installMidi(measurement.ports);
const { connectMidi, disconnectMidi } = await import(pathToFileURL(upstream).href);
const held = new Set();
const callbacks = [];
let inputs = [];
await connectMidi({
  noteOn: (note) => { held.add(note); callbacks.push(["on", note]); },
  noteOff: (note) => { held.delete(note); callbacks.push(["off", note]); },
  inputs: (names) => { inputs = names; },
});
const notes = measurement.actions.map((action) => {
  globalThis.chimeraTestMidi.apply(action);
  return [...held].at(-1) ?? null;
});
disconnectMidi();
console.log(JSON.stringify({ notes, callbacks, inputs }));
