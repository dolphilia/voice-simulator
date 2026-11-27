//! 保存された波形と観測値を、同じ出力フレームの区間で計測する。

mod input;

use self::input::{Artifact, Coordinate, RegisteredArtifact, Run, Trace, Wave, WaveFormat};
use crate::{read_case, write_json};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    error::Error,
    io,
    ops::Range,
    path::{Path, PathBuf},
};

#[derive(Deserialize)]
struct Case {
    id: String,
    revision: u32,
    upstream_revision: String,
    input: Input,
    measurement: Measurement,
}

#[derive(Deserialize)]
struct Input {
    reference_wave: PathBuf,
    candidate_wave: PathBuf,
    reference_trace: Option<PathBuf>,
    candidate_trace: Option<PathBuf>,
}

#[derive(Deserialize)]
struct Measurement {
    sample_rate_hz: u32,
    output_frames: u64,
    output_frame_range: Option<[u64; 2]>,
    internal_samples_per_output_frame: u64,
    pcm_absolute_tolerance: f64,
    #[serde(default)]
    require_pcm_bit_exact: bool,
    state_peak_relative_tolerance: Option<f64>,
    #[serde(default)]
    observation_fields: Vec<String>,
    #[serde(default)]
    reference_trace_coordinate: Coordinate,
    #[serde(default)]
    candidate_trace_coordinate: Coordinate,
}

impl Measurement {
    fn interval(&self) -> Result<Range<u64>, &'static str> {
        let [start, end] = self.output_frame_range.unwrap_or([0, self.output_frames]);
        if start >= end
            || end > self.output_frames
            || self.sample_rate_hz == 0
            || self.internal_samples_per_output_frame == 0
            || self
                .output_frames
                .checked_mul(self.internal_samples_per_output_frame)
                .is_none()
        {
            return Err("比較区間・サンプルレート・内部倍率を確認してください");
        }
        if !self.pcm_absolute_tolerance.is_finite() || self.pcm_absolute_tolerance < 0.0 {
            return Err("PCMの許容差には有限の非負値を指定してください");
        }
        Ok(start..end)
    }

    fn end_sample(&self, frame: u64) -> u64 {
        (frame + 1) * self.internal_samples_per_output_frame - 1
    }
}

#[derive(Serialize)]
struct PcmComparison {
    different_bits: Option<u64>,
    first_bit_difference_frame: Option<u64>,
    first_bit_difference_values: Option<[f32; 2]>,
    maximum_absolute_error: f64,
    first_numeric_difference_frame: Option<u64>,
    first_frame_over_tolerance: Option<u64>,
    status: bool,
}

fn compare_pcm(
    mut reference: Wave,
    mut candidate: Wave,
    limits: &Measurement,
    frames: Range<u64>,
) -> Result<PcmComparison, Box<dyn Error>> {
    if [&reference, &candidate]
        .iter()
        .any(|wave| wave.rate != limits.sample_rate_hz || wave.frames != limits.output_frames)
    {
        return Err(format!(
            "WAVのレートまたは長さが比較条件と異なります (基準 {} Hz/{} フレーム、候補 {} Hz/{} フレーム、指定 {} Hz/{} フレーム)",
            reference.rate, reference.frames, candidate.rate, candidate.frames, limits.sample_rate_hz, limits.output_frames
        ).into());
    }
    let same_format = reference.format == candidate.format;
    if limits.require_pcm_bit_exact && !same_format {
        return Err("ビット一致の比較には同じ保存形式のWAVを指定してください".into());
    }
    let mut result = PcmComparison {
        different_bits: same_format.then_some(0),
        first_bit_difference_frame: None,
        first_bit_difference_values: None,
        maximum_absolute_error: 0.0,
        first_numeric_difference_frame: None,
        first_frame_over_tolerance: None,
        status: true,
    };
    for frame in 0..limits.output_frames {
        let expected = reference.sample()?;
        let actual = candidate.sample()?;
        if !frames.contains(&frame) {
            continue;
        }
        if let Some(count) = &mut result.different_bits
            && actual.to_bits() != expected.to_bits()
        {
            *count += 1;
            if result.first_bit_difference_frame.is_none() {
                result.first_bit_difference_frame = Some(frame);
                result.first_bit_difference_values = Some([actual, expected]);
            }
        }
        let difference = (f64::from(actual) - f64::from(expected)).abs();
        result.maximum_absolute_error = result.maximum_absolute_error.max(difference);
        if difference > 0.0 {
            result.first_numeric_difference_frame.get_or_insert(frame);
        }
        if difference > limits.pcm_absolute_tolerance {
            result.first_frame_over_tolerance.get_or_insert(frame);
        }
    }
    reference.finish()?;
    candidate.finish()?;
    result.status = result.first_frame_over_tolerance.is_none()
        && (!limits.require_pcm_bit_exact || result.different_bits == Some(0));
    Ok(result)
}

#[derive(Serialize)]
struct Difference {
    output_frame: u64,
    internal_sample: u64,
    candidate: f64,
    reference: f64,
}

#[derive(Serialize)]
struct StateComparison {
    reference_peak: f64,
    max_absolute_difference: f64,
    max_abs_diff_over_reference_peak: Option<f64>,
    first_difference: Option<Difference>,
    first_frame_over_tolerance: Option<u64>,
    status: bool,
}

fn compare_states(
    reference: (&Run, &Artifact),
    candidate: (&Run, &Artifact),
    limits: &Measurement,
    frames: Range<u64>,
) -> Result<BTreeMap<String, StateComparison>, Box<dyn Error>> {
    let fields = &limits.observation_fields;
    if fields.is_empty()
        || fields
            .iter()
            .enumerate()
            .any(|(i, key)| key.is_empty() || fields[..i].contains(key))
    {
        return Err("観測列を重複なく指定してください".into());
    }
    let tolerance = limits
        .state_peak_relative_tolerance
        .filter(|t| t.is_finite() && *t > 0.0)
        .ok_or("観測列のピーク相対許容差には正の有限値を指定してください")?;
    let ref_axis = limits.reference_trace_coordinate;
    let cand_axis = limits.candidate_trace_coordinate;
    let open_ref = || Trace::open(reference.0, reference.1, ref_axis, fields);
    let mut peak_scan = open_ref()?;
    let mut peaks: Vec<f64> = vec![0.0; fields.len()];
    let mut ref_values = vec![0.0; fields.len()];
    for frame in frames.clone() {
        peak_scan.values_at(
            ref_axis.at(frame, limits.end_sample(frame)),
            &mut ref_values,
        )?;
        for (peak, value) in peaks.iter_mut().zip(&ref_values) {
            *peak = peak.max(value.abs());
        }
    }
    peak_scan.finish()?;

    let mut reference = open_ref()?;
    let mut candidate = Trace::open(candidate.0, candidate.1, cand_axis, fields)?;
    let mut cand_values = vec![0.0; fields.len()];
    let mut series: Vec<_> = peaks
        .into_iter()
        .map(|reference_peak| StateComparison {
            reference_peak,
            max_absolute_difference: 0.0,
            max_abs_diff_over_reference_peak: None,
            first_difference: None,
            first_frame_over_tolerance: None,
            status: true,
        })
        .collect();
    for frame in frames {
        let sample = limits.end_sample(frame);
        reference.values_at(ref_axis.at(frame, sample), &mut ref_values)?;
        candidate.values_at(cand_axis.at(frame, sample), &mut cand_values)?;
        for (row, (&expected, &actual)) in
            series.iter_mut().zip(ref_values.iter().zip(&cand_values))
        {
            let error = (actual - expected).abs();
            if !error.is_finite() {
                return Err("観測値の差が数値の範囲を超えています".into());
            }
            row.max_absolute_difference = row.max_absolute_difference.max(error);
            if error > 0.0 {
                row.first_difference.get_or_insert(Difference {
                    output_frame: frame,
                    internal_sample: sample,
                    candidate: actual,
                    reference: expected,
                });
                if error >= tolerance * row.reference_peak {
                    row.first_frame_over_tolerance.get_or_insert(frame);
                }
            }
        }
    }
    reference.finish()?;
    candidate.finish()?;
    for row in &mut series {
        row.status = row.first_frame_over_tolerance.is_none();
        let error = row.max_absolute_difference;
        row.max_abs_diff_over_reference_peak = if error == 0.0 {
            Some(0.0)
        } else {
            let relative = error / row.reference_peak;
            relative.is_finite().then_some(relative)
        };
    }
    Ok(fields.iter().cloned().zip(series).collect())
}

fn source_report(
    run: &Run,
    wave: RegisteredArtifact<'_>,
    format: WaveFormat,
    trace: Option<RegisteredArtifact<'_>>,
) -> Value {
    let mut report = json!({
        "run_id": run.manifest.run_id,
        "recorded_status": wave.status,
        "sample_format": format,
        "wave": wave.entry,
        "trace": trace.as_ref().map(|item| item.entry),
    });
    if let Some(case_id) = wave.case_id {
        report["recorded_case_id"] = json!(case_id);
    }
    if let Some(item) = trace
        && let Some(case_id) = item.case_id
    {
        report["trace_case_id"] = json!(case_id);
        report["trace_recorded_status"] = json!(item.status);
    }
    report
}

pub(super) fn run(reference: &Path, candidate: &Path, path: &Path) -> Result<(), Box<dyn Error>> {
    let case = Case::deserialize(read_case(path)?)?;
    let limits = &case.measurement;
    let frames = limits.interval()?;
    let reference = Run::load(reference)?;
    let candidate = Run::load(candidate)?;
    if [&reference, &candidate]
        .iter()
        .any(|run| run.manifest.upstream_revision != case.upstream_revision)
    {
        return Err("比較ケースと実行記録の固定上流コミットが異なります".into());
    }
    let input = &case.input;
    let reference_wave = reference.artifact(&input.reference_wave)?;
    let candidate_wave = candidate.artifact(&input.candidate_wave)?;
    let reference_audio = Wave::open(&reference, reference_wave.entry)?;
    let candidate_audio = Wave::open(&candidate, candidate_wave.entry)?;
    let (reference_format, candidate_format) = (reference_audio.format, candidate_audio.format);
    let pcm = compare_pcm(reference_audio, candidate_audio, limits, frames.clone())?;
    let (reference_trace, candidate_trace, states) =
        match (&input.reference_trace, &input.candidate_trace) {
            (Some(a), Some(b)) => {
                let a = reference.artifact(a)?;
                let b = candidate.artifact(b)?;
                let states = compare_states(
                    (&reference, a.entry),
                    (&candidate, b.entry),
                    limits,
                    frames.clone(),
                )?;
                (Some(a), Some(b), states)
            }
            (None, None) if limits.observation_fields.is_empty() => (None, None, BTreeMap::new()),
            _ => return Err("観測列を比べる場合は基準・候補のCSVを両方指定してください".into()),
        };
    let passed = pcm.status && states.values().all(|row| row.status);
    write_json(
        io::stdout().lock(),
        &json!({
            "case_id": case.id, "revision": case.revision, "upstream_revision": case.upstream_revision,
            "reference": source_report(&reference, reference_wave, reference_format, reference_trace),
            "candidate": source_report(&candidate, candidate_wave, candidate_format, candidate_trace),
            "sample_rate_hz": limits.sample_rate_hz, "output_frames": limits.output_frames,
            "output_frame_range": [frames.start, frames.end],
            "internal_samples_per_output_frame": limits.internal_samples_per_output_frame,
            "thresholds": {
                "pcm_absolute": limits.pcm_absolute_tolerance,
                "pcm_bit_exact": limits.require_pcm_bit_exact,
                "state_peak_relative": limits.state_peak_relative_tolerance,
            },
            "pcm": pcm, "states": states, "status": if passed { "pass" } else { "fail" },
        }),
    )?;
    if !passed {
        return Err("保存済み実行の比較が許容差を超えました".into());
    }
    Ok(())
}
