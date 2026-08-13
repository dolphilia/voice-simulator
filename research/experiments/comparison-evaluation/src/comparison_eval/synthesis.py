from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy import signal
from scipy.io import wavfile

from .fixtures import harmonic_source
from .fixtures import add_noise_at_snr
from .signal import read_audio


def parallel_formant_synth(formants: list[list[float]], duration_sec: float, sample_rate: int, f0_hz: float, brightness: float = 0.0, breathiness: float = 0.0, seed: int = 1) -> np.ndarray:
    source = harmonic_source(f0_hz, duration_sec, sample_rate, tilt_db_octave=-6.0)
    result = np.zeros_like(source)
    for index, (frequency, bandwidth, gain) in enumerate(formants):
        numerator, denominator = signal.iirpeak(frequency, max(0.1, frequency / bandwidth), fs=sample_rate)
        adjusted_gain = gain * (1.0 + brightness * index * 0.45) * max(0.55, 1.0 - breathiness * 0.2)
        result += signal.lfilter(numerator, denominator, source) * adjusted_gain
    if breathiness > 0.0:
        rng = np.random.default_rng(seed)
        sos = signal.butter(3, 3400, btype="highpass", fs=sample_rate, output="sos")
        result += signal.sosfilt(sos, rng.normal(size=result.size)) * breathiness * 0.025
    envelope = np.ones(result.size)
    fade = min(result.size // 2, int(0.02 * sample_rate))
    if fade:
        envelope[:fade] = np.linspace(0, 1, fade)
        envelope[-fade:] = np.linspace(1, 0, fade)
    result *= envelope
    return 0.75 * result / max(float(np.max(np.abs(result))), 1e-12)


def cv_synth(vowel: np.ndarray, consonant: dict[str, float], sample_rate: int, seed: int) -> np.ndarray:
    duration = float(consonant["duration_sec"])
    count = int(round(duration * sample_rate))
    rng = np.random.default_rng(seed)
    numerator, denominator = signal.iirpeak(float(consonant["center_hz"]), float(consonant["q"]), fs=sample_rate)
    noise = signal.lfilter(numerator, denominator, rng.normal(size=count))
    attack = max(1, int(float(consonant["attack_sec"]) * sample_rate))
    noise_envelope = np.linspace(0.0, 1.0, attack).tolist() + np.linspace(1.0, 0.0, max(1, count - attack)).tolist()
    noise = noise[:count] * np.asarray(noise_envelope[:count])
    noise *= 0.45 / max(float(np.max(np.abs(noise))), 1e-12)
    overlap = int(round(float(consonant["overlap_sec"]) * sample_rate))
    output = np.zeros(count + vowel.size - overlap)
    output[:count] += noise
    vowel_start = count - overlap
    output[vowel_start : vowel_start + vowel.size] += vowel
    return output * (0.75 / max(float(np.max(np.abs(output))), 1e-12))


def render_suite(config_path: Path, output: Path) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    sample_rate, f0_hz = int(config["sample_rate"]), float(config["f0_hz"])
    output.mkdir(parents=True, exist_ok=True)
    records = []
    vowels = {}
    for index, (label, formants) in enumerate(config["vowels"].items(), 1):
        audio = parallel_formant_synth(formants, 0.65, sample_rate, f0_hz, seed=index)
        vowels[label] = audio
        path = output / f"vowel-{label}.wav"
        wavfile.write(path, sample_rate, audio.astype(np.float32))
        records.append({"kind": "vowel-identification", "label": label, "path": str(path)})
    for index, (consonant_label, consonant) in enumerate(config["sibilants"].items(), 20):
        target_vowel = "い" if consonant_label == "し" else "う"
        audio = cv_synth(vowels[target_vowel], consonant, sample_rate, index)
        path = output / f"cv-{consonant_label}.wav"
        wavfile.write(path, sample_rate, audio.astype(np.float32))
        records.append({"kind": "cv-identification", "label": consonant_label, "path": str(path)})
    for name, brightness, breathiness in (("brightness-low", -0.7, 0.0), ("brightness-high", 0.7, 0.0), ("breathiness-low", 0.0, 0.0), ("breathiness-high", 0.0, 0.8)):
        audio = parallel_formant_synth(config["vowels"]["あ"], 0.65, sample_rate, f0_hz, brightness, breathiness, 100)
        path = output / f"{name}.wav"
        wavfile.write(path, sample_rate, audio.astype(np.float32))
        records.append({"kind": "attribute-order", "label": name, "path": str(path)})
    return {"schema_version": config["schema_version"], "records": records}


def render_calibration_anchors(reference_path: Path, output: Path, config_path: Path) -> list[dict[str, str]]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    sample_rate, reference = read_audio(reference_path)
    output.mkdir(parents=True, exist_ok=True)
    anchors: list[tuple[str, np.ndarray]] = [("human-clean", reference)]
    anchors.append(("human-noise-20db", add_noise_at_snr(reference, 20.0, seed=11)))
    anchors.append(("human-noise-5db", add_noise_at_snr(reference, 5.0, seed=12)))
    lowpass = signal.sosfilt(signal.butter(6, 1800, btype="lowpass", fs=sample_rate, output="sos"), reference)
    anchors.append(("human-lowpass", lowpass))
    shifted = signal.resample(reference, max(1, int(reference.size / 1.25)))
    shifted = np.pad(shifted, (0, max(0, reference.size - shifted.size)))[: reference.size]
    anchors.append(("human-pitch-formant-up", shifted))
    web = parallel_formant_synth(config["vowels"]["あ"], reference.size / sample_rate, sample_rate, float(config["f0_hz"]), seed=20)
    anchors.append(("web-parallel-formant", web))
    harmonic = harmonic_source(float(config["f0_hz"]), reference.size / sample_rate, sample_rate, tilt_db_octave=-6.0)
    anchors.append(("harmonic-source-only", harmonic))
    time = np.arange(reference.size) / sample_rate
    anchors.append(("sine-only", np.sin(2.0 * np.pi * float(config["f0_hz"]) * time) * 0.5))
    records = []
    for name, audio in anchors:
        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        normalized = audio * (0.8 / max(peak, 1e-12))
        path = output / f"{name}.wav"
        wavfile.write(path, sample_rate, normalized.astype(np.float32))
        records.append({"name": name, "path": str(path), "reference_path": str(reference_path)})
    return records
