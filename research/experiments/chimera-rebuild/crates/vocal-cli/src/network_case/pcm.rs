//! 固定ネットワークをブロック単位でレンダーし、PCMと観測値を保存する。

use serde::Deserialize;
use std::error::Error;
use std::fs::File;
use std::io::{self, BufWriter, Write};
use std::path::Path;
use vocal_core::output::{OutputFrame, OutputStage};

#[derive(Clone, Copy, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Settings {
    pub(super) sample_rate_hz: u32,
    pub(super) gain: f64,
}

pub(crate) fn write(
    mut next_radiation: impl FnMut() -> Result<f64, &'static str>,
    mut stage: OutputStage,
    rate: u32,
    internal_samples: usize,
    block_frames: usize,
    wave: &Path,
    trace: Option<&Path>,
) -> Result<(), Box<dyn Error>> {
    let factor = stage.factor();
    write_frames(
        || {
            stage
                .render_frame(|| next_radiation().map(|value| (value, ())))
                .map(|(frame, ())| frame)
        },
        rate,
        internal_samples / factor,
        factor,
        block_frames,
        wave,
        trace,
    )
}

pub(crate) fn write_frames(
    mut next_frame: impl FnMut() -> Result<OutputFrame, &'static str>,
    rate: u32,
    frames: usize,
    factor: usize,
    block_frames: usize,
    wave: &Path,
    trace: Option<&Path>,
) -> Result<(), Box<dyn Error>> {
    if block_frames == 0 {
        return Err("ブロックのフレーム数には正の値を指定してください".into());
    }
    let mut wave = create_wave(wave, rate, frames)?;
    let mut trace = trace.map(create).transpose()?;
    if let Some(trace) = &mut trace {
        writeln!(
            trace,
            "frame,internal_sample,decimated,dc_removed,limiter_envelope,hold_frames,pcm_f32"
        )?;
    }
    let block_frames = block_frames.min(frames.max(1));
    let mut buffer = vec![OutputFrame::default(); block_frames];
    for start in (0..frames).step_by(block_frames) {
        let active = block_frames.min(frames - start);
        for frame in &mut buffer[..active] {
            *frame = next_frame()?;
        }
        for (offset, output) in buffer[..active].iter().enumerate() {
            wave.write_all(&output.pcm.to_le_bytes())?;
            if let Some(trace) = &mut trace {
                let frame = start + offset;
                let internal_sample = (frame + 1) * factor - 1;
                writeln!(
                    trace,
                    "{frame},{internal_sample},{},{},{},{},{}",
                    output.decimated,
                    output.dc_removed,
                    output.envelope,
                    output.hold_frames,
                    output.pcm
                )?;
            }
        }
    }
    wave.flush()?;
    if let Some(trace) = &mut trace {
        trace.flush()?;
    }
    Ok(())
}

pub(crate) fn create_wave(
    path: &Path,
    rate: u32,
    frames: usize,
) -> Result<BufWriter<File>, Box<dyn Error>> {
    let bytes_per_second = rate
        .checked_mul(4)
        .ok_or("WAVのサンプルレートが範囲外です")?;
    let frame_count = u32::try_from(frames)?;
    let data_bytes = frame_count
        .checked_mul(4)
        .ok_or("WAVのデータが長すぎます")?;
    let riff_size = data_bytes
        .checked_add(50)
        .ok_or("WAVのデータが長すぎます")?;
    let mut wave = create(path)?;
    write_wave_header(
        &mut wave,
        rate,
        frame_count,
        bytes_per_second,
        data_bytes,
        riff_size,
    )?;
    Ok(wave)
}

fn create(path: &Path) -> Result<BufWriter<File>, String> {
    File::create_new(path)
        .map(BufWriter::new)
        .map_err(|error| format!("{}: 出力を作成できません ({error})", path.display()))
}

fn write_wave_header(
    output: &mut impl Write,
    rate: u32,
    frames: u32,
    byte_rate: u32,
    data: u32,
    size: u32,
) -> io::Result<()> {
    // IEEE浮動小数点のモノラルWAV。fmt拡張長は0、factにはフレーム数を入れる。
    output.write_all(b"RIFF")?;
    output.write_all(&size.to_le_bytes())?;
    output.write_all(b"WAVEfmt ")?;
    output.write_all(&18u32.to_le_bytes())?;
    output.write_all(&[3, 0, 1, 0])?;
    output.write_all(&rate.to_le_bytes())?;
    output.write_all(&byte_rate.to_le_bytes())?;
    output.write_all(&[4, 0, 32, 0, 0, 0])?;
    output.write_all(b"fact")?;
    output.write_all(&4u32.to_le_bytes())?;
    output.write_all(&frames.to_le_bytes())?;
    output.write_all(b"data")?;
    output.write_all(&data.to_le_bytes())
}
