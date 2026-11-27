//! 固定上流版のDecimatorと出力式を使い、観測用に状態を出力する。

use chimera::airway::decimator::Decimator;
use chimera::math::{PI, exp, tanh};
use std::error::Error;
use std::fs::File;
use std::io::{self, BufRead, BufReader, BufWriter, Write};

fn main() -> Result<(), Box<dyn Error>> {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    let [factor, rate, gain, signal] = args.as_slice() else {
        return Err("係数、出力レート、ゲイン、放射系列を指定してください".into());
    };
    let factor: usize = factor.parse()?;
    let rate: f64 = rate.parse()?;
    let gain: f64 = gain.parse()?;
    let mut decimator = Decimator::new(factor);
    let mut old_x = 0.0;
    let mut old_y = 0.0;
    let dc = exp((-2.0 * PI * 25.0) / rate);
    let mut envelope = 0.0;
    let mut hold = 0;
    let hold_length = (0.025 * rate).round() as usize;
    let release = exp(-1.0 / (0.2 * rate));
    let mut output = BufWriter::new(io::stdout().lock());
    writeln!(
        output,
        "frame,internal_sample,decimated,dc_removed,limiter_envelope,hold_frames,pcm_f32"
    )?;
    for (i, line) in BufReader::new(File::open(signal)?).lines().enumerate() {
        if !decimator.push(line?.parse()?) {
            continue;
        }
        let x = gain * decimator.value;
        let filtered = x - old_x + dc * old_y;
        old_x = x;
        old_y = filtered;
        let magnitude = filtered.abs();
        if magnitude >= envelope {
            envelope = magnitude;
            hold = hold_length;
        } else if hold > 0 {
            hold -= 1;
        } else {
            envelope *= release;
        }
        let limited = if envelope > 0.75 {
            filtered * (0.75 / envelope)
        } else {
            filtered
        };
        let pcm = if limited.abs() > 0.85 {
            limited.signum() * (0.85 + 0.15 * tanh((limited.abs() - 0.85) / 0.15))
        } else {
            limited
        } as f32;
        let frame = i / factor;
        writeln!(
            output,
            "{frame},{i},{},{filtered},{envelope},{hold},{pcm}",
            decimator.value
        )?;
    }
    output.flush()?;
    Ok(())
}
