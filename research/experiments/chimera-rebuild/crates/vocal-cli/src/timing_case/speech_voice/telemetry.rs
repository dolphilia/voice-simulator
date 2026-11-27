//! CHTL v1の採取順と配列はCHIMERAの `TeleRecorder` に対応する（Jameson Hodge、MIT）。

use std::{
    error::Error,
    fs::File,
    io::{BufWriter, Write},
    path::Path,
};
use vocal_core::{
    anatomy::BodyMix,
    articulators::{ARTICULATOR_COUNT, Articulator},
    voice::{ArticulatedVoice, VoiceSample},
};

const HOP: usize = 768;
const SCOPE_POINTS: usize = 32;
const HISTORY: usize = 4096;
const FALLBACK_SPAN: usize = 1024;

pub(super) struct Recorder {
    rate: u32,
    pharynx: usize,
    oral: usize,
    body: BodyMix,
    control_block: usize,
    flow_weight: f64,
    internal_frames: usize,
    output_frames: usize,
    pressure_squares: Vec<f64>,
    pressure_frames: usize,
    flow: Vec<f64>,
    pcm_squares: f64,
    scope: Scope,
    data: Vec<f32>,
}

impl Recorder {
    pub(super) fn new(
        voice: &ArticulatedVoice,
        rate: u32,
        control_block: usize,
        body: BodyMix,
    ) -> Result<Self, &'static str> {
        let [pharynx, oral] = voice.airway().tract_section_counts();
        let mut out = Self {
            rate,
            pharynx,
            oral,
            body,
            control_block,
            flow_weight: 1.0 - (-64.0 / f64::from(rate) / 0.03).exp(),
            internal_frames: 0,
            output_frames: 0,
            pressure_squares: vec![0.0; pharynx + oral],
            pressure_frames: 0,
            flow: vec![0.0; pharynx + oral],
            pcm_squares: 0.0,
            scope: Scope::new(),
            data: Vec::new(),
        };
        out.snapshot(voice, None)?;
        Ok(out)
    }

    pub(super) fn before_internal(&mut self, voice: &ArticulatedVoice) {
        if self.internal_frames.is_multiple_of(self.control_block) {
            for (filtered, [_, flow]) in self.flow.iter_mut().zip(voice.airway().tract_acoustics())
            {
                *filtered += self.flow_weight * (flow - *filtered);
            }
        }
    }

    pub(super) fn after_internal(&mut self, voice: &ArticulatedVoice) {
        self.internal_frames += 1;
        if self.internal_frames.is_multiple_of(4) {
            for (sum, [pressure, _]) in self
                .pressure_squares
                .iter_mut()
                .zip(voice.airway().tract_acoustics())
            {
                *sum += pressure * pressure;
            }
            self.pressure_frames += 1;
        }
    }

    pub(super) fn output(
        &mut self,
        voice: &ArticulatedVoice,
        sample: &VoiceSample,
        pcm: f32,
    ) -> Result<(), &'static str> {
        self.scope.push(sample);
        let pcm = f64::from(pcm);
        self.pcm_squares += pcm * pcm;
        self.output_frames += 1;
        if self.output_frames.is_multiple_of(HOP) {
            self.snapshot(voice, Some(sample))?;
        }
        Ok(())
    }

    fn snapshot(
        &mut self,
        voice: &ArticulatedVoice,
        sample: Option<&VoiceSample>,
    ) -> Result<(), &'static str> {
        let airway = voice.airway();
        if airway.tract_section_counts() != [self.pharynx, self.oral] {
            return Err("テレメトリの採取中に声道セルの数が変わりました");
        }
        let ph_len = airway
            .tract_sections()
            .take(self.pharynx)
            .map(|cell| cell.length_cm)
            .sum();
        let or_len = airway
            .tract_sections()
            .skip(self.pharynx)
            .map(|cell| cell.length_cm)
            .sum();
        let mut noise = (0.0, -1.0);
        let network = &airway.network;
        for index in 0.. {
            let Some((level, spec)) = network.noise_level(index).zip(network.noise_spec(index))
            else {
                break;
            };
            if level > noise.0 {
                noise = (level, spec.source as f64);
            }
        }
        let voicing = sample.map_or(0.0, |s| s.glottis.voicing);
        let start = self.data.len();
        self.data.extend(
            [
                ph_len,
                or_len,
                network.port_area(airway.velum_port).unwrap_or_default(),
                sample.map_or_else(|| voice.smoothed_pitch_hz(), |s| s.glottis.f0_hz),
                voicing,
                sample.map_or(0.0, |s| s.breath.base_pressure_dyn_cm2 / 980.665),
                (self.pcm_squares / HOP as f64).sqrt(),
                noise.0,
                noise.1,
                sample.map_or(0.0, |s| s.breath.gate),
                self.output_frames as f64 / f64::from(self.rate),
            ]
            .map(|value| value as f32),
        );
        self.data
            .extend(Articulator::ALL.map(|axis| voice.articulators().state(axis).position as f32));
        self.data
            .extend(airway.tract_sections().map(|cell| cell.area_cm2 as f32));
        let count = self.pressure_frames.max(1) as f64;
        self.data.extend(
            self.pressure_squares
                .iter()
                .map(|sum| (sum / count).sqrt() as f32),
        );
        self.data.extend(self.flow.iter().map(|&flow| flow as f32));
        self.scope.append(&mut self.data, voicing);
        if self.data[start..].iter().any(|value| !value.is_finite()) {
            return Err("テレメトリに非有限値があります");
        }
        self.pressure_squares.fill(0.0);
        self.pressure_frames = 0;
        self.pcm_squares = 0.0;
        Ok(())
    }

    pub(super) fn write(self, path: &Path) -> Result<(), Box<dyn Error>> {
        let width = 11 + ARTICULATOR_COUNT + 3 * (self.pharynx + self.oral) + 2 * SCOPE_POINTS;
        let rows = self.output_frames / HOP + 1;
        if self.data.len() != rows * width {
            return Err("テレメトリの行数と列数が一致しません".into());
        }
        let mut file = BufWriter::new(File::create_new(path)?);
        file.write_all(b"CHTL")?;
        for value in [
            1,
            self.rate as usize,
            HOP,
            rows,
            width,
            ARTICULATOR_COUNT,
            self.pharynx,
            self.oral,
            SCOPE_POINTS,
        ] {
            file.write_all(&u32::try_from(value)?.to_le_bytes())?;
        }
        for value in self
            .body
            .coefficients()
            .map(|value| value as f32)
            .into_iter()
            .chain(self.data)
        {
            file.write_all(&value.to_le_bytes())?;
        }
        file.flush()?;
        Ok(())
    }
}

struct Scope {
    history: Vec<[f32; 2]>,
    position: usize,
    phase: f64,
    boundaries: [usize; 3],
    cycles: usize,
}

impl Scope {
    fn new() -> Self {
        Self {
            history: vec![[0.0; 2]; HISTORY],
            position: 0,
            phase: 0.0,
            boundaries: [0; 3],
            cycles: 0,
        }
    }

    fn push(&mut self, sample: &VoiceSample) {
        self.history[self.position] = [
            sample.glottis.area_cm2 as f32,
            sample.glottal_flow_cm3_s as f32,
        ];
        if sample.glottis.phase < self.phase {
            self.boundaries.rotate_left(1);
            self.boundaries[2] = self.position;
            self.cycles += 1;
        }
        self.phase = sample.glottis.phase;
        self.position = (self.position + 1) % HISTORY;
    }

    fn append(&self, data: &mut Vec<f32>, voicing: f64) {
        let width = (HISTORY + self.boundaries[2] - self.boundaries[0]) % HISTORY;
        let (start, span) =
            if self.cycles >= 3 && voicing > 0.2 && (9..HISTORY / 2).contains(&width) {
                (self.boundaries[0], width)
            } else {
                (
                    (HISTORY + self.position - FALLBACK_SPAN) % HISTORY,
                    FALLBACK_SPAN,
                )
            };
        for channel in 0..2 {
            data.extend(
                (0..SCOPE_POINTS)
                    .map(|i| self.history[(start + i * span / SCOPE_POINTS) % HISTORY][channel]),
            );
        }
    }
}
