from __future__ import annotations

from typing import Any

import numpy as np


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

    for index, source_value in enumerate(source):
        state = step_dwm(state=state, mesh=mesh, source_value=float(source_value), config=config)
        pressure = state["pressure"]
        output[index] = float(np.mean(pressure[probe_mask]))

    return {
        "output": output,
        "final_state": state,
        "meta": {
            "num_samples": int(source.size),
            "probe": probe,
            "active_cells": int(np.count_nonzero(mesh["active"])),
        },
    }
