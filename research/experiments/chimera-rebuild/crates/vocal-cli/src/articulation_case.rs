//! 調音器の制御フレームを再現して位置・速度・目標を記録する。

mod tract;
mod voiced;

use crate::geometry_case::{BodyInput, Pose, voice::Settings as VoiceSettings};
use crate::network_case::Destination;
use serde::Deserialize;
use serde_json::{Value, json};
use std::collections::BTreeMap;
use std::error::Error;
use std::fs::File;
use std::io::{self, BufWriter, Write};
use std::num::NonZeroUsize;
use std::path::Path;
use vocal_core::anatomy::BodyMix;
use vocal_core::articulators::{ARTICULATOR_COUNT, Articulator, ArticulatorBank, BlendedTarget};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Case {
    id: String,
    upstream_revision: String,
    hypothesis: String,
    body: BodyInput,
    posture: Pose,
    articulators: Settings,
    area_control: Option<tract::Settings>,
    voice: Option<VoiceSettings>,
    glottal_pressure_override: Option<PressureOverrideInput>,
    measurement: Measurement,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PressureOverrideInput {
    start_sample: usize,
    values_dyn_cm2: Vec<String>,
}

struct PressureOverride {
    start_sample: usize,
    values_dyn_cm2: Vec<f64>,
}

impl PressureOverrideInput {
    fn validate(self, total_samples: usize) -> Result<PressureOverride, &'static str> {
        let end = self.start_sample.checked_add(self.values_dyn_cm2.len());
        if self.values_dyn_cm2.is_empty() || end.is_none_or(|end| end > total_samples) {
            return Err("圧差の入力系列は内部サンプルの描画区間内に指定してください");
        }
        // 計測CSV由来の十進表記をRustの f64 パーサーで丸め、サンプルを再現する。
        let values_dyn_cm2 = self
            .values_dyn_cm2
            .iter()
            .map(|value| {
                value
                    .parse::<f64>()
                    .ok()
                    .filter(|value| value.is_finite())
                    .ok_or("圧差の入力系列には有限の十進文字列を指定してください")
            })
            .collect::<Result<Vec<_>, _>>()?;
        Ok(PressureOverride {
            start_sample: self.start_sample,
            values_dyn_cm2,
        })
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Settings {
    sample_rate_hz: u32,
    control_block_samples: usize,
    base_weight: f64,
    tip_free: bool,
    #[serde(default)]
    events: Vec<Event>,
}

#[derive(Deserialize)]
struct Measurement {
    frames: usize,
    #[serde(default)]
    voiced_tract_oral_cells: Vec<usize>,
    #[serde(default)]
    glottal_pressure: bool,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Event {
    frame: usize,
    gate: Option<f64>,
    f0_hz: Option<f64>,
    body: Option<BodyInput>,
    #[serde(default)]
    targets: BTreeMap<String, f64>,
    #[serde(default)]
    speeds: BTreeMap<String, f64>,
    tip_free: Option<bool>,
    blend: Option<BTreeMap<String, Blend>>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Blend {
    value: f64,
    weight: f64,
    speed: f64,
}

struct FrameChanges {
    frame: usize,
    gate: Option<f64>,
    f0_hz: Option<f64>,
    body: Option<BodyMix>,
    targets: Vec<(Articulator, f64)>,
    speeds: Vec<(Articulator, f64)>,
    tip_free: Option<bool>,
    blend: Option<[BlendedTarget; ARTICULATOR_COUNT]>,
}

impl TryFrom<Event> for FrameChanges {
    type Error = String;

    fn try_from(event: Event) -> Result<Self, String> {
        if event.gate.is_some_and(|gate| !(0.0..=1.5).contains(&gate)) {
            return Err("呼気目標は0〜1.5の範囲で指定してください".into());
        }
        let targets = event
            .targets
            .into_iter()
            .map(|(name, value)| Ok((parse_key(&name)?, value)))
            .collect::<Result<Vec<_>, String>>()?;
        let speeds = event
            .speeds
            .into_iter()
            .map(|(name, speed)| {
                if !speed.is_finite() || speed < 0.0 {
                    return Err(format!(
                        "{name} の速度倍率には有限の非負値を指定してください"
                    ));
                }
                Ok((parse_key(&name)?, speed))
            })
            .collect::<Result<Vec<_>, String>>()?;
        let blend = event
            .blend
            .map(|input| {
                let mut values = [BlendedTarget::default(); ARTICULATOR_COUNT];
                for (name, setting) in input {
                    let key = parse_key(&name)?;
                    let value = BlendedTarget {
                        value: setting.value,
                        weight: setting.weight,
                        speed: setting.speed,
                    };
                    value.validate()?;
                    values[key.index()] = value;
                }
                Ok::<_, String>(values)
            })
            .transpose()?;
        Ok(Self {
            frame: event.frame,
            gate: event.gate,
            f0_hz: event.f0_hz,
            body: event.body.map(BodyMix::from),
            targets,
            speeds,
            tip_free: event.tip_free,
            blend,
        })
    }
}

impl FrameChanges {
    fn apply(
        self,
        bank: &mut ArticulatorBank,
        blend: &mut [BlendedTarget; ARTICULATOR_COUNT],
    ) -> Result<(), &'static str> {
        for (key, value) in self.targets {
            bank.set_target(key, value);
        }
        for (key, value) in self.speeds {
            bank.set_speed(key, value)?;
        }
        if let Some(free) = self.tip_free {
            bank.set_tip_free(free);
        }
        if let Some(values) = self.blend {
            *blend = values;
        }
        Ok(())
    }
}

fn parse_key(name: &str) -> Result<Articulator, String> {
    Articulator::from_name(name).ok_or_else(|| format!("未知の調音器があります ({name})"))
}

struct Simulation {
    body: BodyMix,
    oral_cells: Option<NonZeroUsize>,
    pressure_override: Option<PressureOverride>,
    observe_pressure: bool,
    bank: ArticulatorBank,
    frames: usize,
    block: usize,
    dt: f64,
    base_weight: f64,
    events: Vec<FrameChanges>,
}

impl Simulation {
    fn run_frames(
        mut self,
        mut observe: impl FnMut(usize, &mut ArticulatorBank) -> Result<(), Box<dyn Error>>,
    ) -> Result<(), Box<dyn Error>> {
        let mut blend = [BlendedTarget::default(); ARTICULATOR_COUNT];
        let mut events = self.events.into_iter().peekable();
        for frame in 0..self.frames {
            if events.peek().is_some_and(|event| event.frame == frame) {
                events
                    .next()
                    .expect("このフレームのイベント")
                    .apply(&mut self.bank, &mut blend)?;
            }
            self.bank.step(self.dt, &blend, self.base_weight)?;
            observe(frame, &mut self.bank)?;
        }
        Ok(())
    }

    fn render(self, path: &Path) -> Result<(), Box<dyn Error>> {
        let mut out = BufWriter::new(File::create_new(path)?);
        writeln!(
            out,
            concat!(
                "frame,internal_start_sample,time_s,articulator,position,velocity_per_s,",
                "target,effective,base_speed,applied_speed,tip_free",
            )
        )?;
        let (block, dt) = (self.block, self.dt);
        self.run_frames(|frame, bank| {
            let start = frame * block;
            let time = (frame + 1) as f64 * dt;
            for key in Articulator::ALL {
                let state = bank.state(key);
                writeln!(
                    out,
                    "{frame},{start},{time},{},{},{},{},{},{},{},{}",
                    key.name(),
                    state.position,
                    state.velocity,
                    state.target,
                    state.effective,
                    state.base_speed,
                    state.applied_speed,
                    u8::from(bank.tip_free())
                )?;
            }
            Ok(())
        })?;
        out.flush()?;
        Ok(())
    }
}

pub(super) fn run(input: Value, destination: Destination<'_>) -> Result<(), Box<dyn Error>> {
    let case = Case::deserialize(&input)?;
    let settings = case.articulators;
    let frames = case.measurement.frames;
    if case.id.is_empty()
        || case.upstream_revision.is_empty()
        || case.hypothesis.is_empty()
        || frames == 0
        || settings.sample_rate_hz == 0
        || settings.control_block_samples == 0
        || frames.checked_mul(settings.control_block_samples).is_none()
        || !settings.base_weight.is_finite()
        || settings.base_weight < 0.0
    {
        return Err(
            "ケースID、上流版、仮説、計測区間、制御周期、基準重みを確認してください".into(),
        );
    }
    if settings.events.iter().any(|event| event.frame >= frames)
        || settings
            .events
            .windows(2)
            .any(|pair| pair[0].frame >= pair[1].frame)
    {
        return Err("イベントのフレームは計測範囲内で重複のない昇順に指定してください".into());
    }
    if settings.events.iter().any(|event| {
        event.f0_hz.is_some_and(|f0| {
            case.voice.is_none() || !(0.0 < f0 && f0 < f64::from(settings.sample_rate_hz) * 0.5)
        })
    }) {
        return Err("音高イベントには音源設定と内部ナイキスト周波数未満の正のF0が必要です".into());
    }
    let events = settings
        .events
        .into_iter()
        .map(FrameChanges::try_from)
        .collect::<Result<Vec<_>, _>>()?;
    if case.voice.is_none() && events.iter().any(|event| event.gate.is_some()) {
        return Err("調音イベントの呼気目標を使うには音源設定が必要です".into());
    }
    if case.voice.is_none() && events.iter().any(|event| event.body.is_some()) {
        return Err("発声中の体型を変更するには音源設定が必要です".into());
    }
    let observed_oral_cells = &case.measurement.voiced_tract_oral_cells;
    if !observed_oral_cells.is_empty() && case.voice.is_none() {
        return Err("発声中の口腔セルを計測するには音源設定が必要です".into());
    }
    if case.voice.is_none()
        && (case.glottal_pressure_override.is_some() || case.measurement.glottal_pressure)
    {
        return Err("声門の圧差を指定または観測するには音源設定が必要です".into());
    }
    let pressure_override = case
        .glottal_pressure_override
        .map(|input| input.validate(frames * settings.control_block_samples))
        .transpose()?;
    let bank = ArticulatorBank::new(case.posture.into(), settings.tip_free)?;
    let dt = settings.control_block_samples as f64 / f64::from(settings.sample_rate_hz);
    let simulation = Simulation {
        body: case.body.into(),
        oral_cells: case
            .area_control
            .as_ref()
            .and_then(|setting| setting.oral_cells),
        bank,
        pressure_override,
        observe_pressure: case.measurement.glottal_pressure,
        frames,
        block: settings.control_block_samples,
        dt,
        base_weight: settings.base_weight,
        events,
    };
    if case.voice.is_some() && case.area_control.as_ref().is_some_and(|cfg| cfg.acoustics) {
        return Err("発声と形状変化だけで駆動する音響計測は同時に指定できません".into());
    }
    let project_contacts = case
        .area_control
        .as_ref()
        .is_none_or(|cfg| cfg.project_contacts);
    match destination {
        Destination::Inspect => {
            let specs = Articulator::ALL.map(|key| {
                let bounds = key.spec();
                json!({
                    "articulator": key.name(), "unit": bounds.unit, "minimum": bounds.minimum,
                    "maximum": bounds.maximum, "natural_frequency_hz": bounds.natural_frequency_hz,
                    "initial_position": simulation.bank.state(key).position,
                })
            });
            let mut result = json!({
                "case": input, "frames": frames, "control_seconds": dt, "articulators": specs,
            });
            if let Some(voice) = case.voice {
                result["voice"] =
                    voiced::inspect(simulation, settings.sample_rate_hz, project_contacts, voice)?;
            }
            let mut stream = io::stdout().lock();
            serde_json::to_writer_pretty(&mut stream, &result)?;
            writeln!(stream)?;
            Ok(())
        }
        destination => {
            if let Some(voice) = case.voice {
                return voiced::render(
                    simulation,
                    settings.sample_rate_hz,
                    project_contacts,
                    voice,
                    destination,
                    observed_oral_cells,
                );
            }
            match destination {
                Destination::Trace(path) => match case.area_control {
                    Some(config) => {
                        tract::render(simulation, settings.sample_rate_hz, config, path)
                    }
                    None => simulation.render(path),
                },
                Destination::Pcm { .. } => {
                    Err("調音軌跡ケースは render でCSVへ出力してください".into())
                }
                Destination::Inspect => unreachable!(),
            }
        }
    }
}
