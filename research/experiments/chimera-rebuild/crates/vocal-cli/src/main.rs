use serde::{Deserialize, Serialize};
use serde_json::json;
use std::env;
use std::error::Error;
use std::fs::{self, File};
use std::io::{self, BufWriter, Write};
use std::path::Path;
use std::process::ExitCode;
use vocal_core::airway::{TubeGeometry, UniformTube, WallParameters};

mod alligator_case;
mod articulation_case;
mod axial_case;
mod elephant_case;
mod english_case;
mod geometry_case;
mod ipa_case;
mod lip_reed_case;
mod live_song_case;
mod network_case;
mod saved_compare;
mod seal_airway_case;
mod seal_breath_case;
mod seal_voice_case;
mod song_case;
mod songbird_case;
mod songbird_voice_case;
mod syrinx_case;
mod timing_case;
use network_case::Destination;

const USAGE: &str = "使用法\n  vocal-cli inspect <ケース.json>\n  vocal-cli compare <基準の実行> <候補の実行> <比較ケース.json>\n  vocal-cli render <ケース.json> <出力.csv または .json>\n  vocal-cli render-pcm <ケース.json> <出力.wav> <計測.csv または --no-trace> [ブロックのフレーム数]\n  vocal-cli render-pcm-tele <歌唱ケース.json> <出力.wav> <計測.csv> <声部.tele> [ブロックのフレーム数]\n  vocal-cli geometry <ケース.json> <輪郭.csv>\n  vocal-cli grid <ケース.json> <測定格子.csv>\n  vocal-cli contact <ケース.json> <補正後の格子.csv>\n  vocal-cli area <ケース.json> <断面積と中心線.csv>\n  vocal-cli resample <ケース.json> <セル断面.csv>\n  vocal-cli transfer <ケース.json> <伝達関数.csv>\n  vocal-cli observe-axis <観測設定.json> <口端流量.csv> <音圧.csv>\n  vocal-cli english <英語テキスト>\n  vocal-cli ipa <IPA文字列>\n  vocal-cli plan <IPA文字列> [話速倍率]";

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Case {
    id: String,
    upstream_revision: String,
    hypothesis: String,
    tube: Tube,
    #[serde(skip_serializing_if = "Option::is_none")]
    wall: Option<Wall>,
    impulse: Impulse,
    measurement: Measurement,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Tube {
    length_cm: f64,
    area_cm2: f64,
    cells: usize,
    sample_rate_hz: u32,
    #[serde(skip_serializing_if = "Option::is_none")]
    viscous_scale: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    outlet_half_cell: Option<bool>,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Wall {
    mass_g_cm2: f64,
    resistance_dyn_s_cm3: f64,
    stiffness_dyn_cm3: f64,
    radiation_fraction: f64,
}

impl From<Wall> for WallParameters {
    fn from(wall: Wall) -> Self {
        Self {
            mass_g_cm2: wall.mass_g_cm2,
            resistance_dyn_s_cm3: wall.resistance_dyn_s_cm3,
            stiffness_dyn_cm3: wall.stiffness_dyn_cm3,
            radiation_fraction: wall.radiation_fraction,
        }
    }
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Impulse {
    sample: usize,
    volume_cm3: f64,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Measurement {
    sample_count: usize,
    tail_sample_count: usize,
    sweep_start_hz: f64,
    sweep_end_hz: f64,
    sweep_points: usize,
    observed_peaks_below_hz: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    quarter_wave_modes: Option<usize>,
    #[serde(skip_serializing_if = "Option::is_none")]
    quarter_wave_relative_error_lt: Option<f64>,
    fdtd_vs_linear_relative_error_lt: f64,
    tail_over_peak_lt: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    wall_checks: Option<WallChecks>,
    #[serde(skip_serializing_if = "Option::is_none")]
    radiation_energy: Option<bool>,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct WallChecks {
    peak_count: usize,
    first_mode_shift_min_hz: f64,
    upstream_peak_absolute_error_lt_hz: f64,
    upstream_trace_peak_relative_error_lt: f64,
    endpoint_balance_peak_relative_error_lt: f64,
}

impl Case {
    fn from_value(input: serde_json::Value) -> Result<Self, Box<dyn Error>> {
        let case: Self = serde_json::from_value(input)?;
        case.geometry()
            .coefficients()?
            .with_viscous_scale(case.tube.viscous_scale.unwrap_or(1.0))?;
        let m = &case.measurement;
        if m.radiation_energy.unwrap_or(false)
            && (case.wall.is_some() || case.tube.viscous_scale.unwrap_or(1.0) != 0.0)
        {
            return Err("放射のエネルギー計測には剛体かつ管内粘性なしの設定が必要です".into());
        }
        match (
            case.wall,
            &m.wall_checks,
            m.quarter_wave_modes,
            m.quarter_wave_relative_error_lt,
        ) {
            (None, None, Some(modes), Some(error)) if modes > 0 && 0.0 < error && error < 1.0 => {}
            (Some(wall), Some(checks), None, None) => {
                WallParameters::from(wall).validate()?;
                if checks.peak_count == 0
                    || ![
                        checks.first_mode_shift_min_hz,
                        checks.upstream_peak_absolute_error_lt_hz,
                        checks.upstream_trace_peak_relative_error_lt,
                        checks.endpoint_balance_peak_relative_error_lt,
                    ]
                    .into_iter()
                    .all(|value| value.is_finite() && value > 0.0)
                {
                    return Err("軟壁ケースの測定条件が不正です".into());
                }
            }
            _ => return Err("壁の設定と共鳴の判定条件が一致しません".into()),
        }
        let first_signal_sample = case.impulse.sample.saturating_add(case.tube.cells - 1);
        if first_signal_sample >= m.sample_count.saturating_sub(m.tail_sample_count) {
            return Err("インパルスの到達前に測定区間が終わります".into());
        }
        let impulse_flow = case.impulse.volume_cm3 * f64::from(case.tube.sample_rate_hz);
        if impulse_flow == 0.0 || !impulse_flow.is_finite() {
            return Err("インパルスの流量にはゼロ以外の有限値が必要です".into());
        }
        if m.tail_sample_count == 0
            || m.sweep_points < 3
            || !(0.0 < m.sweep_start_hz
                && m.sweep_start_hz < m.observed_peaks_below_hz
                && m.observed_peaks_below_hz < m.sweep_end_hz
                && m.sweep_end_hz < f64::from(case.tube.sample_rate_hz) * 0.5)
        {
            return Err("測定区間または周波数の範囲が不正です".into());
        }
        if ![m.fdtd_vs_linear_relative_error_lt, m.tail_over_peak_lt]
            .into_iter()
            .all(|value| 0.0 < value && value < 1.0)
        {
            return Err("測定の許容値には 0 と 1 の間の比率が必要です".into());
        }
        Ok(case)
    }

    fn geometry(&self) -> TubeGeometry {
        TubeGeometry {
            length_cm: self.tube.length_cm,
            area_cm2: self.tube.area_cm2,
            cells: self.tube.cells,
            sample_rate_hz: self.tube.sample_rate_hz,
        }
    }
}

fn inspect(case: &Case) -> Result<(), Box<dyn Error>> {
    let coeff = case
        .geometry()
        .coefficients()?
        .with_viscous_scale(case.tube.viscous_scale.unwrap_or(1.0))?;
    let mut output = io::stdout().lock();
    let mut report = json!({
        "case": case,
        "unit_system": "CGS",
        "cell_length_cm": coeff.cell_length_cm,
        "step_seconds": coeff.step_seconds,
        "courant": coeff.courant,
        "cell_compliance_cm3_per_dyn_cm2": coeff.cell_compliance,
        "branch_inertance_g_cm4": coeff.branch_inertance,
        "branch_resistance_dyn_s_cm5": coeff.branch_resistance,
        "radiation_inertance_g_cm4": coeff.radiation_inertance,
        "radiation_resistance_dyn_s_cm5": coeff.radiation_resistance,
    });
    if case.tube.outlet_half_cell.unwrap_or(false) {
        report["outlet_series_inertance_g_cm4"] = json!(0.5 * coeff.branch_inertance);
    }
    serde_json::to_writer_pretty(&mut output, &report)?;
    writeln!(output)?;
    Ok(())
}

fn render(case: &Case, output_path: &Path) -> Result<(), Box<dyn Error>> {
    let mut tube = match case.wall {
        Some(wall) => UniformTube::with_wall(case.geometry(), wall.into())?,
        None => UniformTube::new(case.geometry())?,
    }
    .with_viscous_scale(case.tube.viscous_scale.unwrap_or(1.0))?;
    if case.tube.outlet_half_cell.unwrap_or(false) {
        tube = tube.with_outlet_half_cell()?;
    }
    let energy_observation = case.measurement.radiation_energy.unwrap_or(false);
    let file = File::create_new(output_path)
        .map_err(|error| format!("{}: 出力を作成できません ({error})", output_path.display()))?;
    let mut output = BufWriter::new(file);
    write!(
        output,
        "sample,inlet_flow_cm3_s,inlet_pressure_dyn_cm2,outlet_pressure_dyn_cm2,radiation_flow_cm3_s,radiation_flow_derivative_cm3_s2"
    )?;
    if case.wall.is_some() {
        write!(
            output,
            ",inlet_wall_flow_cm3_s,outlet_wall_flow_cm3_s,total_wall_flow_cm3_s,wall_radiation_flow_cm3_s,inlet_branch_flow_cm3_s,outlet_branch_flow_cm3_s"
        )?;
    }
    if energy_observation {
        write!(
            output,
            ",outlet_branch_flow_cm3_s,radiation_load_pressure_mid_dyn_cm2,half_cell_flow_cm3_s,radiation_inertance_flow_cm3_s,stored_energy_erg"
        )?;
    }
    writeln!(output)?;
    for sample_index in 0..case.measurement.sample_count {
        let flow = if sample_index == case.impulse.sample {
            case.impulse.volume_cm3 * f64::from(case.tube.sample_rate_hz)
        } else {
            0.0
        };
        let sample = tube.step(flow);
        let values = [
            sample.inlet_pressure_dyn_cm2,
            sample.outlet_pressure_dyn_cm2,
            sample.radiation_flow_cm3_s,
            sample.radiation_flow_derivative_cm3_s2,
        ];
        if !values.into_iter().all(f64::is_finite) {
            return Err(format!("サンプル {sample_index} の観測値が非有限です").into());
        }
        let [inlet_pressure, outlet_pressure, radiation_flow, derivative] = values;
        write!(
            output,
            "{sample_index},{flow},{inlet_pressure},{outlet_pressure},{radiation_flow},{derivative}"
        )?;
        if let Some(wall) = sample.wall {
            let wall_values = [
                wall.inlet_wall_flow_cm3_s,
                wall.outlet_wall_flow_cm3_s,
                wall.total_wall_flow_cm3_s,
                wall.wall_radiation_flow_cm3_s,
                wall.inlet_branch_flow_cm3_s,
                wall.outlet_branch_flow_cm3_s,
            ];
            if !wall_values.into_iter().all(f64::is_finite) {
                return Err(format!("サンプル {sample_index} の壁・枝流量が非有限です").into());
            }
            for value in wall_values {
                write!(output, ",{value}")?;
            }
        }
        if energy_observation {
            let energy = tube
                .lossless_energy()
                .ok_or("剛体かつ管内粘性なしの計測が必要です")?;
            let values = [
                sample.outlet_branch_flow_cm3_s,
                sample.radiation_load_pressure_mid_dyn_cm2,
                energy.half_cell_flow_cm3_s,
                energy.radiation_inertance_flow_cm3_s,
                energy.stored_energy_erg,
            ];
            if !values.into_iter().all(f64::is_finite) {
                return Err(
                    format!("サンプル {sample_index} のエネルギー計測値が非有限です").into(),
                );
            }
            for value in values {
                write!(output, ",{value}")?;
            }
        }
        writeln!(output)?;
    }
    output.flush()?;
    Ok(())
}

fn write_json(mut out: impl Write, value: &impl Serialize) -> Result<(), Box<dyn Error>> {
    serde_json::to_writer_pretty(&mut out, value)?;
    writeln!(out)?;
    out.flush()?;
    Ok(())
}

fn read_case(path: &Path) -> Result<serde_json::Value, Box<dyn Error>> {
    let contents = fs::read(path).map_err(|error| format!("{}: {error}", path.display()))?;
    Ok(serde_json::from_slice(&contents)
        .map_err(|error| format!("{}: ケースの形式エラー ({error})", path.display()))?)
}

fn run_case(path: &Path, destination: Destination<'_>) -> Result<(), Box<dyn Error>> {
    let input = read_case(path)?;
    if input.get("ipa").is_some() {
        ipa_case::run(input, destination)
    } else if input.get("speech_timing").is_some() {
        timing_case::run(input, destination)
    } else if input.get("english_text").is_some() {
        english_case::run(input, destination)
    } else if input.get("song_plan").is_some() {
        song_case::run(input, destination)
    } else if input.get("song_voice").is_some() {
        timing_case::speech_voice::run_song(input, destination, None)
    } else if input.get("live_song_voice").is_some() {
        live_song_case::run(input, destination)
    } else if input.get("speech_voice").is_some() {
        timing_case::speech_voice::run(input, destination)
    } else if input.get("beatbox_voice").is_some() {
        timing_case::speech_voice::run_beatbox(input, destination)
    } else if input.get("beatbox_pattern").is_some() {
        timing_case::speech_voice::beat_pattern::run(input, destination)
    } else if let Some(settings) = input.get("syrinx_labia") {
        syrinx_case::run(settings, destination)
    } else if let Some(settings) = input.get("songbird_airway") {
        songbird_case::run(settings, destination)
    } else if let Some(settings) = input.get("songbird_voice") {
        songbird_voice_case::run(settings, destination)
    } else if let Some(settings) = input.get("seal_breath") {
        seal_breath_case::run(settings, destination)
    } else if let Some(settings) = input.get("alligator_voice") {
        alligator_case::run(settings, destination)
    } else if let Some(settings) = input.get("elephant_voice") {
        elephant_case::run(settings, destination)
    } else if let Some(settings) = input.get("lip_reed") {
        lip_reed_case::run(settings, destination)
    } else if let Some(settings) = input.get("seal_airway") {
        seal_airway_case::run(settings, destination)
    } else if let Some(settings) = input.get("seal_voice") {
        seal_voice_case::run(settings, destination)
    } else if input.get("network").is_some() {
        network_case::run(input, destination)
    } else if input.get("articulators").is_some() {
        articulation_case::run(input, destination)
    } else if input.get("posture").is_some() {
        match destination {
            Destination::Inspect => geometry_case::inspect(&input),
            Destination::Trace(_) | Destination::Pcm { .. } if input.get("voice").is_some() => {
                geometry_case::render_fixed_voice(&input, destination)
            }
            Destination::Trace(path) if input.get("fixed_airway").is_some() => {
                geometry_case::render_fixed_airway(&input, path)
            }
            _ => Err(
                "姿勢ケースには geometry、grid、contact、area、resample のいずれかを指定してください".into(),
            ),
        }
    } else {
        let case = Case::from_value(input)?;
        match destination {
            Destination::Trace(path) => render(&case, path),
            Destination::Inspect => inspect(&case),
            Destination::Pcm { .. } => {
                Err("PCMの出力にはネットワーク形式のケースを指定してください".into())
            }
        }
    }
}

fn run() -> Result<(), Box<dyn Error>> {
    let args = env::args().skip(1).collect::<Vec<_>>();
    match args.as_slice() {
        [option] if option == "-h" || option == "--help" => println!("{USAGE}"),
        [command, path] if command == "inspect" => run_case(Path::new(path), Destination::Inspect)?,
        [command, reference, candidate, case] if command == "compare" => {
            saved_compare::run(Path::new(reference), Path::new(candidate), Path::new(case))?;
        }
        [command, path, source, output] if command == "observe-axis" => {
            axial_case::observe(
                read_case(Path::new(path))?,
                Path::new(source),
                Path::new(output),
            )?;
        }
        [command, input] if command == "english" => english_case::from_text(input)?,
        [command, input] if command == "ipa" => ipa_case::from_text(input)?,
        [command, input] if command == "plan" => timing_case::from_text(input, 1.0)?,
        [command, input, rate] if command == "plan" => {
            let rate = rate
                .parse()
                .map_err(|_| "話速倍率は数値で指定してください")?;
            timing_case::from_text(input, rate)?;
        }
        [command, path, output] if command == "geometry" => {
            geometry_case::render(&read_case(Path::new(path))?, Path::new(output))?;
        }
        [command, path, output] if command == "grid" => {
            geometry_case::render_grid(&read_case(Path::new(path))?, Path::new(output))?;
        }
        [command, path, output] if command == "contact" => {
            geometry_case::render_contact(&read_case(Path::new(path))?, Path::new(output))?;
        }
        [command, path, output] if command == "area" => {
            geometry_case::render_area(&read_case(Path::new(path))?, Path::new(output))?;
        }
        [command, path, output] if command == "resample" => {
            geometry_case::render_resampled(&read_case(Path::new(path))?, Path::new(output))?;
        }
        [command, path, output] if command == "transfer" => {
            geometry_case::render_transfer(&read_case(Path::new(path))?, Path::new(output))?;
        }
        [command, path, output] if command == "render" => {
            run_case(Path::new(path), Destination::Trace(Path::new(output)))?;
        }
        [command, path, wave, trace, telemetry, tail @ ..]
            if command == "render-pcm-tele" && tail.len() <= 1 =>
        {
            let block_frames = tail
                .first()
                .map(|value| value.parse())
                .transpose()?
                .unwrap_or(128);
            timing_case::speech_voice::run_song(
                read_case(Path::new(path))?,
                Destination::Pcm {
                    wave: Path::new(wave),
                    trace: Some(Path::new(trace)),
                    block_frames,
                },
                Some(Path::new(telemetry)),
            )?;
        }
        [command, path, wave, trace, tail @ ..] if command == "render-pcm" && tail.len() <= 1 => {
            let block_frames = tail
                .first()
                .map(|value| value.parse::<usize>())
                .transpose()?
                .unwrap_or(128);
            run_case(
                Path::new(path),
                Destination::Pcm {
                    wave: Path::new(wave),
                    trace: (trace != "--no-trace").then(|| Path::new(trace)),
                    block_frames,
                },
            )?;
        }
        _ => return Err(USAGE.into()),
    }
    Ok(())
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("エラー: {error}");
            ExitCode::FAILURE
        }
    }
}
