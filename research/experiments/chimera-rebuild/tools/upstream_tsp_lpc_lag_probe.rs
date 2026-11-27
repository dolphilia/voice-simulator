//! 固定推定器とラグ窓の定数だけを変えた推定器を、同じ窓で観測する。

use chimera::analysis::lpc::{FormantOpts, autocorr, estimate_formants, levinson, lpc_envelope_db, poly_roots};
use chimera::math::{PI, cos, exp, pow};
use serde_json::{Value, json};
use std::error::Error;

mod math {
    pub use chimera::math::*;
}

mod lpc_zero_window;

fn main() -> Result<(), Box<dyn Error>> {
    let input = std::env::args().nth(1).ok_or("窓の入力JSONが必要です")?;
    let (fs, order, frame, grid): (f64, usize, Vec<f64>, Vec<f64>) =
        serde_json::from_reader(std::fs::File::open(input)?)?;
    let shaped: Vec<f64> = frame.iter().enumerate().map(|(i, &sample)| {
        let previous = if i == 0 { 0.0 } else { frame[i - 1] };
        let hamming = 0.54 - 0.46 * cos((2.0 * PI * i as f64) / (frame.len() as f64 - 1.0));
        (sample - 0.97 * previous) * hamming
    }).collect();
    let raw = autocorr(&shaped, order);
    let fixed = estimate_formants(&frame, fs, FormantOpts {
        order: Some(order), min_freq: Some(150.0), max_bw: Some(600.0),
        ..Default::default()
    }).iter().map(|p| [p.freq, p.bw]).collect::<Vec<_>>();
    let zero = lpc_zero_window::estimate_formants(&frame, fs, lpc_zero_window::FormantOpts {
        order: Some(order), min_freq: Some(150.0), max_bw: Some(600.0),
        ..Default::default()
    }).iter().map(|p| [p.freq, p.bw]).collect::<Vec<_>>();
    let variants: Vec<_> = [(40.0, fixed), (0.0, zero)].into_iter().map(|(width, poles)| {
        let weighted: Vec<_> = raw.iter().enumerate().map(|(lag, &r)| {
            r * exp(-0.5 * pow((2.0 * PI * width * lag as f64) / fs, 2.0))
        }).collect();
        let lpc = levinson(&weighted, order);
        let (real, imaginary) = poly_roots(&lpc.a, 400);
        let roots: Vec<_> = real.into_iter().zip(imaginary).collect();
        let curve = if width == 0.0 {
            lpc_zero_window::lpc_envelope_db(&lpc.a, lpc.err, fs, &grid)
        } else {
            lpc_envelope_db(&lpc.a, lpc.err, fs, &grid)
        };
        json!({
            "lag_window_hz": width, "weighted_autocorrelation": weighted,
            "coefficients": lpc.a, "prediction_error": lpc.err,
            "roots": roots, "poles": poles, "lpc_envelope_db": curve
        })
    }).collect();
    let output: Value = json!({"shaped": shaped, "autocorrelation": raw, "variants": variants});
    serde_json::to_writer(std::io::stdout().lock(), &output)?;
    Ok(())
}
