from __future__ import annotations

from typing import Any

import numpy as np


def compute_internal_timestep(config: dict) -> tuple[float, int]:
    """Compute a stable internal timestep and substep count for the mesh."""

    dx = float(config["grid_step_m"])
    c = float(config["sound_speed"])
    audio_fs = int(config["sample_rate"])
    courant = float(config.get("courant_factor", 0.95))
    if dx <= 0 or c <= 0 or audio_fs <= 0:
        raise ValueError("grid_step_m, sound_speed, and sample_rate must be positive.")

    # 2D rectilinear DWM stability target; keep a small safety margin.
    max_dt = dx / (np.sqrt(2.0) * c)
    internal_dt = courant * max_dt
    audio_dt = 1.0 / audio_fs
    substeps = max(1, int(np.ceil(audio_dt / internal_dt)))
    return internal_dt, substeps


def initialize_state(mesh: dict) -> dict[str, np.ndarray]:
    shape = mesh["active"].shape
    zeros = np.zeros(shape, dtype=np.float64)
    return {
        "in_n": zeros.copy(),
        "in_s": zeros.copy(),
        "in_e": zeros.copy(),
        "in_w": zeros.copy(),
        "pressure": zeros.copy(),
    }


def _scatter_step(state: dict, mesh: dict, source_value: float, config: dict) -> dict[str, np.ndarray]:
    active = mesh["active"]
    glottal = mesh["glottal_mask"]
    lip = mesh["lip_mask"]

    incoming_n = state["in_n"].copy()
    incoming_s = state["in_s"].copy()
    incoming_e = state["in_e"].copy()
    incoming_w = state["in_w"].copy()

    if np.any(glottal):
        incoming_w[glottal] += float(source_value)

    junction_sum = incoming_n + incoming_s + incoming_e + incoming_w
    pressure = 0.5 * junction_sum

    out_n = pressure - incoming_n
    out_s = pressure - incoming_s
    out_e = pressure - incoming_e
    out_w = pressure - incoming_w

    loss = float(config["loss"])
    wall_reflect = float(config["wall_reflection"])
    open_reflect = float(config["open_reflection"])
    source_reflect = float(config["source_reflection"])

    next_in_n = np.zeros_like(pressure)
    next_in_s = np.zeros_like(pressure)
    next_in_e = np.zeros_like(pressure)
    next_in_w = np.zeros_like(pressure)

    north_active = mesh["north_active"]
    south_active = mesh["south_active"]
    east_active = mesh["east_active"]
    west_active = mesh["west_active"]

    next_in_s[:-1, :] += loss * out_n[1:, :] * north_active[1:, :]
    next_in_n[1:, :] += loss * out_s[:-1, :] * south_active[:-1, :]
    next_in_w[:, 1:] += loss * out_e[:, :-1] * east_active[:, :-1]
    next_in_e[:, :-1] += loss * out_w[:, 1:] * west_active[:, 1:]

    boundary_north = mesh["boundary_north"]
    boundary_south = mesh["boundary_south"]
    boundary_east = mesh["boundary_east"]
    boundary_west = mesh["boundary_west"]

    next_in_n += loss * out_n * boundary_north * wall_reflect
    next_in_s += loss * out_s * boundary_south * wall_reflect
    next_in_e += loss * out_e * boundary_east * wall_reflect
    next_in_w += loss * out_w * boundary_west * wall_reflect

    lip_reflection_mask = lip & boundary_east
    next_in_e[lip_reflection_mask] = loss * out_e[lip_reflection_mask] * open_reflect

    glottal_reflection_mask = glottal & boundary_west
    next_in_w[glottal_reflection_mask] = loss * out_w[glottal_reflection_mask] * source_reflect

    next_in_n[~active] = 0.0
    next_in_s[~active] = 0.0
    next_in_e[~active] = 0.0
    next_in_w[~active] = 0.0
    pressure[~active] = 0.0

    return {
        "in_n": next_in_n,
        "in_s": next_in_s,
        "in_e": next_in_e,
        "in_w": next_in_w,
        "pressure": pressure,
    }


def step_dwm(state: dict, mesh: dict, source_value: float, config: dict) -> dict[str, np.ndarray]:
    return _scatter_step(state=state, mesh=mesh, source_value=source_value, config=config)


def _sample_probe_signals(state: dict, probe_mask: np.ndarray) -> tuple[float, float]:
    pressure = state["pressure"]
    out_e = pressure - state["in_e"]
    in_e = state["in_e"]
    lip_flux = out_e[probe_mask] - in_e[probe_mask]
    return float(np.mean(pressure[probe_mask])), float(np.mean(lip_flux))


def _sample_probe(state: dict, probe_mask: np.ndarray, output_mode: str) -> float:
    pressure_mean, lip_flow_mean = _sample_probe_signals(state=state, probe_mask=probe_mask)

    if output_mode == "pressure":
        return pressure_mean

    if output_mode == "flow":
        return lip_flow_mean

    if output_mode == "radiated":
        return lip_flow_mean

    raise ValueError(f"Unsupported output_mode: {output_mode}")


def run_dwm(mesh: dict, source: np.ndarray, config: dict, probe: str = "lip") -> dict[str, Any]:
    source = np.asarray(source, dtype=np.float64)
    if source.ndim != 1:
        raise ValueError("source must be a 1D array.")

    probe_mask_name = "lip_mask" if probe == "lip" else "glottal_mask"
    probe_mask = np.asarray(mesh[probe_mask_name], dtype=bool)
    if not np.any(probe_mask):
        raise ValueError(f"No probe cells found for probe='{probe}'.")

    state = initialize_state(mesh)
    output = np.zeros(source.size, dtype=np.float64)
    internal_dt, substeps = compute_internal_timestep(config)
    audio_dt = 1.0 / int(config["sample_rate"])
    output_mode = str(config.get("output_mode", "pressure"))
    radiation_cutoff_hz = float(config.get("radiation_cutoff_hz", 800.0))
    radiation_gain = float(config.get("radiation_gain", 1.0))

    # 1st-order high-pass on lip flow as a simple radiation proxy.
    rc = 1.0 / (2.0 * np.pi * max(radiation_cutoff_hz, 1e-6))
    radiation_alpha = rc / (rc + audio_dt)
    previous_flow_value = 0.0
    previous_radiated_value = 0.0

    for index, source_value in enumerate(source):
        accumulated_probe = 0.0
        source_per_substep = float(source_value) / substeps

        for _ in range(substeps):
            state = step_dwm(state=state, mesh=mesh, source_value=source_per_substep, config=config)
            accumulated_probe += _sample_probe(
                state=state,
                probe_mask=probe_mask,
                output_mode=output_mode,
            )

        probe_value = accumulated_probe / substeps
        if output_mode == "radiated":
            radiated_value = radiation_alpha * (
                previous_radiated_value + probe_value - previous_flow_value
            )
            output[index] = radiation_gain * radiated_value
            previous_flow_value = probe_value
            previous_radiated_value = radiated_value
        else:
            output[index] = probe_value

    return {
        "output": output,
        "final_state": state,
        "meta": {
            "num_samples": int(source.size),
            "probe": probe,
            "active_cells": int(np.count_nonzero(mesh["active"])),
            "internal_dt_sec": float(internal_dt),
            "internal_fs_hz": float(1.0 / internal_dt),
            "substeps_per_sample": int(substeps),
            "output_mode": output_mode,
            "radiation_cutoff_hz": radiation_cutoff_hz,
        },
    }
