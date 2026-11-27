//! 固定版または研究版の出力段の係数を返す。

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let rate = 48_000.0;
    #[cfg(tsp_candidate_output)]
    let (taps, pole, release) = (
        vocal_core::output::OutputStage::new(96_000, 48_000, 0.0)?.coefficients().to_vec(),
        libm::exp(-std::f64::consts::TAU * 25.0 / rate),
        libm::exp(-1.0 / (0.2 * rate)),
    );
    #[cfg(not(tsp_candidate_output))]
    let (taps, pole, release) = (
        chimera::airway::decimator::design_lowpass(49, 0.46 / 2.0, 8.5),
        chimera::math::exp(-2.0 * chimera::math::PI * 25.0 / rate),
        chimera::math::exp(-1.0 / (0.2 * rate)),
    );
    println!("{}", serde_json::json!({"taps": taps, "dc_pole": pole, "release": release}));
    Ok(())
}
