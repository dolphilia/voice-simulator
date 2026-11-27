//! 固定上流の公開APIから片側の鳴管の開口率を取得する。

use chimera::sources::syrinx::SyrinxLabia;
use std::env;
use std::io::{self, BufWriter, Write};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = env::args().skip(1);
    let fs = args.next().ok_or("内部レートが必要です")?.parse()?;
    let samples = args.next().ok_or("サンプル数が必要です")?.parse()?;
    let seed = args.next().ok_or("初期変位の種が必要です")?.parse()?;
    let mut changes = Vec::new();
    while let Some(sample) = args.next() {
        let controls = args
            .by_ref()
            .take(4)
            .map(|x| x.parse())
            .collect::<Result<Vec<f64>, _>>()?;
        let [drive, tension, f0, gate] = controls[..] else {
            return Err("駆動、張力、音高、ゲートが必要です".into());
        };
        changes.push((sample.parse::<usize>()?, drive, tension, f0, gate));
    }
    let mut source = SyrinxLabia::new(fs, seed);
    let mut events = changes.into_iter().peekable();
    let mut output = BufWriter::new(io::stdout().lock());
    writeln!(output, "sample,opening")?;
    for sample in 0..samples {
        if let Some((_, drive, tension, f0, gate)) = events.next_if(|event| event.0 == sample) {
            source.drive = drive;
            source.tension = tension;
            source.f0 = f0;
            source.gate = gate;
        }
        writeln!(output, "{sample},{}", source.next())?;
    }
    output.flush()?;
    Ok(())
}
