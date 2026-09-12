from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy import signal


def _fade_edges(audio: np.ndarray, count: int) -> np.ndarray:
    output = audio.copy()
    count = min(max(0, count), output.size // 2)
    if count:
        fade = np.sin(np.linspace(0.0, np.pi / 2.0, count)) ** 2
        output[:count] *= fade
        output[-count:] *= fade[::-1]
    return output


def _normalize(audio: np.ndarray, target_dbfs: float, peak_limit_dbfs: float = -1.0) -> np.ndarray:
    rms = float(np.sqrt(np.mean(audio * audio)))
    if rms <= 1e-12:
        return audio.copy()
    output = audio * (10.0 ** (target_dbfs / 20.0) / rms)
    peak = float(np.max(np.abs(output)))
    limit = 10.0 ** (peak_limit_dbfs / 20.0)
    return output * min(1.0, limit / max(peak, 1e-12))


def saw_source(sample_rate: int, count: int, f0_hz: float) -> np.ndarray:
    time = np.arange(count, dtype=float) / sample_rate
    return signal.sawtooth(2.0 * np.pi * f0_hz * time, width=0.0)


def lf_family_source(sample_rate: int, count: int, f0_hz: float, parameters: dict[str, float]) -> np.ndarray:
    """周期的なLF形状の声門流微分近似。式と形状値をmanifestへ固定する。"""
    phase = np.mod(np.arange(count, dtype=float) * f0_hz / sample_rate, 1.0)
    peak = float(parameters["peak_phase"])
    closure = float(parameters["closure_phase"])
    return_time = float(parameters["return_time_phase"])
    growth = float(parameters["growth"])
    if not 0.0 < peak < closure < 1.0 or return_time <= 0.0:
        raise ValueError("invalid LF-family shape")
    output = np.zeros(count, dtype=float)
    opening = phase <= closure
    opening_phase = phase[opening]
    omega = math.pi / peak
    raw = np.exp(growth * opening_phase) * np.sin(omega * opening_phase)
    scale = max(abs(float(np.min(raw))), abs(float(np.max(raw))), 1e-12)
    output[opening] = raw / scale
    tail_phase = phase[~opening] - closure
    if tail_phase.size:
        tail = -np.exp(-tail_phase / return_time)
        tail_end = -math.exp(-(1.0 - closure) / return_time)
        output[~opening] = tail - tail_end
    output -= float(np.mean(output))
    return output / max(float(np.max(np.abs(output))), 1e-12)


def parallel_formants(
    source: np.ndarray,
    sample_rate: int,
    formants_hz: list[float],
    bandwidths_hz: list[float],
    gains: list[float],
) -> np.ndarray:
    output = np.zeros_like(source)
    for formant, bandwidth, gain in zip(formants_hz, bandwidths_hz, gains, strict=True):
        b, a = signal.iirpeak(formant, max(formant / bandwidth, 1.0), fs=sample_rate)
        output += float(gain) * signal.lfilter(b, a, source)
    return output


def cascade_all_pole(
    source: np.ndarray,
    sample_rate: int,
    formants_hz: list[float],
    bandwidths_hz: list[float],
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    output = source.copy()
    sections: list[dict[str, Any]] = []
    for formant, bandwidth in zip(formants_hz, bandwidths_hz, strict=True):
        radius = math.exp(-math.pi * bandwidth / sample_rate)
        angle = 2.0 * math.pi * formant / sample_rate
        denominator = np.asarray([1.0, -2.0 * radius * math.cos(angle), radius * radius])
        numerator = np.asarray([1.0 - radius])
        output = signal.lfilter(numerator, denominator, output)
        sections.append({
            "formant_hz": formant,
            "bandwidth_hz": bandwidth,
            "pole_radius": radius,
            "denominator": denominator.tolist(),
            "numerator": numerator.tolist(),
        })
    return output, sections


def two_mass_source(sample_rate: int, count: int, spec: dict[str, float]) -> tuple[np.ndarray, dict[str, float]]:
    """対称2質量・準定常Bernoulli駆動の実装可能性モデル。完全なIF72声道結合ではない。"""
    oversampling = int(spec["internal_oversampling"])
    internal_rate = sample_rate * oversampling
    warmup = int(round(float(spec["warmup_sec"]) * internal_rate))
    total = warmup + count * oversampling
    dt = 1.0 / internal_rate
    m1, m2 = float(spec["mass_1_kg"]), float(spec["mass_2_kg"])
    k1, k2, kc = (float(spec[key]) for key in ("stiffness_1_n_m", "stiffness_2_n_m", "coupling_stiffness_n_m"))
    r1 = 2.0 * float(spec["damping_ratio_1"]) * math.sqrt(m1 * k1)
    r2 = 2.0 * float(spec["damping_ratio_2"]) * math.sqrt(m2 * k2)
    fold_length = float(spec["fold_length_m"])
    thickness = float(spec["lower_thickness_m"])
    rest_area = float(spec["rest_area_m2"])
    pressure = float(spec["subglottal_pressure_pa"])
    density = float(spec["air_density_kg_m3"])
    collision_multiplier = float(spec["collision_stiffness_multiplier"])
    state = np.asarray([1e-6, 0.0, -1e-6, 0.0], dtype=float)
    flow = np.zeros(total, dtype=float)
    minimum_gap = rest_area / (2.0 * fold_length)

    def derivative(value: np.ndarray) -> tuple[np.ndarray, float, bool]:
        x1, v1, x2, v2 = value
        raw_area1 = rest_area + 2.0 * fold_length * x1
        raw_area2 = rest_area + 2.0 * fold_length * x2
        area1, area2 = max(1e-12, raw_area1), max(1e-12, raw_area2)
        minimum_area = max(0.0, min(raw_area1, raw_area2))
        volume_flow = minimum_area * math.sqrt(2.0 * pressure / density) if minimum_area > 0.0 else 0.0
        lower_pressure = pressure * (1.0 - (minimum_area / area1) ** 2) if minimum_area > 0.0 else 0.0
        contact1 = -collision_multiplier * k1 * min(0.0, x1 + minimum_gap)
        contact2 = -collision_multiplier * k2 * min(0.0, x2 + minimum_gap)
        acceleration1 = (lower_pressure * fold_length * thickness - r1 * v1 - k1 * x1 - kc * (x1 - x2) + contact1) / m1
        acceleration2 = (-r2 * v2 - k2 * x2 - kc * (x2 - x1) + contact2) / m2
        return np.asarray([v1, acceleration1, v2, acceleration2]), volume_flow, minimum_area <= 0.0

    closed = 0
    maximum_displacement = 0.0
    for index in range(total):
        k_1, volume_flow, is_closed = derivative(state)
        k_2, _, _ = derivative(state + 0.5 * dt * k_1)
        k_3, _, _ = derivative(state + 0.5 * dt * k_2)
        k_4, _, _ = derivative(state + dt * k_3)
        state += dt * (k_1 + 2.0 * k_2 + 2.0 * k_3 + k_4) / 6.0
        if not np.all(np.isfinite(state)):
            raise RuntimeError("two-mass solver diverged")
        maximum_displacement = max(maximum_displacement, abs(float(state[0])), abs(float(state[2])))
        if maximum_displacement > 0.005:
            raise RuntimeError("two-mass displacement exceeded safety bound")
        flow[index] = volume_flow
        closed += int(is_closed and index >= warmup)
    rendered_flow = signal.resample_poly(flow[warmup:], 1, oversampling)[:count]
    source = np.gradient(rendered_flow)
    source -= float(np.mean(source))
    peaks, _ = signal.find_peaks(rendered_flow, distance=max(1, int(sample_rate / 500.0)), prominence=max(float(np.std(rendered_flow)), 1e-12))
    f0 = sample_rate / float(np.mean(np.diff(peaks))) if peaks.size >= 3 else 0.0
    return source / max(float(np.max(np.abs(source))), 1e-12), {
        "measured_f0_hz": f0,
        "closed_ratio": closed / max(1, count * oversampling),
        "maximum_displacement_m": maximum_displacement,
        "internal_sample_rate": float(internal_rate),
    }


def render_two_mass_candidate(spec: dict[str, Any]) -> dict[str, Any]:
    sample_rate = int(spec["sample_rate"])
    count = int(round(float(spec["duration_sec"]) * sample_rate))
    source, diagnostics = two_mass_source(sample_rate, count, spec["two_mass"])
    audio, sections = cascade_all_pole(source, sample_rate, spec["formants_hz"], spec["bandwidths_hz"])
    audio = _fade_edges(audio, int(round(float(spec["edge_fade_ms"]) * sample_rate / 1000.0)))
    audio = _normalize(audio, float(spec["target_dbfs"]))
    return {
        "condition": "B4-two-mass-cascade",
        "audio": audio,
        "source": "symmetric-two-mass-bernoulli",
        "filter": "cascade",
        "filter_sections": sections,
        "diagnostics": diagnostics,
        "contains_human_audio": False,
    }


def render_waveguide_candidate(spec: dict[str, Any], waveguide: dict[str, Any]) -> dict[str, Any]:
    """既存Webプロトタイプと同じKelly–Lochbaum散乱をオフライン生成する。"""
    sample_rate = int(spec["sample_rate"])
    count = int(round(float(spec["duration_sec"]) * sample_rate))
    oversampling = int(waveguide["internal_oversampling"])
    internal_rate = sample_rate * oversampling
    sections = int(waveguide["num_sections"])
    controls = np.asarray(waveguide["areas_cm2"], dtype=float)
    areas = np.interp(np.linspace(0.0, controls.size - 1, sections), np.arange(controls.size), controls)
    minimum_area = float(waveguide["minimum_area_cm2"])
    reflection = np.zeros(sections)
    for index in range(sections - 1):
        left_area = max(minimum_area, float(areas[index]))
        right_area = max(minimum_area, float(areas[index + 1]))
        reflection[index] = (right_area - left_area) / (right_area + left_area)
    reflection[-1] = float(waveguide["mouth_reflection"])
    loss = np.exp(-float(waveguide["loss_alpha"]) / np.sqrt(np.maximum(minimum_area, areas)))
    right_previous = np.zeros(sections)
    left_previous = np.zeros(sections)
    right = np.zeros(sections)
    left = np.zeros(sections)
    warmup = int(round(float(waveguide["warmup_sec"]) * internal_rate))
    total = warmup + count * oversampling
    source = saw_source(internal_rate, total, float(spec["f0_hz"]))
    output = np.zeros(total)
    for sample_index in range(total):
        right[0] = source[sample_index] + float(waveguide["glottal_reflection"]) * left_previous[0]
        for section in range(sections - 1):
            coefficient = reflection[section]
            section_loss = loss[section]
            right[section + 1] = ((1.0 + coefficient) * right_previous[section] - coefficient * left_previous[section + 1]) * section_loss
            left[section] = ((1.0 - coefficient) * left_previous[section + 1] + coefficient * right_previous[section]) * section_loss
        left[-1] = reflection[-1] * right_previous[-1] * loss[-1]
        output[sample_index] = right_previous[-1] + left_previous[-1]
        right, right_previous = right_previous, right
        left, left_previous = left_previous, left
    rendered = signal.resample_poly(output[warmup:], 1, oversampling)[:count]
    rendered = _fade_edges(rendered, int(round(float(spec["edge_fade_ms"]) * sample_rate / 1000.0)))
    rendered = _normalize(rendered, float(spec["target_dbfs"]))
    return {
        "condition": "B5-saw-waveguide",
        "audio": rendered,
        "source": "saw",
        "filter": "kelly-lochbaum-waveguide",
        "areas_cm2": areas.tolist(),
        "reflection_coefficients": reflection.tolist(),
        "loss_coefficients": loss.tolist(),
        "diagnostics": {
            "internal_sample_rate": float(internal_rate),
            "maximum_reflection_absolute": float(np.max(np.abs(reflection[:-1]))),
            "minimum_loss": float(np.min(loss)),
        },
        "contains_human_audio": False,
    }


def _smooth_random_control(count: int, sample_rate: int, cutoff_hz: float, rng: np.random.Generator) -> np.ndarray:
    noise = rng.standard_normal(count)
    sos = signal.butter(2, cutoff_hz, btype="lowpass", fs=sample_rate, output="sos")
    control = signal.sosfiltfilt(sos, noise)
    central = control[max(0, count // 8) : max(1, count - count // 8)]
    control -= float(np.mean(central))
    return control / max(float(np.std(central)), 1e-12)


def varying_saw_source(
    sample_rate: int,
    count: int,
    f0_hz: float,
    variation: dict[str, float],
    rng: np.random.Generator,
) -> tuple[np.ndarray, dict[str, float]]:
    pitch = _smooth_random_control(count, sample_rate, float(variation["control_lowpass_hz"]), rng)
    independent = _smooth_random_control(count, sample_rate, float(variation["control_lowpass_hz"]), rng)
    correlation = float(variation["pitch_amplitude_correlation"])
    amplitude = correlation * pitch + math.sqrt(max(0.0, 1.0 - correlation * correlation)) * independent
    amplitude /= max(float(np.std(amplitude)), 1e-12)
    instantaneous_f0 = f0_hz * (1.0 + float(variation["f0_std_fraction"]) * pitch)
    phase = np.cumsum(instantaneous_f0 / sample_rate)
    source = signal.sawtooth(2.0 * np.pi * phase, width=0.0)
    amplitude_db = float(variation["amplitude_std_db"]) * amplitude
    source *= np.power(10.0, amplitude_db / 20.0)
    return source, {
        "rendered_f0_mean_hz": float(np.mean(instantaneous_f0)),
        "rendered_f0_std_fraction": float(np.std(instantaneous_f0) / max(np.mean(instantaneous_f0), 1e-12)),
        "rendered_amplitude_std_db": float(np.std(amplitude_db)),
        "rendered_control_correlation": float(np.corrcoef(pitch, amplitude)[0, 1]),
    }


def render_voice_quality_candidates(spec: dict[str, Any], quality: dict[str, Any]) -> list[dict[str, Any]]:
    """B2へ声門スペクトル、微細変動、aspirationを順に加える。"""
    sample_rate = int(spec["sample_rate"])
    count = int(round(float(spec["duration_sec"]) * sample_rate))
    warmup = int(round(0.1 * sample_rate))
    render_count = count + warmup
    rng = np.random.default_rng(int(spec["seed"]) + int(quality["seed_offset"]))
    static_source = saw_source(sample_rate, render_count, float(spec["f0_hz"]))
    varying_source, variation_diagnostics = varying_saw_source(
        sample_rate, render_count, float(spec["f0_hz"]), quality["microvariation"], rng,
    )
    tilt = quality["spectral_tilt"]
    tilt_b, tilt_a = signal.butter(1, float(tilt["cutoff_hz"]), btype="lowpass", fs=sample_rate)
    tilted_static = signal.lfilter(tilt_b, tilt_a, static_source)
    tilted_varying = signal.lfilter(tilt_b, tilt_a, varying_source)
    aspiration = quality["aspiration"]
    noise_sos = signal.butter(
        2,
        [float(aspiration["highpass_hz"]), float(aspiration["lowpass_hz"])],
        btype="bandpass",
        fs=sample_rate,
        output="sos",
    )
    noise = signal.sosfilt(noise_sos, rng.standard_normal(render_count))
    source_rms = float(np.sqrt(np.mean(tilted_varying[warmup:] ** 2)))
    noise_rms = float(np.sqrt(np.mean(noise[warmup:] ** 2)))
    noise *= source_rms * 10.0 ** (float(aspiration["source_rms_relative_db"]) / 20.0) / max(noise_rms, 1e-12)
    sources = (
        ("B6-tilted-saw-cascade", tilted_static, "spectral-tilt"),
        ("B7-tilted-varied-saw-cascade", tilted_varying, "spectral-tilt+microvariation"),
        ("B8-tilted-varied-aspirated-saw-cascade", tilted_varying + noise, "spectral-tilt+microvariation+aspiration"),
    )
    results: list[dict[str, Any]] = []
    for condition, source, additions in sources:
        audio, sections = cascade_all_pole(source, sample_rate, spec["formants_hz"], spec["bandwidths_hz"])
        audio = audio[warmup : warmup + count]
        audio = _fade_edges(audio, int(round(float(spec["edge_fade_ms"]) * sample_rate / 1000.0)))
        audio = _normalize(audio, float(spec["target_dbfs"]))
        results.append({
            "condition": condition,
            "audio": audio,
            "source": additions,
            "filter": "cascade",
            "filter_sections": sections,
            "diagnostics": {
                **(variation_diagnostics if "microvariation" in additions else {}),
                "tilt_cutoff_hz": float(tilt["cutoff_hz"]),
                "aspiration_source_rms_relative_db": float(aspiration["source_rms_relative_db"]) if "aspiration" in additions else None,
            },
            "contains_human_audio": False,
        })
    return results


def _corrected_controls(
    count: int,
    sample_rate: int,
    cutoff_hz: float,
    correlation: float,
    active_start: int,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """有効区間内で平均・分散・相関を固定した帯域制限制御。"""
    time_axis = np.arange(count, dtype=float) / sample_rate
    frequencies = np.linspace(max(0.5, cutoff_hz / 12.0), cutoff_hz, 12)

    def mixture() -> np.ndarray:
        phases = rng.uniform(0.0, 2.0 * np.pi, frequencies.size)
        weights = rng.uniform(0.6, 1.4, frequencies.size) / np.sqrt(frequencies)
        return np.sum(weights[:, None] * np.sin(2.0 * np.pi * frequencies[:, None] * time_axis + phases[:, None]), axis=0)

    pitch = mixture()
    independent = mixture()
    active = slice(active_start, count)
    pitch -= float(np.mean(pitch[active]))
    pitch /= max(float(np.std(pitch[active])), 1e-12)
    independent -= float(np.mean(independent[active]))
    projection = float(np.mean(independent[active] * pitch[active]))
    independent -= projection * pitch
    independent /= max(float(np.std(independent[active])), 1e-12)
    amplitude = correlation * pitch + math.sqrt(max(0.0, 1.0 - correlation * correlation)) * independent
    amplitude -= float(np.mean(amplitude[active]))
    amplitude /= max(float(np.std(amplitude[active])), 1e-12)
    return pitch, amplitude


def render_corrected_variation_candidates(
    spec: dict[str, Any],
    quality: dict[str, Any],
    correction: dict[str, Any],
) -> list[dict[str, Any]]:
    sample_rate = int(spec["sample_rate"])
    count = int(round(float(spec["duration_sec"]) * sample_rate))
    warmup = int(round(0.1 * sample_rate))
    render_count = count + warmup
    rng = np.random.default_rng(int(spec["seed"]) + int(correction["seed_offset"]))
    pitch, amplitude = _corrected_controls(
        render_count,
        sample_rate,
        float(correction["control_lowpass_hz"]),
        float(correction["pitch_amplitude_correlation"]),
        warmup,
        rng,
    )
    tilt_b, tilt_a = signal.butter(
        1, float(quality["spectral_tilt"]["cutoff_hz"]), btype="lowpass", fs=sample_rate,
    )
    active = slice(warmup, render_count)
    results: list[dict[str, Any]] = []
    for configured in correction["conditions"]:
        f0_std_fraction = float(configured["f0_std_fraction"])
        instantaneous_f0 = float(spec["f0_hz"]) * (1.0 + f0_std_fraction * pitch)
        if float(np.min(instantaneous_f0[active])) <= 0.0:
            raise ValueError("corrected variation produced non-positive F0")
        phase = np.cumsum(instantaneous_f0 / sample_rate)
        source = signal.sawtooth(2.0 * np.pi * phase, width=0.0)
        amplitude_db = float(correction["amplitude_std_db"]) * amplitude
        source *= np.power(10.0, amplitude_db / 20.0)
        source = signal.lfilter(tilt_b, tilt_a, source)
        audio, sections = cascade_all_pole(source, sample_rate, spec["formants_hz"], spec["bandwidths_hz"])
        audio = audio[warmup : warmup + count]
        audio = _fade_edges(audio, int(round(float(spec["edge_fade_ms"]) * sample_rate / 1000.0)))
        audio = _normalize(audio, float(spec["target_dbfs"]))
        results.append({
            "condition": configured["condition"],
            "audio": audio,
            "source": "spectral-tilt+corrected-microvariation",
            "filter": "cascade",
            "filter_sections": sections,
            "diagnostics": {
                "rendered_f0_mean_hz": float(np.mean(instantaneous_f0[active])),
                "rendered_f0_std_fraction": float(np.std(instantaneous_f0[active]) / np.mean(instantaneous_f0[active])),
                "rendered_amplitude_std_db": float(np.std(amplitude_db[active])),
                "rendered_control_correlation": float(np.corrcoef(pitch[active], amplitude[active])[0, 1]),
                "control_method": "bounded-sinusoid-mixture-active-region-normalized",
            },
            "contains_human_audio": False,
        })
    return results


def _normalize_stable_region(
    audio: np.ndarray,
    stable_start: int,
    stable_end: int,
    target_rms: float,
    peak_limit_dbfs: float = -1.0,
) -> np.ndarray:
    output = audio.copy()
    current = float(np.sqrt(np.mean(output[stable_start:stable_end] ** 2)))
    output *= target_rms / max(current, 1e-12)
    peak = float(np.max(np.abs(output)))
    limit = 10.0 ** (peak_limit_dbfs / 20.0)
    return output * min(1.0, limit / max(peak, 1e-12))


def render_onset_secondary_candidates(
    spec: dict[str, Any],
    quality: dict[str, Any],
    correction: dict[str, Any],
    onset: dict[str, Any],
) -> list[dict[str, Any]]:
    """合格済みB9の持続部を固定し、開始制御だけを加算する。"""
    sample_rate = int(spec["sample_rate"])
    count = int(round(float(spec["duration_sec"]) * sample_rate))
    warmup = int(round(0.1 * sample_rate))
    render_count = count + warmup
    canonical_correction = {**correction, "seed_offset": int(onset["canonical_seed_offset"])}
    canonical = render_corrected_variation_candidates(spec, quality, canonical_correction)[0]["audio"]
    stable_start = int(round(float(onset["stable_normalization_start_sec"]) * sample_rate))
    stable_end = count - int(round(float(spec["edge_fade_ms"]) * sample_rate / 1000.0))
    target_rms = float(np.sqrt(np.mean(canonical[stable_start:stable_end] ** 2)))
    attack_count = int(round(float(onset["gain_attack_ms"]) * sample_rate / 1000.0))
    gain_envelope = np.ones(count)
    gain_envelope[:attack_count] = np.sin(np.linspace(0.0, np.pi / 2.0, attack_count)) ** 2
    gain_only = _normalize_stable_region(canonical * gain_envelope, stable_start, stable_end, target_rms)

    rng_noise = np.random.default_rng(int(spec["seed"]) + int(onset["seed_offset"]))
    band = [float(value) for value in onset["aspiration_band_hz"]]
    noise_sos = signal.butter(2, band, btype="bandpass", fs=sample_rate, output="sos")
    noise_source = signal.sosfilt(noise_sos, rng_noise.standard_normal(render_count))
    filtered_noise, _ = cascade_all_pole(noise_source, sample_rate, spec["formants_hz"], spec["bandwidths_hz"])
    filtered_noise = filtered_noise[warmup : warmup + count]
    aspiration_count = int(round(float(onset["aspiration_duration_ms"]) * sample_rate / 1000.0))
    aspiration_envelope = np.zeros(count)
    aspiration_envelope[:aspiration_count] = np.sin(np.linspace(0.0, np.pi, aspiration_count)) ** 2
    filtered_noise *= aspiration_envelope
    noise_rms = float(np.sqrt(np.mean(filtered_noise[:aspiration_count] ** 2)))
    filtered_noise *= target_rms * 10.0 ** (float(onset["aspiration_output_rms_relative_db"]) / 20.0) / max(noise_rms, 1e-12)
    gain_aspiration = _normalize_stable_region(gain_only + filtered_noise, stable_start, stable_end, target_rms)

    rng_control = np.random.default_rng(int(spec["seed"]) + int(onset["canonical_seed_offset"]))
    pitch, amplitude = _corrected_controls(
        render_count,
        sample_rate,
        float(correction["control_lowpass_hz"]),
        float(correction["pitch_amplitude_correlation"]),
        warmup,
        rng_control,
    )
    subtle = correction["conditions"][0]
    f0 = float(spec["f0_hz"]) * (1.0 + float(subtle["f0_std_fraction"]) * pitch)
    settlement_count = int(round(float(onset["f0_settlement_ms"]) * sample_rate / 1000.0))
    settlement = np.ones(render_count)
    active_progress = np.linspace(0.0, 1.0, settlement_count)
    settlement[warmup : warmup + settlement_count] = float(onset["f0_start_ratio"]) + (1.0 - float(onset["f0_start_ratio"])) * np.sin(active_progress * np.pi / 2.0) ** 2
    phase = np.cumsum(f0 * settlement / sample_rate)
    settled_source = signal.sawtooth(2.0 * np.pi * phase, width=0.0)
    settled_source *= np.power(10.0, float(correction["amplitude_std_db"]) * amplitude / 20.0)
    tilt_b, tilt_a = signal.butter(1, float(quality["spectral_tilt"]["cutoff_hz"]), btype="lowpass", fs=sample_rate)
    settled_source = signal.lfilter(tilt_b, tilt_a, settled_source)
    settled_audio, sections = cascade_all_pole(settled_source, sample_rate, spec["formants_hz"], spec["bandwidths_hz"])
    settled_audio = settled_audio[warmup : warmup + count] * gain_envelope
    settled_audio += filtered_noise
    settled_audio = _fade_edges(settled_audio, int(round(float(spec["edge_fade_ms"]) * sample_rate / 1000.0)))
    coupled = _normalize_stable_region(settled_audio, stable_start, stable_end, target_rms)

    common = {
        "filter": "cascade",
        "filter_sections": sections,
        "contains_human_audio": False,
        "stable_normalization_start_sec": float(onset["stable_normalization_start_sec"]),
    }
    return [
        {"condition": "O0-b9-common-edge", "audio": canonical, "source": "B9", "onset_additions": [], **common},
        {"condition": "O1-b9-gain-attack", "audio": gain_only, "source": "B9", "onset_additions": ["gain-attack"], **common},
        {"condition": "O2-b9-gain-aspiration", "audio": gain_aspiration, "source": "B9", "onset_additions": ["gain-attack", "decaying-aspiration"], **common},
        {"condition": "O3-b9-coupled-onset", "audio": coupled, "source": "B9-with-f0-settlement", "onset_additions": ["gain-attack", "decaying-aspiration", "f0-settlement"], **common},
    ]


def render_f0_generalization_candidates(
    spec: dict[str, Any],
    quality: dict[str, Any],
    correction: dict[str, Any],
    onset: dict[str, Any],
    f0_values_hz: list[float],
) -> list[dict[str, Any]]:
    """B9と40 ms gain attackを複数F0へ移し、知覚評価前の候補を作る。"""
    results: list[dict[str, Any]] = []
    for f0_hz in f0_values_hz:
        if f0_hz <= 0.0:
            raise ValueError("F0は正である必要があります")
        local_spec = {**spec, "f0_hz": float(f0_hz)}
        local_onset = {**onset, "gain_attack_ms": 40.0}
        sustain = render_corrected_variation_candidates(local_spec, quality, correction)[0]
        onset_candidates = render_onset_secondary_candidates(local_spec, quality, correction, local_onset)
        gain_attack = onset_candidates[1]
        label = int(round(f0_hz))
        sustain["condition"] = f"F{label}-B9-sustain"
        sustain["f0_hz"] = float(f0_hz)
        sustain["generalization_status"] = "preflight-not-perceptually-approved"
        gain_attack["condition"] = f"F{label}-G40-onset"
        gain_attack["f0_hz"] = float(f0_hz)
        gain_attack["gain_attack_ms"] = 40.0
        gain_attack["generalization_status"] = "preflight-not-perceptually-approved"
        results.extend((sustain, gain_attack))
    return results


def render_vowel_generalization_candidates(
    spec: dict[str, Any],
    quality: dict[str, Any],
    correction: dict[str, Any],
    onset: dict[str, Any],
    profiles: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """声門側のB9/G40を固定し、声道のformant極だけを母音ごとに交換する。"""
    results: list[dict[str, Any]] = []
    for vowel, profile in profiles.items():
        formants = [float(value) for value in profile["formants_hz"]]
        bandwidths = [float(value) for value in profile["bandwidths_hz"]]
        if len(formants) != 3 or len(bandwidths) != 3:
            raise ValueError(f"/{vowel}/: F1〜F3と帯域幅は各3値必要です")
        if any(value <= 0.0 for value in formants + bandwidths) or formants != sorted(formants):
            raise ValueError(f"/{vowel}/: formantと帯域幅が不正です")
        local_spec = {**spec, "formants_hz": formants, "bandwidths_hz": bandwidths}
        local_onset = {**onset, "gain_attack_ms": 40.0}
        sustain = render_corrected_variation_candidates(local_spec, quality, correction)[0]
        gain_attack = render_onset_secondary_candidates(local_spec, quality, correction, local_onset)[1]
        common = {
            "vowel": vowel,
            "f0_hz": float(local_spec["f0_hz"]),
            "formants_hz": formants,
            "bandwidths_hz": bandwidths,
            "profile_provenance": profile["provenance"],
            "generalization_status": "preflight-not-perceptually-approved",
        }
        sustain.update({"condition": f"V-{vowel}-B9-sustain", **common})
        gain_attack.update({"condition": f"V-{vowel}-G40-onset", "gain_attack_ms": 40.0, **common})
        results.extend((sustain, gain_attack))
    return results


def render_gain_attack_scaling_candidates(
    spec: dict[str, Any],
    quality: dict[str, Any],
    correction: dict[str, Any],
    onset: dict[str, Any],
    f0_values_hz: list[float],
    fixed_duration_ms: float,
    reference_cycles: float,
) -> list[dict[str, Any]]:
    """固定時間attackと、同じ周期数を保つattackを各F0で生成する。"""
    if fixed_duration_ms <= 0.0 or reference_cycles <= 0.0:
        raise ValueError("attack時間と周期数は正である必要があります")
    results: list[dict[str, Any]] = []
    for f0_hz in f0_values_hz:
        if f0_hz <= 0.0:
            raise ValueError("F0は正である必要があります")
        local_spec = {**spec, "f0_hz": float(f0_hz)}
        scaled_duration_ms = 1000.0 * reference_cycles / float(f0_hz)
        label = int(round(f0_hz))
        for rule, duration_ms in (("fixed", fixed_duration_ms), ("cycle", scaled_duration_ms)):
            candidate = render_onset_secondary_candidates(
                local_spec, quality, correction, {**onset, "gain_attack_ms": float(duration_ms)},
            )[1]
            candidate.update({
                "condition": f"A{label}-{rule}-gain-attack",
                "f0_hz": float(f0_hz),
                "gain_attack_rule": rule,
                "gain_attack_ms": float(duration_ms),
                "gain_attack_cycles": float(duration_ms) * float(f0_hz) / 1000.0,
                "generalization_status": "preflight-not-perceptually-approved",
            })
            results.append(candidate)
    return results


def render_candidates(spec: dict[str, Any]) -> list[dict[str, Any]]:
    sample_rate = int(spec["sample_rate"])
    count = int(round(float(spec["duration_sec"]) * sample_rate))
    warmup = int(round(0.1 * sample_rate))
    render_count = count + warmup
    sources = {
        "saw": saw_source(sample_rate, render_count, float(spec["f0_hz"])),
        "lf-family": lf_family_source(sample_rate, render_count, float(spec["f0_hz"]), spec["lf_family"]),
    }
    combinations = (
        ("B0-saw-parallel", "saw", "parallel"),
        ("B1-lf-parallel", "lf-family", "parallel"),
        ("B2-saw-cascade", "saw", "cascade"),
        ("B3-lf-cascade", "lf-family", "cascade"),
    )
    results: list[dict[str, Any]] = []
    for condition, source_name, filter_name in combinations:
        source = sources[source_name]
        sections: list[dict[str, Any]] = []
        if filter_name == "parallel":
            audio = parallel_formants(source, sample_rate, spec["formants_hz"], spec["bandwidths_hz"], spec["parallel_gains"])
        else:
            audio, sections = cascade_all_pole(source, sample_rate, spec["formants_hz"], spec["bandwidths_hz"])
        audio = audio[warmup : warmup + count]
        audio = _fade_edges(audio, int(round(float(spec["edge_fade_ms"]) * sample_rate / 1000.0)))
        audio = _normalize(audio, float(spec["target_dbfs"]))
        results.append({
            "condition": condition,
            "audio": audio,
            "source": source_name,
            "filter": filter_name,
            "filter_sections": sections,
            "contains_human_audio": False,
        })
    return results
