// 固定上流の整列用変換から、量子化前後の波形を採取する。
pub fn research_mfa_input(request: &str) -> Result<(), String> {
    let text = std::fs::read_to_string(request).map_err(|e| e.to_string())?;
    let files: Vec<(String, String, String)> = serde_json::from_str(&text).map_err(|e| e.to_string())?;
    for (input, noisy, quantized) in files {
        let (clean, fs) = read_wav(&input)?;
        if fs != crate::FS || clean.len() < (0.02 * fs) as usize || clean.iter().any(|v| !v.is_finite()) {
            return Err(format!("{input}: 有限な48 kHzの入力が必要です"));
        }
        let output = over_noise_floor(&clean);
        crate::wav::write(&noisy, &output, fs as u32, true).map_err(|e| format!("{noisy}: {e}"))?;
        crate::wav::write(&quantized, &output, fs as u32, false).map_err(|e| format!("{quantized}: {e}"))?;
    }
    Ok(())
}
