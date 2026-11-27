//! 固定上流の通常描画から /i/ のポート状態・放射とPCMを採取する。

use chimera::anatomy::human::{BodyMix, NEUTRAL};
use chimera::phonetics::planner::vowel_table;
use chimera::voice::human_voice::{HumanVoice, SourcePatch};
use std::error::Error;
use std::fs::File;
use std::io::{BufWriter, Write};

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    let [
        area,
        internal,
        output,
        frames,
        pressure,
        gate,
        f0,
        breathiness,
        tension,
        gain,
        prefix,
        probe,
        extra @ ..,
    ] = args.as_slice()
    else {
        return Err("開口、レート、標本数、発声設定、出力先、観測指定を入力してください".into());
    };
    let internal: usize = internal.parse()?;
    let output: usize = output.parse()?;
    if output == 0 || !internal.is_multiple_of(output) {
        return Err("観測には整数の間引き率が必要です".into());
    }
    let frames: usize = frames.parse()?;
    let factor = internal / output;
    let mut pose = vowel_table()["male"]["i"].artic.apply_to(&NEUTRAL);
    pose.velum = area.parse()?;
    let mut voice = HumanVoice::new(output as f64, BodyMix::MALE.body(), factor);
    voice.artic.x = pose;
    voice.artic.target = pose;
    voice.artic.tip_free = false;
    voice.max_penetration = f64::INFINITY;
    voice.airway.apply(&pose, 0.0);
    let override_area = match extra {
        [] => None,
        [area] => Some(area.parse::<f64>()?),
        #[cfg(research_fixed_network_trace)]
        [area, start, end] => {
            let start: usize = start.parse()?;
            let end: usize = end.parse()?;
            if start >= end || end > frames * factor {
                return Err("気道全体の観測範囲を内部サンプルで指定してください".into());
            }
            let columns = voice.airway.net.n_nodes + voice.airway.net.n_branches;
            voice.research_network_trace =
                Some((start..end, Vec::with_capacity((end - start) * columns)));
            Some(area.parse::<f64>()?)
        }
        _ => return Err("ポート面積の上書きは1値で指定してください".into()),
    };
    if let Some(area) = override_area {
        if !area.is_finite() || area < 0.0 {
            return Err("ポート面積の上書きには有限の非負値を指定してください".into());
        }
        #[cfg(research_fixed_velum_port)]
        {
            voice.research_velum_area_override = Some(area);
            voice
                .airway
                .net
                .set_port_target(voice.airway.velum_port, area);
        }
        #[cfg(not(research_fixed_velum_port))]
        return Err("ポート面積の上書きに対応した上流の計測用ビルドが必要です".into());
    }
    voice.airway.net.snap_to_targets();
    voice.airway.net.noise_scale = 0.0;
    voice.set_source(&SourcePatch {
        f0: Some(f0.parse()?),
        pressure: Some(pressure.parse()?),
        breathiness: Some(breathiness.parse()?),
        tension: Some(tension.parse()?),
        drift: Some(0.0),
        ..SourcePatch::default()
    });
    voice.glottis.params.jitter = 0.0;
    voice.glottis.params.shimmer = 0.0;
    voice.output_gain = gain.parse()?;
    voice.set_gate(gate.parse()?);
    match probe.as_str() {
        "observer" => voice.research_velum_radiation = Some(Vec::with_capacity(frames * factor)),
        "plain" => {}
        _ => return Err("観測指定は observer または plain を使用してください".into()),
    }
    let mut pcm = vec![0.0_f32; frames];
    voice.render(&mut pcm);
    let mut wave = BufWriter::new(File::create_new(format!("{prefix}.f32"))?);
    for value in pcm {
        wave.write_all(&value.to_le_bytes())?;
    }
    wave.flush()?;
    if let Some(trace) = voice.research_velum_radiation {
        let mut pipe = BufWriter::new(File::create_new(format!("{prefix}.f64"))?);
        for row in trace {
            for value in row {
                pipe.write_all(&value.to_le_bytes())?;
            }
        }
        pipe.flush()?;
    }
    #[cfg(research_fixed_network_trace)]
    if let Some((_, state)) = voice.research_network_trace {
        let mut pipe = BufWriter::new(File::create_new(format!("{prefix}-network.f64"))?);
        for value in state {
            pipe.write_all(&value.to_le_bytes())?;
        }
        pipe.flush()?;
    }
    Ok(())
}
