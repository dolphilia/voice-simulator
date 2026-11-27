//! 確認用07の観測列をリトルエンディアンの倍精度で保存する。

use std::io::{self, Write};

pub fn write_row(out: &mut impl Write, values: &[f64]) -> io::Result<()> {
    for value in values {
        out.write_all(&value.to_le_bytes())?;
    }
    Ok(())
}
