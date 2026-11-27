//! 固定上流の調音器に同じ制御イベントを適用し、更新直後の状態を観測する。

use chimera::anatomy::human::{ArticKey, ArticPatch, BodyMix, HumanBody, N_ARTIC};
use chimera::control::{articulators::ArticulatorBank, score::Blended};
use chimera::voice::human_airway::HumanAirway;
use chimera::voice::human_voice::{DEFAULT_SOURCE, HumanVoice, SourcePatch};
use std::error::Error;
use std::fs::File;
use std::io::{self, BufWriter, Write};

const NAMES: [&str; N_ARTIC] = [
    "jaw_cm",
    "tongue_body_x_cm",
    "tongue_body_y_cm",
    "tongue_tip_x_cm",
    "tongue_tip_y_cm",
    "tip_curl",
    "tongue_root_cm",
    "lip_aperture_cm",
    "lip_protrusion_cm",
    "lip_spread",
    "labiodental",
    "velum_cm2",
    "larynx_cm",
    "epilarynx",
    "ventricular",
    "lateral",
    "dorsum",
];

fn main() -> Result<(), Box<dyn Error>> {
    let mut args = std::env::args().skip(1);
    let path = args.next().ok_or("比較用のイベント表を指定してください")?;
    let mode = args.next();
    let acoustics = matches!(mode.as_deref(), Some("network" | "network-with-contact"));
    let project = match mode.as_deref() {
        None | Some("voice") => None,
        Some("tract" | "network") => Some(false),
        Some("tract-with-contact" | "network-with-contact") => Some(true),
        _ => return Err("比較プローブのモードが不正です".into()),
    };
    let text = std::fs::read_to_string(path)?;
    let mut lines = text.lines();
    let settings = lines.next().map(fields).unwrap_or_default();
    let [rate, block, frames, tip_free, base_weight, body @ ..] = settings.as_slice() else {
        return Err("内部レート・制御ブロック・フレーム数・舌先・基準重みが必要です".into());
    };
    let body = match body {
        [] | ["male"] => BodyMix::MALE,
        ["female"] => BodyMix::FEMALE,
        ["child"] => BodyMix::CHILD,
        [blend] => {
            let (female, child) = blend.split_once(',').ok_or("体型の指定が不正です")?;
            BodyMix::new(female.parse()?, child.parse()?)
        }
        _ => return Err("体型の指定は一つです".into()),
    }
    .body();
    let block = block.parse::<usize>()?;
    let rate = rate.parse::<f64>()?;
    let dt = block as f64 / rate;
    let frames = frames.parse::<usize>()?;
    let base_weight = base_weight.parse::<f64>()?;
    let mut bank = ArticulatorBank::new();
    bank.tip_free = *tip_free == "1";
    let initial = fields(lines.next().ok_or("初期姿勢が必要です")?);
    if initial.len() != N_ARTIC {
        return Err("初期姿勢に全17成分が必要です".into());
    }
    let mut patch = ArticPatch::default();
    for (key, value) in ArticKey::ALL.into_iter().zip(initial) {
        patch.set(key, value.parse()?);
    }
    bank.snap(&patch);

    let events = lines
        .map(|line| {
            let (frame, instruction) =
                line.split_once(' ').ok_or("イベントにフレームが必要です")?;
            Ok::<_, Box<dyn Error>>((frame.parse::<usize>()?, fields(instruction)))
        })
        .collect::<Result<Vec<_>, _>>()?;
    if mode.as_deref() == Some("voice") {
        if base_weight != 1.0 {
            return Err("発声の上流参照では基準重みを1にそろえてください".into());
        }
        return render_voice(
            bank,
            rate,
            block,
            frames,
            &events,
            &args.collect::<Vec<_>>(),
            body,
        );
    }
    let mut events = events.into_iter().peekable();
    let mut blend = [Blended::default(); N_ARTIC];
    let mut out = BufWriter::new(io::stdout().lock());
    let mut airway = project.map(|_| HumanAirway::new(rate, body));
    if let Some(airway) = &mut airway {
        airway.apply(&bank.x, 0.0);
        if acoustics {
            airway.net.snap_to_targets();
            writeln!(
                out,
                concat!(
                    "sample,pharynx_area_cm2,pharynx_minimum_cm2,pharynx_dx_cm,",
                    "oral_center_area_cm2,oral_center_minimum_cm2,oral_dx_cm,",
                    "lips_area_cm2,lips_minimum_cm2,constriction_minimum_cm2,velum_area_cm2,",
                    "pressure_pharynx,pressure_junction,pressure_oral_center,pressure_lips,pressure_nose,",
                    "flow_center_in,flow_center_out,flow_wall_center,flow_velum,flow_lips,flow_nose,",
                    "radiation_derivative",
                )
            )?;
        } else {
            writeln!(
                out,
                concat!(
                    "frame,pass,tube,cell,raw_area_cm2,raw_minimum_cm2,area_cm2,minimum_cm2,",
                    "anatomical_length_cm,simulation_length_cm,teeth_s_cm,lip_cell,",
                    "tip_distance_cm,body_distance_cm,velum_cm2",
                )
            )?;
            write_tract(&mut out, -1, "seed", airway, &bank)?;
        }
    } else {
        writeln!(
            out,
            concat!(
                "frame,internal_start_sample,time_s,articulator,position,velocity_per_s,",
                "target,effective,base_speed,applied_speed,tip_free",
            )
        )?;
    }
    for frame in 0..frames {
        while events.peek().is_some_and(|event| event.0 == frame) {
            let (_, instruction) = events.next().expect("イベント");
            apply(&mut bank, &mut blend, &instruction)?;
        }
        bank.step(dt, Some(&blend), base_weight);
        if let Some(airway) = &mut airway {
            airway.apply(&bank.x, dt);
            if !acoustics {
                write_tract(&mut out, frame as i64, "apply", airway, &bank)?;
            }
            if project == Some(true) && enforce_contacts(&mut bank, airway) {
                airway.reapply(&bank.x);
                if !acoustics {
                    write_tract(&mut out, frame as i64, "reapply", airway, &bank)?;
                }
            }
            if acoustics {
                // 形状変化で生じる圧力と放射だけを比較する。
                airway.net.set_noise_sources(&[]);
                airway.net.begin_block(block);
                for offset in 0..block {
                    let y = airway.net.step();
                    write_acoustics(&mut out, frame * block + offset, airway, y)?;
                }
            }
            continue;
        }
        let start = frame * block;
        let time = (frame + 1) as f64 * dt;
        for key in ArticKey::ALL {
            let i = key.index();
            let speed = bank.speed[i];
            let applied = if blend[i].weight > 0.0 {
                speed * blend[i].speed
            } else {
                speed
            };
            writeln!(
                out,
                "{frame},{start},{time},{},{},{},{},{},{speed},{applied},{}",
                NAMES[i],
                bank.x.get(key),
                bank.v[i],
                bank.target.get(key),
                bank.effective.get(key),
                u8::from(bank.tip_free)
            )?;
        }
    }
    out.flush()?;
    Ok(())
}

fn fields(line: &str) -> Vec<&str> {
    line.split_whitespace().collect()
}

fn apply(
    bank: &mut ArticulatorBank,
    blend: &mut [Blended; N_ARTIC],
    command: &[&str],
) -> Result<(), Box<dyn Error>> {
    match command {
        ["target", key, value] => {
            let key = ArticKey::ALL[key.parse::<usize>()?];
            bank.set_target(&ArticPatch::default().with(key, value.parse()?));
        }
        ["speed", key, value] => bank.speed[key.parse::<usize>()?] = value.parse()?,
        ["tip_free", free] => bank.tip_free = *free == "1",
        ["clear_blend"] => blend.fill(Blended::default()),
        ["blend", key, value, weight, speed] => {
            blend[key.parse::<usize>()?] = Blended {
                value: value.parse()?,
                weight: weight.parse()?,
                speed: speed.parse()?,
            };
        }
        _ => return Err("イベント表に未知の命令があります".into()),
    }
    Ok(())
}

// HumanVoice の非公開の接触補正を、固定上流の公開状態へ適用する。
fn enforce_contacts(bank: &mut ArticulatorBank, airway: &HumanAirway) -> bool {
    let k = airway.body.scale;
    let limit = -0.1 * k;
    let mut changed = false;
    for (d, n, kx, ky) in [
        (
            airway.tract.contact_tip,
            airway.tract.contact_tip_n,
            ArticKey::TtX,
            ArticKey::TtY,
        ),
        (
            airway.tract.contact_body,
            airway.tract.contact_body_n,
            ArticKey::TbX,
            ArticKey::TbY,
        ),
    ] {
        if d >= limit {
            continue;
        }
        changed = true;
        let depth = limit - d;
        let sx = (if bank.x.get(kx) > 0.5 {
            1.0 / 0.86
        } else {
            1.0
        }) / k;
        let sy = 1.0 / k;
        *bank.x.get_mut(kx) += n.x * depth * sx;
        *bank.x.get_mut(ky) += n.y * depth * sy;
        let (ix, iy) = (kx.index(), ky.index());
        let vn = bank.v[ix] * n.x / sx + bank.v[iy] * n.y / sy;
        if vn < 0.0 {
            bank.v[ix] -= vn * n.x * sx;
            bank.v[iy] -= vn * n.y * sy;
        }
    }
    changed
}

fn write_tract(
    out: &mut impl Write,
    frame: i64,
    pass: &str,
    airway: &HumanAirway,
    bank: &ArticulatorBank,
) -> io::Result<()> {
    let f = airway.frame.as_ref().expect("観測前に形状を確定する");
    let mut ph_raw = vec![0.0; airway.n_ph];
    let mut or_raw = vec![0.0; airway.n_or];
    let mut ph_min = vec![0.0; airway.n_ph];
    let mut or_min = vec![0.0; airway.n_or];
    airway.tract.resample(
        &bank.x,
        f,
        &mut ph_raw,
        &mut or_raw,
        Some(&mut ph_min),
        Some(&mut or_min),
    );
    let lips_from = (airway.n_or as f64 * (1.0 - (f.lip_s - f.teeth_s) / airway.or_len)) as usize;
    for (tube, raw, raw_min, areas, minimums, anatomical, simulation) in [
        (
            "pharynx",
            &ph_raw,
            &ph_min,
            &airway.ph_areas,
            &airway.ph_min,
            airway.ph_len,
            airway.net.tube_length[airway.pharynx.index],
        ),
        (
            "oral",
            &or_raw,
            &or_min,
            &airway.or_areas,
            &airway.or_min,
            airway.or_len,
            airway.net.tube_length[airway.oral.index],
        ),
    ] {
        for cell in 0..areas.len() {
            let lip = u8::from(tube == "oral" && cell >= lips_from);
            writeln!(
                out,
                "{frame},{pass},{tube},{cell},{},{},{},{},{anatomical},{simulation},{},{lip},{},{},{}",
                raw[cell],
                raw_min[cell],
                areas[cell],
                minimums[cell],
                f.teeth_s,
                airway.tract.contact_tip,
                airway.tract.contact_body,
                f.velum_port,
            )?;
        }
    }
    Ok(())
}

fn write_acoustics(
    out: &mut impl Write,
    sample: usize,
    airway: &HumanAirway,
    radiation: f64,
) -> io::Result<()> {
    let ph = airway.pharynx.first_node();
    let junction = airway.pharynx.last_node();
    let center = airway.n_or / 2 - 1;
    let oral = airway.oral.node(center);
    let lips = airway.oral.last_node();
    let nose = airway.nasal.last_node();
    let net = &airway.net;
    write!(out, "{sample}")?;
    for value in [
        net.area[ph],
        net.amin[ph],
        net.dx[ph],
        net.area[oral],
        net.amin[oral],
        net.dx[oral],
        net.area[lips],
        net.amin[lips],
        net.amin[airway.oral.node(2 * airway.n_or / 3 - 1)],
        net.port_area[airway.velum_port],
        net.p[ph],
        net.p[junction],
        net.p[oral],
        net.p[lips],
        net.p[nose],
        net.u[airway.oral.branch(center - 1)],
        net.u[airway.oral.branch(center)],
        net.wall_u[oral],
        net.u[airway.velum_port],
        net.radiated_flow(airway.rad_lips),
        net.radiated_flow(airway.rad_nose),
        radiation,
    ] {
        write!(out, ",{value}")?;
    }
    writeln!(out)
}

fn render_voice(
    bank: ArticulatorBank,
    internal_rate: f64,
    block_samples: usize,
    frames: usize,
    events: &[(usize, Vec<&str>)],
    args: &[String],
    body: HumanBody,
) -> Result<(), Box<dyn Error>> {
    let [
        output,
        pressure,
        gate,
        f0,
        breathiness,
        tension,
        gain,
        block,
        pcm,
        trace,
        detail @ ..,
    ] = args
    else {
        return Err("発声の出力レート、音源設定、ホストブロック、出力先が必要です".into());
    };
    let output = output.parse::<f64>()?;
    let factor = (internal_rate / output) as usize;
    let host = block.parse::<usize>()?;
    if factor == 0
        || output * factor as f64 != internal_rate
        || block_samples != 64 * factor
        || host == 0
        || f0.parse::<f64>()? != DEFAULT_SOURCE.f0
    {
        return Err("既定F0と出力64サンプルごとの制御周期を指定してください".into());
    }
    let mut voice = HumanVoice::new(output, body, factor);
    let (cells, unlimited_rate) = match detail {
        [] => (Vec::new(), None),
        [cells] => (parse_trace_cells(cells, voice.airway.n_or)?, None),
        [cells, rate] => (
            parse_trace_cells(cells, voice.airway.n_or)?,
            Some(rate.parse::<f64>()?),
        ),
        _ => return Err("前方セルの一覧と速度制限対照の上限を確認してください".into()),
    };
    if let Some(rate) = unlimited_rate {
        if !rate.is_finite() || rate <= 0.0 {
            return Err("速度制限の対照には有限の正値を指定してください".into());
        }
        voice.airway.max_area_rate = rate;
        voice.airway.lip_open_rate = rate;
        voice.airway.seal_rate = rate;
    }
    voice.artic = bank;
    voice.airway.apply(&voice.artic.x, 0.0);
    voice.airway.net.snap_to_targets();
    voice.airway.net.noise_scale = 0.0;
    voice.set_source(&SourcePatch {
        f0: Some(DEFAULT_SOURCE.f0),
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

    let mut pcm = BufWriter::new(File::create_new(pcm)?);
    let mut trace = if trace == "-" {
        None
    } else {
        Some(BufWriter::new(File::create_new(trace)?))
    };
    if let Some(out) = &mut trace {
        write!(
            out,
            concat!(
                "internal_sample,control_frame,jaw_cm,tongue_tip_y_cm,",
                "pharynx_dx_cm,oral_dx_cm,oral_area_cm2,oral_minimum_cm2,velum_area_cm2,",
                "gate,lung_boundary_dyn_cm2,pressure_sub_dyn_cm2,pressure_supra_dyn_cm2,",
                "glottal_area_cm2,glottal_flow_cm3_s,glottal_phase,glottal_voicing,glottal_f0_hz,",
                "velum_flow_cm3_s,lip_flow_cm3_s,nose_flow_cm3_s,radiation_derivative_cm3_s2,",
                "tongue_body_x_cm,tongue_body_y_cm,lip_aperture_cm,lip_minimum_cm2",
            )
        )?;
        if !cells.is_empty() {
            write!(
                out,
                ",labiodental,lip_pressure_dyn_cm2,wall_radiation_cm3_s"
            )?;
            for cell in &cells {
                write!(
                    out,
                    ",oral_{cell}_applied_area_cm2,oral_{cell}_applied_minimum_cm2,oral_{cell}_pressure_dyn_cm2"
                )?;
            }
        }
        writeln!(out)?;
    }
    let total = frames
        .checked_mul(64)
        .ok_or("発声のフレーム数が範囲外です")?;
    #[cfg(research_glottal_pressure)]
    let pressure_path = prepare_pressure_trace(&mut voice, total * factor)?;
    let mut buffer = vec![0.0; host.min(total)];
    let mut events = events.iter().peekable();
    let mut unused_blend = [Blended::default(); N_ARTIC];
    let mut frame = 0;
    while frame < total {
        while events
            .peek()
            .is_some_and(|(control, _)| *control * 64 == frame)
        {
            let (_, instruction) = events.next().expect("この時刻のイベント");
            if matches!(instruction.first(), Some(&("clear_blend" | "blend"))) {
                return Err("発声の上流参照には調音ジェスチャーを含められません".into());
            }
            match instruction.as_slice() {
                ["gate", value] => voice.set_gate(value.parse()?),
                ["f0_hz", value] => {
                    voice.set_source(&SourcePatch::f0(value.parse()?));
                    // 音源設定を再適用した後も、比較用の周期変動は無効にする。
                    voice.glottis.params.jitter = 0.0;
                    voice.glottis.params.shimmer = 0.0;
                }
                _ => apply(&mut voice.artic, &mut unused_blend, instruction)?,
            }
        }
        let next = events.peek().map_or(total, |(control, _)| *control * 64);
        let n = if trace.is_some() {
            1
        } else {
            host.min(next - frame)
        };
        voice.render(&mut buffer[..n]);
        for value in &buffer[..n] {
            pcm.write_all(&value.to_le_bytes())?;
        }
        if let Some(out) = &mut trace {
            let air = &voice.airway;
            let net = &air.net;
            let ph = air.pharynx.first_node();
            let sub = air.trachea.last_node();
            let oral = air.oral.node(air.n_or / 2 - 1);
            write!(out, "{},{}", (frame + 1) * factor - 1, frame / 64)?;
            for value in [
                voice.artic.x.get(ArticKey::Jaw),
                voice.artic.x.get(ArticKey::TtY),
                net.dx[ph],
                net.dx[oral],
                net.area[oral],
                net.amin[oral],
                net.port_area[air.velum_port],
                voice.gate,
                net.p[air.lungs],
                net.p[sub],
                net.p[ph],
                voice.glottis.area,
                net.u[air.glottis_port],
                voice.glottis.cycle_phase(),
                voice.glottis.voicing,
                voice.glottis.f0_now,
                net.u[air.velum_port],
                net.radiated_flow(air.rad_lips),
                net.radiated_flow(air.rad_nose),
                net.out,
                voice.artic.x.get(ArticKey::TbX),
                voice.artic.x.get(ArticKey::TbY),
                voice.artic.x.get(ArticKey::LipAp),
                net.amin[air.oral.last_node()],
            ] {
                write!(out, ",{value}")?;
            }
            if !cells.is_empty() {
                // 固定上流の WALL_SOFT を使う咽頭・口腔だけが、壁流量の1/4を外へ放射する。
                let wall_radiation: f64 = [air.pharynx, air.oral]
                    .into_iter()
                    .flat_map(|tube| tube.first_node()..=tube.last_node())
                    .map(|node| 0.25 * net.wall_u[node])
                    .sum();
                write!(
                    out,
                    ",{},{},{wall_radiation}",
                    voice.artic.x.labiodental,
                    net.p[air.oral.last_node()]
                )?;
                for &cell in &cells {
                    let node = air.oral.node(cell);
                    write!(
                        out,
                        ",{},{},{}",
                        net.area[node], net.amin[node], net.p[node]
                    )?;
                }
            }
            writeln!(out)?;
        }
        frame += n;
    }
    if let Some(out) = &mut trace {
        out.flush()?;
    }
    pcm.flush()?;
    #[cfg(research_glottal_pressure)]
    if let Some(path) = pressure_path {
        let mut out = BufWriter::new(File::create_new(path)?);
        writeln!(
            out,
            "internal_sample,glottal_physical_pressure_dyn_cm2,glottal_input_pressure_dyn_cm2"
        )?;
        for (sample, [physical, input]) in voice
            .research_glottal_pressure_trace
            .take()
            .ok_or("声門の圧差系列がありません")?
            .into_iter()
            .enumerate()
        {
            writeln!(out, "{sample},{physical},{input}")?;
        }
        out.flush()?;
    }
    Ok(())
}

#[cfg(research_glottal_pressure)]
fn prepare_pressure_trace(
    voice: &mut HumanVoice,
    count: usize,
) -> Result<Option<std::path::PathBuf>, Box<dyn Error>> {
    let Some(output) = std::env::var_os("CHIMERA_RESEARCH_PRESSURE_TRACE") else {
        return Ok(None);
    };
    if let Some(path) = std::env::var_os("CHIMERA_RESEARCH_PRESSURE_INPUT") {
        let contents = std::fs::read_to_string(path)?;
        let mut lines = contents.lines();
        let start: usize = lines
            .next()
            .ok_or("声門圧差を指定する開始位置がありません")?
            .parse()?;
        let values = lines
            .map(str::parse::<f64>)
            .collect::<Result<Vec<_>, _>>()?;
        if values.is_empty()
            || values.iter().any(|x| !x.is_finite())
            || start
                .checked_add(values.len())
                .is_none_or(|end| end > count)
        {
            return Err("声門圧差の系列に有限な値と有効な区間を指定してください".into());
        }
        voice.research_glottal_pressure = Some((start, values));
    }
    voice.research_glottal_pressure_trace = Some(Vec::with_capacity(count));
    Ok(Some(output.into()))
}

fn parse_trace_cells(input: &str, count: usize) -> Result<Vec<usize>, Box<dyn Error>> {
    let cells: Vec<usize> = input.split(',').map(str::parse).collect::<Result<_, _>>()?;
    if cells
        .iter()
        .enumerate()
        .any(|(i, cell)| *cell >= count || cells[..i].contains(cell))
    {
        return Err("計測する口腔セルは有効な番号を重複なしで指定してください".into());
    }
    Ok(cells)
}
