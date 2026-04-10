from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy import signal
from scipy.io import wavfile


def compute_spectrum(audio: np.ndarray, fs: int) -> tuple[np.ndarray, np.ndarray]:
    audio = np.asarray(audio, dtype=np.float64)
    if audio.ndim != 1:
        raise ValueError("audio must be a 1D array.")
    if fs <= 0:
        raise ValueError("fs must be positive.")

    fft_size = min(audio.size, 16_384)
    if fft_size < 8:
        raise ValueError("audio is too short to compute a spectrum.")

    window = np.hanning(fft_size)
    spectrum = np.fft.rfft(audio[:fft_size] * window)
    frequencies = np.fft.rfftfreq(fft_size, d=1.0 / fs)
    magnitude_db = 20.0 * np.log10(np.maximum(np.abs(spectrum), 1e-12))
    return frequencies, magnitude_db


def compute_spectrogram(audio: np.ndarray, fs: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    audio = np.asarray(audio, dtype=np.float64)
    if audio.ndim != 1:
        raise ValueError("audio must be a 1D array.")
    if fs <= 0:
        raise ValueError("fs must be positive.")

    frequencies, times, spectrogram = signal.spectrogram(
        audio,
        fs=fs,
        window="hann",
        nperseg=min(1024, audio.size),
        noverlap=min(768, max(0, audio.size // 2)),
        scaling="spectrum",
        mode="magnitude",
    )
    spectrogram_db = 20.0 * np.log10(np.maximum(spectrogram, 1e-12))
    return frequencies, times, spectrogram_db


def find_major_peaks(audio: np.ndarray, fs: int, n_peaks: int = 5) -> np.ndarray:
    frequencies, magnitude_db = compute_spectrum(audio, fs)
    peaks, _ = signal.find_peaks(magnitude_db, prominence=3.0)
    if peaks.size == 0:
        return np.array([], dtype=np.float64)

    ranked = peaks[np.argsort(magnitude_db[peaks])[::-1]]
    selected = np.sort(ranked[:n_peaks])
    return frequencies[selected]


def save_wav(path, audio: np.ndarray, fs: int) -> None:
    audio = np.asarray(audio, dtype=np.float64)
    if audio.ndim != 1:
        raise ValueError("audio must be a 1D array.")
    if fs <= 0:
        raise ValueError("fs must be positive.")

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    peak = np.max(np.abs(audio))
    normalized = audio if peak <= 0 else audio / peak
    wavfile.write(output_path, fs, normalized.astype(np.float32))

