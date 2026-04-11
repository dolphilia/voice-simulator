from __future__ import annotations

DEFAULT_SAMPLE_RATE = 44_100
DEFAULT_DURATION_SEC = 0.12
DEFAULT_SOUND_SPEED = 343.0
DEFAULT_GRID_STEP_M = 0.004
DEFAULT_F0 = 120.0
DEFAULT_LOSS = 0.999
DEFAULT_WALL_REFLECTION = 0.995
DEFAULT_OPEN_REFLECTION = -0.92
DEFAULT_SOURCE_REFLECTION = 0.85
DEFAULT_LIP_PROBE = "lip"
DEFAULT_COURANT_FACTOR = 0.95
DEFAULT_OUTPUT_MODE = "radiated"
DEFAULT_RADIATION_CUTOFF_HZ = 1200.0
DEFAULT_RADIATION_GAIN = 1.0


def make_default_config() -> dict:
    """Return a mutable default config dictionary for DWM experiments."""

    return {
        "sample_rate": DEFAULT_SAMPLE_RATE,
        "duration_sec": DEFAULT_DURATION_SEC,
        "sound_speed": DEFAULT_SOUND_SPEED,
        "grid_step_m": DEFAULT_GRID_STEP_M,
        "f0": DEFAULT_F0,
        "loss": DEFAULT_LOSS,
        "wall_reflection": DEFAULT_WALL_REFLECTION,
        "open_reflection": DEFAULT_OPEN_REFLECTION,
        "source_reflection": DEFAULT_SOURCE_REFLECTION,
        "lip_probe": DEFAULT_LIP_PROBE,
        "courant_factor": DEFAULT_COURANT_FACTOR,
        "output_mode": DEFAULT_OUTPUT_MODE,
        "radiation_cutoff_hz": DEFAULT_RADIATION_CUTOFF_HZ,
        "radiation_gain": DEFAULT_RADIATION_GAIN,
    }
