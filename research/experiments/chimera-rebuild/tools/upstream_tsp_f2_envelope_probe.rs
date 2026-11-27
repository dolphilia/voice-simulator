//! 固定版の推定器で、保存音声から切り出した同じ窓の極とLPC包絡を記録する。

use chimera::analysis::lpc::{FormantOpts, autocorr, estimate_formants, levinson, lpc_envelope_db, poly_roots};
use chimera::math::{PI, cos, exp, pow};
use serde_json::{Value, json};
use std::error::Error;

fn observe(frame: &[f64], frequencies: &[f64], order: usize, include_roots: bool) -> Value {
    // TSP経路と同じ条件で、係数と残差も取得する。
    const FS: f64 = 12_000.0;
    let windowed: Vec<f64> = frame.iter().enumerate().map(|(i, &sample)| {
        let previous = if i == 0 { 0.0 } else { frame[i - 1] };
        let hamming = 0.54 - 0.46 * cos((2.0 * PI * i as f64) / (frame.len() as f64 - 1.0));
        (sample - 0.97 * previous) * hamming
    }).collect();
    let mut corr = autocorr(&windowed, order);
    for (lag, r) in corr.iter_mut().enumerate().skip(1) {
        *r *= exp(-0.5 * pow((2.0 * PI * 40.0 * lag as f64) / FS, 2.0));
    }
    let lpc = levinson(&corr, order);
    let opts = FormantOpts {
        order: Some(order),
        min_freq: Some(150.0),
        max_bw: Some(600.0),
        ..Default::default()
    };
    let poles: Vec<_> = estimate_formants(frame, FS, opts)
        .iter().map(|p| [p.freq, p.bw]).collect();
    let mut result = json!({
        "poles": poles,
        "coefficients": lpc.a,
        "prediction_error": lpc.err,
        "lpc_envelope_db": lpc_envelope_db(&lpc.a, lpc.err, FS, frequencies)
    });
    if include_roots {
        // 公開推定器と同じ係数・反復数で帯域幅の選別前の根を採る。
        let (real, imaginary) = poly_roots(&lpc.a, 400);
        let roots: Vec<_> = real.into_iter().zip(imaginary).collect();
        result["roots"] = json!(roots);
    }
    result
}

fn main() -> Result<(), Box<dyn Error>> {
    let mut args = std::env::args().skip(1);
    let path = args.next().ok_or("窓の入力JSONが必要です")?;
    let (frequencies, frames): (Vec<f64>, Vec<Vec<f64>>) =
        serde_json::from_reader(std::fs::File::open(path)?)?;
    let mut args = args.peekable();
    let include_roots = args.peek().is_some_and(|arg| arg == "--roots");
    if include_roots {
        args.next();
    }
    let orders: Vec<usize> = args.map(|arg| arg.parse()).collect::<Result<_, _>>()?;
    if !orders.is_empty()
        && (orders.len() != frames.len() || orders.iter().any(|&p| p != 12 && p != 14))
    {
        return Err("各窓にLPCの次数12または14を指定してください".into());
    }
    let result: Vec<_> = frames.iter().enumerate().map(|(i, frame)| {
        observe(frame, &frequencies, orders.get(i).copied().unwrap_or(14), include_roots)
    }).collect();
    serde_json::to_writer(std::io::stdout().lock(), &result)?;
    Ok(())
}
