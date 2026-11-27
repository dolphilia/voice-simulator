//! 公開LPC推定器のプリエンファシス設定を比較し、途中の値を記録する。

use chimera::analysis::lpc::{FormantOpts, autocorr, estimate_formants, levinson, lpc_envelope_db, poly_roots};
use chimera::math::{PI, cos, exp, pow};
use serde_json::{Value, json};
use std::error::Error;

fn observe(
    frame: &[f64],
    fs: f64,
    order: usize,
    grid: &[f64],
    pre_emph: Option<f64>,
    (min_frequency, max_bandwidth): (f64, f64),
) -> Value {
    let pre = pre_emph.unwrap_or(0.97);
    let emphasized: Vec<_> = frame.iter().enumerate().map(|(i, &sample)| {
        sample - if i > 0 { pre * frame[i - 1] } else { 0.0 }
    }).collect();
    let shaped: Vec<_> = emphasized.iter().enumerate().map(|(i, &sample)| {
        sample * (0.54 - 0.46 * cos((2.0 * PI * i as f64) / (frame.len() as f64 - 1.0)))
    }).collect();
    let raw = autocorr(&shaped, order);
    let mut weighted = raw.clone();
    for (k, r) in weighted.iter_mut().enumerate().skip(1) {
        *r *= exp(-0.5 * pow((2.0 * PI * 40.0 * k as f64) / fs, 2.0));
    }
    let lpc = levinson(&weighted, order);
    let (re, im) = poly_roots(&lpc.a, 400);
    let roots: Vec<_> = re.into_iter().zip(im).collect();
    let opts = FormantOpts {
        order: Some(order), pre_emph, min_freq: Some(min_frequency), max_bw: Some(max_bandwidth)
    };
    let poles: Vec<_> = estimate_formants(frame, fs, opts)
        .iter().map(|p| [p.freq, p.bw]).collect();
    json!({
        "pre_emphasis_option": pre_emph, "pre_emphasis_coefficient": pre,
        "emphasized": emphasized, "shaped": shaped, "autocorrelation": raw,
        "weighted_autocorrelation": weighted, "coefficients": lpc.a, "prediction_error": lpc.err,
        "roots": roots, "poles": poles, "lpc_envelope_db": lpc_envelope_db(&lpc.a, lpc.err, fs, grid)
    })
}

fn main() -> Result<(), Box<dyn Error>> {
    let mut args = std::env::args().skip(1);
    let input = args.next().ok_or("窓の入力JSONが必要です")?;
    let (fs, order, frame, grid): (f64, usize, Vec<f64>, Vec<f64>) =
        serde_json::from_reader(std::fs::File::open(input)?)?;
    let options: Vec<Option<f64>> = match args.next() {
        Some(values) => serde_json::from_str(&values)?,
        None => vec![None, Some(0.0)],
    };
    let limits = args.next().as_deref().map(serde_json::from_str).transpose()?.unwrap_or((150.0, 600.0));
    let variants: Vec<_> = options.into_iter()
        .map(|pre| observe(&frame, fs, order, &grid, pre, limits))
        .collect();
    serde_json::to_writer(std::io::stdout().lock(), &variants)?;
    Ok(())
}
