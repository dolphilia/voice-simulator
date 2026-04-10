from __future__ import annotations

from typing import Any

import numpy as np
from matplotlib.path import Path


def _segment_to_mask(xs: np.ndarray, ys: np.ndarray, segment: np.ndarray, tol: float) -> np.ndarray:
    x0, y0 = segment[0]
    x1, y1 = segment[1]
    dx = x1 - x0
    dy = y1 - y0
    denom = dx * dx + dy * dy
    if denom == 0:
        distance = np.sqrt((xs - x0) ** 2 + (ys - y0) ** 2)
        return distance <= tol

    t = ((xs - x0) * dx + (ys - y0) * dy) / denom
    t = np.clip(t, 0.0, 1.0)
    proj_x = x0 + t * dx
    proj_y = y0 + t * dy
    distance = np.sqrt((xs - proj_x) ** 2 + (ys - proj_y) ** 2)
    return distance <= tol


def build_rect_mesh(shape: dict, dx: float) -> dict[str, Any]:
    """Rasterize a polygonal tract shape onto a rectangular grid."""

    polygon = np.asarray(shape["polygon"], dtype=np.float64)
    if polygon.ndim != 2 or polygon.shape[1] != 2:
        raise ValueError("shape['polygon'] must be a Nx2 array.")
    if dx <= 0:
        raise ValueError("dx must be positive.")

    min_x, min_y = np.min(polygon[:, 0]), np.min(polygon[:, 1])
    max_x, max_y = np.max(polygon[:, 0]), np.max(polygon[:, 1])
    margin = dx

    x_coords = np.arange(min_x - margin, max_x + margin + dx * 0.5, dx)
    y_coords = np.arange(min_y - margin, max_y + margin + dx * 0.5, dx)
    xs, ys = np.meshgrid(x_coords, y_coords, indexing="xy")

    path = Path(polygon)
    points = np.column_stack([xs.ravel(), ys.ravel()])
    active = path.contains_points(points, radius=dx * 0.25).reshape(xs.shape)

    north_active = np.roll(active, shift=-1, axis=0)
    south_active = np.roll(active, shift=1, axis=0)
    east_active = np.roll(active, shift=-1, axis=1)
    west_active = np.roll(active, shift=1, axis=1)

    north_active[-1, :] = False
    south_active[0, :] = False
    east_active[:, -1] = False
    west_active[:, 0] = False

    boundary_north = active & ~north_active
    boundary_south = active & ~south_active
    boundary_east = active & ~east_active
    boundary_west = active & ~west_active

    tol = dx * 0.75
    glottal_segment = np.asarray(shape["glottal_port"], dtype=np.float64)
    lip_segment = np.asarray(shape["lip_port"], dtype=np.float64)

    glottal_mask = active & boundary_west & _segment_to_mask(xs, ys, glottal_segment, tol)
    lip_mask = active & boundary_east & _segment_to_mask(xs, ys, lip_segment, tol)

    if not np.any(glottal_mask):
        glottal_mask = active & boundary_west
    if not np.any(lip_mask):
        lip_mask = active & boundary_east

    if not np.any(glottal_mask):
        raise ValueError("Failed to identify a glottal port on the rasterized mesh.")
    if not np.any(lip_mask):
        raise ValueError("Failed to identify a lip port on the rasterized mesh.")

    return {
        "shape": shape,
        "dx": float(dx),
        "x_coords": x_coords,
        "y_coords": y_coords,
        "xs": xs,
        "ys": ys,
        "active": active,
        "north_active": north_active,
        "south_active": south_active,
        "east_active": east_active,
        "west_active": west_active,
        "boundary_north": boundary_north,
        "boundary_south": boundary_south,
        "boundary_east": boundary_east,
        "boundary_west": boundary_west,
        "glottal_mask": glottal_mask,
        "lip_mask": lip_mask,
    }


def get_probe_index(mesh: dict, which: str = "lip") -> tuple[int, int]:
    mask_name = "lip_mask" if which == "lip" else "glottal_mask"
    mask = np.asarray(mesh[mask_name], dtype=bool)
    indices = np.argwhere(mask)
    if indices.size == 0:
        raise ValueError(f"No probe cells found for {which}.")

    center = indices.mean(axis=0)
    order = np.argsort(np.sum((indices - center) ** 2, axis=1))
    iy, ix = indices[order[0]]
    return int(iy), int(ix)


def summarize_mesh(mesh: dict) -> dict[str, Any]:
    active = np.asarray(mesh["active"], dtype=bool)
    glottal = np.asarray(mesh["glottal_mask"], dtype=bool)
    lip = np.asarray(mesh["lip_mask"], dtype=bool)

    return {
        "grid_shape": tuple(int(v) for v in active.shape),
        "active_cells": int(np.count_nonzero(active)),
        "glottal_cells": int(np.count_nonzero(glottal)),
        "lip_cells": int(np.count_nonzero(lip)),
        "dx": float(mesh["dx"]),
        "label": mesh["shape"].get("label", "unknown"),
    }
