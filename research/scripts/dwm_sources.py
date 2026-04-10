from __future__ import annotations

import numpy as np


def make_impulse(n_samples: int, index: int = 0, amplitude: float = 1.0) -> np.ndarray:
    if n_samples <= 0:
        raise ValueError("n_samples must be positive.")

    signal = np.zeros(n_samples, dtype=np.float64)
    if 0 <= index < n_samples:
        signal[index] = amplitude
    return signal


def make_pulse_train(
    n_samples: int,
    fs: int,
    f0: float,
    amplitude: float = 1.0,
) -> np.ndarray:
    if n_samples <= 0:
        raise ValueError("n_samples must be positive.")
    if fs <= 0 or f0 <= 0:
        raise ValueError("fs and f0 must be positive.")

    period = max(1, int(round(fs / f0)))
    signal = np.zeros(n_samples, dtype=np.float64)
    signal[::period] = amplitude
    return signal


def make_simple_glottal_source(
    n_samples: int,
    fs: int,
    f0: float,
    amplitude: float = 1.0,
) -> np.ndarray:
    """Generate a simple Rosenberg-like glottal derivative sequence."""

    if n_samples <= 0:
        raise ValueError("n_samples must be positive.")
    if fs <= 0 or f0 <= 0:
        raise ValueError("fs and f0 must be positive.")

    period = max(8, int(round(fs / f0)))
    open_len = max(2, int(period * 0.45))
    close_len = max(2, int(period * 0.18))
    rest_len = max(0, period - open_len - close_len)

    open_phase = 0.5 - 0.5 * np.cos(np.linspace(0.0, np.pi, open_len, endpoint=False))
    close_phase = np.cos(np.linspace(0.0, np.pi / 2.0, close_len, endpoint=False)) ** 2
    flow = np.concatenate([open_phase, close_phase[::-1], np.zeros(rest_len, dtype=np.float64)])
    flow = flow[:period]
    derivative = np.diff(np.concatenate([[0.0], flow]))
    derivative /= max(np.max(np.abs(derivative)), 1e-12)

    repetitions = int(np.ceil(n_samples / derivative.size))
    tiled = np.tile(derivative, repetitions)[:n_samples]
    return tiled * amplitude

