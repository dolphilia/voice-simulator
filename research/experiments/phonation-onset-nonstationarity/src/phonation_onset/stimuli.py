from __future__ import annotations

import math

import numpy as np

from .audio import integrity, normalize


def _fit_length(audio: np.ndarray, length: int) -> np.ndarray:
    if audio.size >= length:
        return audio[:length].copy()
    return np.pad(audio, (0, length - audio.size))


def _best_loop_segment(audio: np.ndarray, center: int, requested: int, sample_rate: int) -> tuple[np.ndarray, int]:
    edge = max(16, int(round(0.004 * sample_rate)))
    best_score, best = float("inf"), None
    start_base = max(0, min(audio.size - requested, center - requested // 2))
    search = max(1, int(round(0.012 * sample_rate)))
    for offset in range(-search, search + 1, max(1, search // 16)):
        start = max(0, min(audio.size - requested, start_base + offset))
        segment = audio[start : start + requested]
        if segment.size < max(requested, edge * 2):
            continue
        score = float(np.sqrt(np.mean((segment[:edge] - segment[-edge:]) ** 2)))
        if score < best_score:
            best_score, best = score, segment.copy()
    if best is None:
        raise ValueError("stable region is too short for requested loop")
    return best, int(best.size)


def loop_with_crossfade(segment: np.ndarray, output_length: int, crossfade: int) -> tuple[np.ndarray, list[int]]:
    if segment.size <= crossfade * 2:
        crossfade = max(1, segment.size // 4)
    output = segment.copy()
    seams: list[int] = []
    while output.size < output_length:
        overlap = min(crossfade, output.size, segment.size)
        seam = output.size - overlap
        fade = np.linspace(0.0, 1.0, overlap, endpoint=False)
        blended = output[-overlap:] * np.sqrt(1.0 - fade) + segment[:overlap] * np.sqrt(fade)
        output = np.concatenate([output[:-overlap], blended, segment[overlap:]])
        seams.append(seam)
    return output[:output_length], [item for item in seams if item < output_length]


def join_with_crossfade(left: np.ndarray, right: np.ndarray, crossfade: int) -> tuple[np.ndarray, int]:
    overlap = min(max(1, crossfade), left.size, right.size)
    fade = np.linspace(0.0, 1.0, overlap, endpoint=False)
    blended = left[-overlap:] * np.sqrt(1.0 - fade) + right[:overlap] * np.sqrt(fade)
    return np.concatenate([left[:-overlap], blended, right[overlap:]]), left.size - overlap


def seam_jump_ratio(audio: np.ndarray, seams: list[int], radius: int = 32) -> float:
    if not seams or audio.size < 3:
        return 0.0
    derivative = np.abs(np.diff(audio))
    baseline = float(np.quantile(derivative, 0.95))
    if baseline <= 1e-12:
        return 0.0
    jumps = []
    for seam in seams:
        lo, hi = max(0, seam - radius), min(derivative.size, seam + radius)
        if hi > lo:
            jumps.append(float(np.max(derivative[lo:hi]) / baseline))
    return max(jumps, default=0.0)


def apply_microvariation(audio: np.ndarray, pitch_control: np.ndarray, amplitude_control: np.ndarray, sample_rate: int) -> np.ndarray:
    """同じ周辺分布を保った対照を作れる、小振幅の時間ワープと振幅変動。"""
    count = audio.size
    if count == 0:
        return audio.copy()
    source_axis = np.arange(count, dtype=float)
    pitch = np.interp(np.linspace(0, max(0, pitch_control.size - 1), count), source_axis[: pitch_control.size], pitch_control) if pitch_control.size else np.zeros(count)
    amplitude = np.interp(np.linspace(0, max(0, amplitude_control.size - 1), count), source_axis[: amplitude_control.size], amplitude_control) if amplitude_control.size else np.zeros(count)
    pitch = np.clip(pitch, -2.5, 2.5)
    amplitude = np.clip(amplitude, -2.5, 2.5)
    # 最大約15 centの微細な速度変化。平均速度を1へ戻し、長さを変えない。
    speed = np.power(2.0, (6.0 * pitch) / 1200.0)
    speed /= max(float(np.mean(speed)), 1e-12)
    warped_axis = np.cumsum(speed) - speed[0]
    warped_axis *= (count - 1) / max(float(warped_axis[-1]), 1e-12)
    warped = np.interp(warped_axis, source_axis, audio)
    gain = np.power(10.0, (0.45 * amplitude) / 20.0)
    return warped * gain


def _standardize_control(values: np.ndarray, output_count: int) -> np.ndarray:
    finite = values[np.isfinite(values)]
    if finite.size < 3:
        return np.zeros(output_count)
    filled = np.interp(np.arange(values.size), np.flatnonzero(np.isfinite(values)), finite)
    centered = filled - np.median(filled)
    scale = float(np.median(np.abs(centered))) * 1.4826
    if scale <= 1e-9:
        scale = float(np.std(centered))
    normalized = centered / max(scale, 1e-9)
    return np.interp(np.linspace(0, values.size - 1, output_count), np.arange(values.size), normalized)


def render_a_stimuli(
    audio: np.ndarray,
    sample_rate: int,
    activity_onset_sec: float,
    stable_onset_sec: float,
    activity_end_sec: float,
    output_duration_sec: float,
    shortened_duration_sec: float,
    loop_lengths_ms: list[int],
    crossfade_ms: float,
    target_dbfs: float,
    f0_control: np.ndarray | None = None,
    rms_control: np.ndarray | None = None,
) -> list[dict[str, object]]:
    pre = int(round(0.03 * sample_rate))
    start = max(0, int(round(activity_onset_sec * sample_rate)) - pre)
    stable = max(start, int(round(stable_onset_sec * sample_rate)))
    end = min(audio.size, max(stable + 1, int(round(activity_end_sec * sample_rate))))
    source = audio[start:end]
    output_length = int(round(output_duration_sec * sample_rate))
    short_length = int(round(shortened_duration_sec * sample_rate))
    crossfade = int(round(crossfade_ms * sample_rate / 1000.0))
    results: list[dict[str, object]] = []

    def add(condition: str, value: np.ndarray, seams: list[int], metadata: dict[str, object] | None = None) -> None:
        rendered = normalize(_fit_length(value, min(output_length, max(value.size, short_length))), target_dbfs)
        results.append({
            "condition": condition, "audio": rendered, "seams": seams,
            "seam_jump_ratio": seam_jump_ratio(rendered, seams), "integrity": integrity(rendered, sample_rate),
            "metadata": metadata or {},
        })

    add("A0-original", _fit_length(source, output_length), [])
    onset_length = max(0, stable - start)
    stable_material = audio[stable:end]
    a1 = np.concatenate([source[:onset_length], stable_material[: max(0, short_length - onset_length)]])
    add("A1-onset-shortened", a1, [])
    add("A2-stable-only", stable_material, [])

    center = stable + max(0, (end - stable) // 2)
    onset = source[:onset_length]
    for milliseconds in loop_lengths_ms:
        requested = int(round(milliseconds * sample_rate / 1000.0))
        segment, actual = _best_loop_segment(audio[stable:end], max(0, center - stable), requested, sample_rate)
        looped, loop_seams = loop_with_crossfade(segment, max(1, output_length - onset.size + crossfade), crossfade)
        looped, join_seam = join_with_crossfade(onset, looped, crossfade)
        seams = [join_seam, *[join_seam + item for item in loop_seams]]
        condition = "A3-loop-long" if milliseconds == max(loop_lengths_ms) else f"A4-loop-short-{milliseconds}ms"
        add(condition, looped, seams, {"requested_loop_ms": milliseconds, "actual_loop_samples": actual, "onset_preserved": True})

        if milliseconds == 80:
            sustain_count = max(1, looped.size - onset.size)
            pitch = _standardize_control(np.asarray(f0_control if f0_control is not None else []), sustain_count)
            amplitude = _standardize_control(np.asarray(rms_control if rms_control is not None else []), sustain_count)
            correlation = float(np.corrcoef(pitch, amplitude)[0, 1]) if np.std(pitch) > 0 and np.std(amplitude) > 0 else 0.0
            varied = np.concatenate([looped[:onset.size], apply_microvariation(looped[onset.size:], pitch, amplitude, sample_rate)])
            add("A5-loop-correlated-variation", varied, seams, {
                "base_loop_ms": milliseconds, "onset_preserved": True,
                "control_source": "same-reference-stable-f0-rms", "relationship": "measured-time-alignment",
                "pitch_control_std": float(np.std(pitch)), "amplitude_control_std": float(np.std(amplitude)), "control_correlation": correlation,
            })
            # 同じ制御列と分散を保ち、振幅系列だけ半周ずらして時間関係を崩す。
            independent_amplitude = np.roll(amplitude, max(1, amplitude.size // 2))
            independent_correlation = float(np.corrcoef(pitch, independent_amplitude)[0, 1]) if np.std(pitch) > 0 and np.std(independent_amplitude) > 0 else 0.0
            varied_control = np.concatenate([looped[:onset.size], apply_microvariation(looped[onset.size:], pitch, independent_amplitude, sample_rate)])
            add("A6-loop-independent-variation", varied_control, seams, {
                "base_loop_ms": milliseconds, "onset_preserved": True,
                "control_source": "same-reference-stable-f0-rms", "relationship": "amplitude-control-half-rotation",
                "pitch_control_std": float(np.std(pitch)), "amplitude_control_std": float(np.std(independent_amplitude)), "control_correlation": independent_correlation,
            })
    return results
