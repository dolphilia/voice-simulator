//! 子ども声部の観測器が共有するCSVの列。

use std::io::{self, Write};

pub const HEADER: &str = concat!(
    "frame,lip_cm,lip_area_cm2,pharynx_area_cm2,gate,f0_hz,phase,glottal_area_cm2,",
    "drive_area_cm2,drive_flow_cm3_s,glottal_level_dyn_cm2,glottal_gain,max_level,max_source"
);
pub const STARTUP_HEADER: &str = concat!(
    "sample,tip_x_cm,tip_y_cm,tip_target_x_cm,tip_target_y_cm,tip_vx_cm_s,tip_vy_cm_s,",
    "lip_area_cm2,pharynx_area_cm2,glottal_flow_cm3_s,radiation_derivative_cm3_s2"
);

pub const RADIATION_HEADER: &str = concat!(
    "internal_sample,lip_cm3_s,nose_cm3_s,wall_cm3_s,total_cm3_s,",
    "derivative_cm3_s2,velum_branch_area_cm2"
);

pub fn trace_arg<'a>(args: &'a [String], option: &str) -> (&'a [String], Option<&'a String>) {
    match args {
        [rest @ .., flag, path] if flag == option => (rest, Some(path)),
        _ => (args, None),
    }
}

pub fn write_radiation_pair(
    out: &mut impl Write,
    frame: usize,
    values: [[f64; 6]; 2],
) -> io::Result<()> {
    for (offset, row) in values.into_iter().enumerate() {
        write_row(out, 2 * frame + offset + 1, row)?;
    }
    Ok(())
}

/// 内部放射2点、間引き、ゲイン、DC除去、包絡、保持残数を順に保存する。
pub fn write_output_row(
    out: &mut impl Write,
    radiation: [f64; 2],
    stages: [f64; 5],
) -> io::Result<()> {
    for value in radiation.into_iter().chain(stages) {
        if !value.is_finite() {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "出力段に非有限の観測値があります",
            ));
        }
        out.write_all(&value.to_le_bytes())?;
    }
    Ok(())
}

pub fn write_row<const N: usize>(
    out: &mut impl Write,
    frame: usize,
    values: [f64; N],
) -> io::Result<()> {
    if !values.into_iter().all(f64::is_finite) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            format!("非有限の観測値 ({frame})"),
        ));
    }
    write!(out, "{frame}")?;
    for value in values {
        write!(out, ",{value}")?;
    }
    writeln!(out)
}
