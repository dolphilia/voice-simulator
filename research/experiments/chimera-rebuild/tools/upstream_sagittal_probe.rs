//! 固定上流の公開フレームから、輪郭・格子・接触・断面・セルを取り出す。

use chimera::anatomy::geom::Vec2;
use chimera::anatomy::human::{
    BodyMix, HumanArtic, HumanBody, HumanFrame, HumanVocalTract, NEUTRAL,
};
use chimera::engine::default_f0;
use chimera::voice::human_airway::HumanAirway;
use std::env;
use std::error::Error;
use std::fs;
use std::io::{self, BufWriter, Write};
use std::num::NonZeroUsize;
use std::ops::Range;
use std::slice::from_ref;

struct FixedAirwayDrive {
    rate: f64,
    samples: usize,
    volume: f64,
    impulse_sample: usize,
    steady_flow: f64,
    periodic_flow: Option<(usize, Vec<f64>)>,
    trace_state_samples: Option<Range<usize>>,
}

fn main() -> Result<(), Box<dyn Error>> {
    let mut args = env::args().skip(1).peekable();
    if args.peek().is_some_and(|arg| arg == "--segment-lengths") {
        args.next();
        let path = args
            .next()
            .ok_or("隣接する中点の座標ファイルを指定してください")?;
        if args.next().is_some() {
            return Err("座標ファイルは1件指定してください".into());
        }
        let mut out = BufWriter::new(io::stdout().lock());
        for line in fs::read_to_string(path)?.lines() {
            let values = line
                .split_ascii_whitespace()
                .map(str::parse)
                .collect::<Result<Vec<f64>, _>>()?;
            let &[x0, y0, x1, y1] = values.as_slice() else {
                return Err("座標は前後2点の4値を1行に指定してください".into());
            };
            if !values.iter().all(|value| value.is_finite()) {
                return Err("座標に非有限の値があります".into());
            }
            let length = chimera::anatomy::geom::dist(Vec2 { x: x1, y: y1 }, Vec2 { x: x0, y: y0 });
            writeln!(out, "{length}")?;
        }
        out.flush()?;
        return Ok(());
    }
    let mix = if args.peek().is_some_and(|arg| arg == "--body") {
        args.next();
        let value = args
            .next()
            .ok_or("体型名または女性,子どもの割合を指定してください")?;
        if let Some((female, child)) = value.split_once(',') {
            BodyMix::new(female.parse()?, child.parse()?)
        } else {
            BodyMix::from(value.as_str())
        }
    } else {
        BodyMix::MALE
    };
    let mode = args.peek().filter(|arg| arg.starts_with("--")).cloned();
    if mode.is_some() {
        args.next();
    }
    let counts = if mode.as_deref() == Some("--resample") {
        let mut count = || -> Result<NonZeroUsize, Box<dyn Error>> {
            Ok(args
                .next()
                .ok_or("咽頭と口腔のセル数を指定してください")?
                .parse()?)
        };
        Some([count()?.get(), count()?.get()])
    } else {
        None
    };
    let biased = mode.as_deref() == Some("--fixed-airway-bias");
    let trace_state = mode.as_deref() == Some("--fixed-airway-state");
    let fixed = if trace_state || mode.as_deref() == Some("--fixed-airway-periodic") {
        let mut argument = || {
            args.next()
                .ok_or("内部レート・サンプル数・開始点・定常流量・流量ファイルを指定してください")
        };
        let rate = argument()?.parse()?;
        let samples: usize = argument()?.parse()?;
        let start: usize = argument()?.parse()?;
        let steady_flow: f64 = argument()?.parse()?;
        let series = fs::read_to_string(argument()?)?
            .split_ascii_whitespace()
            .map(str::parse)
            .collect::<Result<Vec<f64>, _>>()?;
        if series.is_empty()
            || series.len() > samples.saturating_sub(start)
            || !series.iter().all(|value| value.is_finite())
            || !steady_flow.is_finite()
        {
            return Err("周期流量の1ブロックを計算区間内に有限値で指定してください".into());
        }
        let trace_state_samples = if trace_state {
            let first: usize = argument()?.parse()?;
            let end: usize = argument()?.parse()?;
            if first >= end || end > samples {
                return Err("観測区間は計算区間内の空でない半開区間を指定してください".into());
            }
            Some(first..end)
        } else {
            None
        };
        Some(FixedAirwayDrive {
            rate,
            samples,
            volume: 0.0,
            impulse_sample: 0,
            steady_flow,
            periodic_flow: Some((start, series)),
            trace_state_samples,
        })
    } else if biased || mode.as_deref() == Some("--fixed-airway") {
        let mut argument = || {
            args.next().ok_or(
                "内部レート・サンプル数・注入体積と、定常流モードの追加引数を指定してください",
            )
        };
        Some(FixedAirwayDrive {
            rate: argument()?.parse()?,
            samples: argument()?.parse()?,
            volume: argument()?.parse()?,
            impulse_sample: if biased { argument()?.parse()? } else { 0 },
            steady_flow: if biased { argument()?.parse()? } else { 0.0 },
            periodic_flow: None,
            trace_state_samples: None,
        })
    } else {
        None
    };
    let controls = args
        .map(|value| value.parse())
        .collect::<Result<Vec<f64>, _>>()?;
    let &[
        jaw,
        tb_x,
        tb_y,
        tt_x,
        tt_y,
        root,
        tt_curl,
        dorsum,
        lip_ap,
        lip_prot,
        lip_width,
        labiodental,
        velum,
        larynx,
        ref extra @ ..,
    ] = controls.as_slice()
    else {
        return Err("14個の調音値を指定してください".into());
    };
    let (lateral, epilarynx, ventricular) = match *extra {
        [] => (NEUTRAL.lateral, NEUTRAL.epilarynx, NEUTRAL.ventricular),
        [lateral] => (lateral, NEUTRAL.epilarynx, NEUTRAL.ventricular),
        [lateral, epilarynx, ventricular] => (lateral, epilarynx, ventricular),
        _ => {
            return Err(
                "追加の調音値は舌側面のみ、または舌側面・喉頭蓋付近・仮声帯の3個です".into(),
            );
        }
    };
    let pose = HumanArtic {
        jaw,
        tb_x,
        tb_y,
        tt_x,
        tt_y,
        root,
        tt_curl,
        dorsum,
        lip_ap,
        lip_prot,
        lip_width,
        labiodental,
        velum,
        larynx,
        lateral,
        epilarynx,
        ventricular,
        ..NEUTRAL
    };
    let mut output = BufWriter::new(io::stdout().lock());
    if let Some(drive) = fixed {
        write_fixed_airway(&mut output, mix.body(), &pose, drive)?;
        output.flush()?;
        return Ok(());
    }
    let body = mix.body();
    let mut model = HumanVocalTract::new(body);
    let f = model.compute_new(&pose);
    if let Some(counts) = counts {
        write_resampled(&mut output, &model, &pose, &f, counts)?;
        output.flush()?;
        return Ok(());
    }
    match mode.as_deref() {
        Some("--body-metrics") => {
            writeln!(
                output,
                concat!(
                    "male,female,child,preset,nearest,scale,pharynx,tongue_radius,lip_width,",
                    "fold_length,open_phase,default_f0_hz,tongue_radius_cm,lip_width_cm,",
                    "velum_port_cm2,epilarynx_length_cm"
                )
            )?;
            let [(_, male), (_, female), (_, child)] = mix.weights();
            let spread = pose.lip_width.clamp(0.0, 1.0);
            writeln!(
                output,
                "{male},{female},{child},{},{},{},{},{},{},{},{},{},{},{},{},{}",
                mix.preset().map_or("", |preset| preset.as_str()),
                mix.nearest().as_str(),
                body.scale,
                body.pharynx,
                body.tongue_radius,
                body.lip_width,
                body.fold_length,
                body.open_phase,
                default_f0(mix),
                f.tongue_radius,
                (1.1 + (body.lip_width - 1.1) * spread) * body.scale,
                f.velum_port,
                f.grid[0].s,
            )?;
        }
        Some("--grid") => write_grid(&mut output, &f, Columns::Rays)?,
        Some("--contact") => write_grid(&mut output, &f, Columns::Gaps)?,
        Some("--area") => write_grid(&mut output, &f, Columns::Areas)?,
        Some("--area-metrics") => {
            writeln!(
                output,
                "length_cm,pharynx_length_cm,teeth_s_cm,lip_s_cm,lip_area_cm2,split_index"
            )?;
            writeln!(
                output,
                "{},{},{},{},{},{}",
                f.length, f.pharynx_length, f.teeth_s, f.lip_s, f.lip_area, f.split_index
            )?;
        }
        Some("--contact-metrics") => {
            writeln!(output, "part,distance_cm,normal_x,normal_y")?;
            for (part, distance, normal) in [
                ("tip", model.contact_tip, model.contact_tip_n),
                ("body", model.contact_body, model.contact_body_n),
            ] {
                writeln!(output, "{part},{distance},{},{}", normal.x, normal.y)?;
            }
        }
        Some(_) => return Err("輪郭・格子・接触・断面・セルの出力形式を確認してください".into()),
        None => write_contours(&mut output, &model, &f)?,
    }
    output.flush()?;
    Ok(())
}

fn write_fixed_airway(
    out: &mut impl Write,
    body: HumanBody,
    pose: &HumanArtic,
    drive: FixedAirwayDrive,
) -> io::Result<()> {
    let FixedAirwayDrive {
        rate,
        samples,
        volume,
        impulse_sample,
        steady_flow,
        periodic_flow,
        trace_state_samples,
    } = drive;
    let mut airway = HumanAirway::new(rate, body);
    airway.apply(pose, 0.0);
    let net = &mut airway.net;
    net.snap_to_targets();
    net.noise_scale = 0.0;
    let elements = net.linear_elements();
    if samples == 0 {
        let courant = net.check_cfl();
        let velum = net.port_area[airway.velum_port];
        writeln!(
            out,
            concat!(
                "node,tube,anatomical_length_cm,simulation_length_cm,cell_length_cm,",
                "area_cm2,minimum_area_cm2,geometric_compliance,velum_port_cm2,courant,branch_count",
            )
        )?;
        for node in 0..net.n_nodes {
            let tube = net.tube_of_node(node);
            let length = net.tube_length[tube];
            let anatomy = if tube == airway.pharynx.index {
                airway.ph_len
            } else if tube == airway.oral.index {
                airway.or_len
            } else {
                length
            };
            writeln!(
                out,
                "{node},{},{anatomy},{length},{},{},{},{},{velum},{courant},{}",
                net.tube_names[tube],
                net.dx[node],
                net.area[node],
                net.amin[node],
                elements.c[node],
                net.n_branches
            )?;
        }
        return Ok(());
    }
    let ph_entry = airway.pharynx.first_node();
    let junction = airway.pharynx.last_node();
    let lips = airway.oral.last_node();
    let nostrils = airway.nasal.last_node();
    let sinus = net.tubes.last().expect("上顎洞").first_node();
    let oral_link = elements
        .a
        .iter()
        .zip(&elements.b)
        .position(|(&a, &b)| a == junction && b == airway.oral.first_node())
        .expect("咽頭と口腔の接続");
    let sinus_neck = elements
        .b
        .iter()
        .position(|&b| b == sinus)
        .expect("上顎洞の頸部");
    let (nodes, branches) = if trace_state_samples.is_some() {
        (net.n_nodes, net.n_branches)
    } else {
        (0, 0)
    };
    write!(
        out,
        concat!(
            "sample,pressure_pharynx_entry,pressure_junction,pressure_lips,pressure_nose,pressure_sinus,",
            "flow_oral_link,flow_velum,flow_sinus_neck,flow_lips,flow_nose,flow_walls,radiation_derivative",
        )
    )?;
    for node in 0..nodes {
        write!(out, ",pressure_node_{node}")?;
    }
    for branch in 0..branches {
        write!(out, ",flow_branch_{branch}")?;
    }
    writeln!(out)?;
    for sample in 0..samples {
        let periodic = periodic_flow.as_ref().and_then(|(start, series)| {
            sample
                .checked_sub(*start)
                .map(|offset| series[offset % series.len()])
        });
        net.ext_flow[ph_entry] = if let Some(flow) = periodic {
            flow
        } else if sample == impulse_sample {
            steady_flow + volume * rate
        } else {
            steady_flow
        };
        let radiation = net.step();
        if trace_state_samples
            .as_ref()
            .is_some_and(|range| !range.contains(&sample))
        {
            continue;
        }
        let walls: f64 = net
            .wall_u
            .iter()
            .zip(&elements.wall_rad)
            .map(|(flow, fraction)| flow * fraction)
            .sum();
        write!(
            out,
            "{sample},{},{},{},{},{},{},{},{},{},{},{walls},{radiation}",
            net.p[ph_entry],
            net.p[junction],
            net.p[lips],
            net.p[nostrils],
            net.p[sinus],
            net.u[oral_link],
            net.u[airway.velum_port],
            net.u[sinus_neck],
            net.radiated_flow(airway.rad_lips),
            net.radiated_flow(airway.rad_nose)
        )?;
        for value in &net.p[..nodes] {
            write!(out, ",{value}")?;
        }
        for value in &net.u[..branches] {
            write!(out, ",{value}")?;
        }
        writeln!(out)?;
    }
    Ok(())
}

fn write_resampled(
    out: &mut impl Write,
    model: &HumanVocalTract,
    pose: &HumanArtic,
    frame: &HumanFrame,
    [pharynx_count, oral_count]: [usize; 2],
) -> io::Result<()> {
    let mut pharynx = vec![0.0; pharynx_count];
    let mut oral = vec![0.0; oral_count];
    let mut pharynx_min = vec![0.0; pharynx_count];
    let mut oral_min = vec![0.0; oral_count];
    let (pharynx_length, oral_length) = model.resample(
        pose,
        frame,
        &mut pharynx,
        &mut oral,
        Some(&mut pharynx_min),
        Some(&mut oral_min),
    );
    writeln!(out, "tube,cell,start_cm,end_cm,area_cm2,minimum_area_cm2")?;
    for (name, start, length, areas, minima) in [
        ("pharynx", 0.0, pharynx_length, pharynx, pharynx_min),
        ("oral", pharynx_length, oral_length, oral, oral_min),
    ] {
        let width = length / areas.len() as f64;
        for (index, (area, minimum)) in areas.into_iter().zip(minima).enumerate() {
            let left = start + width * index as f64;
            let right = start + width * (index + 1) as f64;
            writeln!(out, "{name},{index},{left},{right},{area},{minimum}")?;
        }
    }
    Ok(())
}

fn write_contours(out: &mut impl Write, model: &HumanVocalTract, f: &HumanFrame) -> io::Result<()> {
    let parts: [(&str, &[Vec2]); 15] = [
        ("outer", &f.outer),
        ("inner", &f.inner),
        ("tongue", &f.tongue),
        ("velum", &f.velum),
        ("upper_lip", &f.upper_lip),
        ("lower_lip", &f.lower_lip),
        ("upper_teeth", &f.upper_teeth),
        ("lower_teeth", &f.lower_teeth),
        ("jaw_bone", &f.jaw_bone),
        ("epiglottis", &f.epiglottis),
        ("nasal_cavity", &f.nasal_cavity),
        ("palate", model.palate()),
        ("glottis", from_ref(&f.glottis)),
        ("tongue_center", from_ref(&f.tongue_center)),
        ("tip", from_ref(&f.tip)),
    ];
    writeln!(out, "part,index,x_cm,y_cm")?;
    for (name, points) in parts {
        for (index, Vec2 { x, y }) in points.iter().enumerate() {
            writeln!(out, "{name},{index},{x},{y}")?;
        }
    }
    Ok(())
}

enum Columns {
    Rays,
    Gaps,
    Areas,
}

fn write_grid(out: &mut impl Write, frame: &HumanFrame, columns: Columns) -> io::Result<()> {
    write!(
        out,
        "index,region,inner_x_cm,inner_y_cm,outer_x_cm,outer_y_cm,mid_x_cm,mid_y_cm,ray_cm"
    )?;
    if !matches!(columns, Columns::Rays) {
        write!(out, ",gap_cm")?;
    }
    if matches!(columns, Columns::Areas) {
        write!(out, ",area_cm2,s_cm")?;
    }
    writeln!(out)?;
    for (index, g) in frame.grid.iter().enumerate() {
        write!(
            out,
            "{index},{},{},{},{},{},{},{},{}",
            g.region, g.inner.x, g.inner.y, g.outer.x, g.outer.y, g.mid.x, g.mid.y, g.ray
        )?;
        if !matches!(columns, Columns::Rays) {
            write!(out, ",{}", g.d)?;
        }
        if matches!(columns, Columns::Areas) {
            write!(out, ",{},{}", g.area, g.s)?;
        }
        writeln!(out)?;
    }
    Ok(())
}
