//! 通常の英語発話計画を研究版コアに渡し、音源と放射を内部レートで観測する。

mod tsp_fine_trace;
#[cfg(tsp_tract_snapshot)]
mod tsp_transfer_request;
#[cfg(tsp_tract_snapshot)]
mod candidate_tsp_tract_snapshot;

use serde_json::Value;
use std::{
    error::Error,
    fs::{self, File},
    io::{BufWriter, Write},
};
use vocal_core::{
    anatomy::{Articulation, BodyMix, BodyName, Point},
    articulators::Articulator,
    output::OutputStage,
    phonetics::english::{self, English},
    voice::{ArticulatedVoice, FixedVoiceSettings},
};

fn required_number(object: &Value, key: &str) -> Result<f64, String> {
    object[key]
        .as_f64()
        .ok_or_else(|| format!("数値の設定がありません ({key})"))
}

fn posture(pose: &Value) -> Result<Articulation, Box<dyn Error>> {
    let point = |key: &str| -> Result<Point, Box<dyn Error>> {
        let [x, y]: [f64; 2] = serde_json::from_value(pose[key].clone())?;
        Ok(Point::new(x, y))
    };
    let number = |key| required_number(pose, key);
    Ok(Articulation {
        jaw_cm: number("jaw_cm")?,
        tongue_body_cm: point("tongue_body_cm")?,
        tongue_tip_cm: point("tongue_tip_cm")?,
        tongue_root_cm: number("tongue_root_cm")?,
        tip_curl: number("tip_curl")?,
        dorsum: number("dorsum")?,
        lip_aperture_cm: number("lip_aperture_cm")?,
        lip_protrusion_cm: number("lip_protrusion_cm")?,
        lip_spread: number("lip_spread")?,
        labiodental: number("labiodental")?,
        velum_cm2: number("velum_cm2")?,
        larynx_cm: number("larynx_cm")?,
        lateral: pose["lateral"].as_f64().unwrap_or_default(),
        epilarynx: pose["epilarynx"].as_f64().unwrap_or_default(),
        ventricular: pose["ventricular"].as_f64().unwrap_or_default(),
    })
}

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    #[cfg(tsp_tract_snapshot)]
    let (snapshot, args) = candidate_tsp_tract_snapshot::options(&args)?;
    #[cfg(not(tsp_tract_snapshot))]
    let args = args.as_slice();
    let (args, amplitude_path) = match args {
        [args @ .., amplitude_path] if args.len() == 8 => (args, Some(amplitude_path)),
        args => (args, None),
    };
    let [
        case,
        dictionary,
        count,
        initial_f0,
        base_f0,
        trace,
        wav,
        output,
    ] = args
    else {
        return Err(
            "発話ケース、辞書、観測フレーム数、初期と基準のF0、各保存先を指定してください".into(),
        );
    };
    let input: Value = serde_json::from_slice(&fs::read(case)?)?;
    let spec = &input["speech_voice"];
    let voice = &spec["voice"];
    let body: BodyMix = serde_json::from_value::<BodyName>(spec["body"].clone())?.into();
    let dictionary = fs::read_to_string(dictionary)?;
    let lexicon = English::with_dictionary(&dictionary);
    let speech = &spec["input"];
    let speaking_f0: f64 = base_f0.parse()?;
    let (plan, gestures) = english::plan_voice_with_body(
        &lexicon,
        speech["text"].as_str().ok_or("本文がありません")?,
        speech["start_seconds"]
            .as_f64()
            .unwrap_or(english::START_SECONDS),
        speech["rate"].as_f64().unwrap_or(1.0),
        speaking_f0,
        body,
    )?;
    let count: usize = count.parse()?;
    let internal_rate = serde_json::from_value(spec["internal_sample_rate_hz"].clone())?;
    let output_rate: u32 = serde_json::from_value(voice["output_sample_rate_hz"].clone())?;
    let frames = (plan.render_end_seconds * f64::from(output_rate)).round() as usize;
    #[cfg(tsp_tract_snapshot)]
    if snapshot.0.completed_frames > frames {
        return Err("観測時刻が発話の範囲外です".into());
    }
    let gain = required_number(voice, "output_gain")?;
    let mut stage = OutputStage::new(internal_rate, output_rate, gain)?;
    if count > frames || stage.factor() != 2 {
        return Err("観測範囲または内部レートが登録条件を満たしません".into());
    }
    let mut spoken = ArticulatedVoice::for_speech_with_body(
        internal_rate,
        64 * stage.factor(),
        posture(&spec["posture"])?,
        FixedVoiceSettings {
            pressure_cm_h2o: required_number(voice, "pressure_cm_h2o")?,
            gate: required_number(voice, "gate")?,
            f0_hz: initial_f0.parse()?,
            breathiness: required_number(voice, "breathiness")?,
            tension: required_number(voice, "tension")?,
        },
        body,
    )?;
    spoken.set_base_pitch(speaking_f0)?;
    let variation = &spec["source_variation"];
    if let Some(cents) = variation["pitch_drift_cents"].as_f64() {
        spoken.set_pitch_drift_cents(cents)?;
    }
    if let Some(amount) = variation["period_jitter"].as_f64() {
        spoken.set_period_jitter(amount)?;
    }
    if let Some(amount) = variation["amplitude_shimmer"].as_f64() {
        spoken.set_amplitude_shimmer(amount)?;
    }
    spoken.enable_turbulence(required_number(&spec["turbulence"], "scale")?)?;
    spoken.set_score(gestures)?;
    #[cfg(tsp_tract_snapshot)]
    if snapshot.0.completed_frames == 0 {
        candidate_tsp_tract_snapshot::write(&spoken, &snapshot.0, snapshot.1)?;
    }

    let mut trace = BufWriter::new(File::create_new(trace)?);
    let mut pcm = BufWriter::new(File::create_new(wav)?);
    let mut output = BufWriter::new(File::create_new(output)?);
    let mut amplitude = amplitude_path
        .map(File::create_new)
        .transpose()?
        .map(BufWriter::new);
    for frame in 0..frames {
        let mut radiation_pair = [0.0; 2];
        let mut source_pair = [[0.0; 13]; 2];
        let mut amplitude_pair = [0.0; 2];
        let (out, ()) = stage.render_frame(|| {
            let sample = spoken.step()?;
            let radiation = sample.radiation.radiation_flow_derivative_cm3_s2;
            if frame < count {
                let tip = spoken
                    .articulators()
                    .state(Articulator::TongueTipY)
                    .position;
                if amplitude.is_some() {
                    amplitude_pair = [amplitude_pair[1], sample.glottis.cycle_amplitude_scale];
                }
                radiation_pair = [radiation_pair[1], radiation];
                source_pair = [
                    source_pair[1],
                    [
                        tip,
                        sample.breath.gate,
                        sample.glottal_input_pressure_dyn_cm2,
                        sample.glottis.f0_hz,
                        sample.glottis.phase,
                        sample.glottis.area_cm2,
                        sample.glottis.voicing,
                        sample.glottal_flow_cm3_s,
                        sample.lip_flow_cm3_s,
                        sample.nose_flow_cm3_s,
                        sample.radiation.wall_radiation_flow_cm3_s,
                        sample.radiation.radiation_flow_cm3_s,
                        radiation,
                    ],
                ];
            }
            Ok((radiation, ()))
        })?;
        pcm.write_all(&out.pcm.to_le_bytes())?;
        #[cfg(tsp_tract_snapshot)]
        if frame + 1 == snapshot.0.completed_frames {
            candidate_tsp_tract_snapshot::write(&spoken, &snapshot.0, snapshot.1)?;
        }
        if frame < count {
            for row in &source_pair {
                tsp_fine_trace::write_row(&mut trace, row)?;
            }
            if let Some(amplitude) = &mut amplitude {
                tsp_fine_trace::write_row(amplitude, &amplitude_pair)?;
            }
            tsp_fine_trace::write_row(&mut output, &radiation_pair)?;
            tsp_fine_trace::write_row(
                &mut output,
                &[
                    out.decimated,
                    out.decimated * gain,
                    out.dc_removed,
                    out.envelope,
                    out.hold_frames as f64,
                ],
            )?;
        }
    }
    output.flush()?;
    trace.flush()?;
    pcm.flush()?;
    if let Some(amplitude) = &mut amplitude {
        amplitude.flush()?;
    }
    Ok(())
}
