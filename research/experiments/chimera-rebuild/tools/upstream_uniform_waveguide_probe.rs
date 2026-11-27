//! 固定上流の一様管と、同じ終端を使う双方向遅延を内部レートで観測する。

use chimera::airway::network::{AirwayNetwork, Area, TubeSpec};
use std::error::Error;
use std::io::{self, BufWriter, Write};

type Sample = [f64; 4];

fn upstream(
    rate: f64,
    cells: usize,
    length_cm: f64,
    area_cm2: f64,
    viscous_scale: f64,
) -> impl FnMut(f64) -> Sample {
    let mut net = AirwayNetwork::new(rate);
    let tube = net.add_tube(
        TubeSpec::new("matched", cells, length_cm, Area::Uniform(area_cm2)).viscous(viscous_scale),
    );
    let inlet = tube.first_node();
    let outlet = tube.last_node();
    let radiation = net.add_radiation(outlet);
    net.finalize();
    net.begin_block(1);
    move |input| {
        net.ext_flow[inlet] = input;
        let derivative = net.step();
        [
            net.p[inlet],
            net.p[outlet],
            net.radiated_flow(radiation),
            derivative,
        ]
    }
}

fn waveguide(
    rate: f64,
    delay_samples: usize,
    impedance: f64,
    inlet_reflection: f64,
    mut outlet_pressure: impl FnMut(f64) -> f64,
) -> impl FnMut(f64) -> Sample {
    // 一様断面では散乱が恒等になり、各方向の区間列は固定長の遅延にまとめられる。
    let mut waves = vec![[0.0; 2]; delay_samples];
    let mut index = 0;
    let mut last_flow = 0.0;
    move |input| {
        let [towards_mouth, towards_source] = waves[index];
        let at_source = impedance * input + inlet_reflection * towards_source;
        let at_mouth = outlet_pressure(towards_mouth);
        let reflected = at_mouth - towards_mouth;
        waves[index] = [at_source, reflected];
        index = (index + 1) % waves.len();
        let flow = (towards_mouth - reflected) / impedance;
        let derivative = (flow - last_flow) * rate;
        last_flow = flow;
        [at_source + towards_source, at_mouth, flow, derivative]
    }
}

fn radiation(rate: f64, impedance: f64, inertance: f64, resistance: f64) -> impl FnMut(f64) -> f64 {
    let mut inertance_flow = 0.0;
    let step_over_inertance = 1.0 / (rate * inertance);
    let denominator = 1.0 + impedance * (1.0 / resistance + 0.5 * step_over_inertance);
    move |incident| {
        let pressure = (2.0 * incident - impedance * inertance_flow) / denominator;
        inertance_flow += step_over_inertance * pressure;
        pressure
    }
}

fn render(
    rate: f64,
    count: usize,
    at: usize,
    volume: f64,
    mut step: impl FnMut(f64) -> Sample,
) -> Result<(), Box<dyn Error>> {
    let mut output = BufWriter::new(io::stdout().lock());
    writeln!(
        output,
        "sample,inlet_flow_cm3_s,inlet_pressure_dyn_cm2,outlet_pressure_dyn_cm2,radiation_flow_cm3_s,radiation_flow_derivative_cm3_s2"
    )?;
    for n in 0..count {
        let input = if n == at { rate * volume } else { 0.0 };
        let [inlet_pressure, outlet_pressure, flow, derivative] = step(input);
        writeln!(
            output,
            "{n},{input},{inlet_pressure},{outlet_pressure},{flow},{derivative}"
        )?;
    }
    output.flush()?;
    Ok(())
}

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    let [mode, rate, count, at, volume, cells, rest @ ..] = args.as_slice() else {
        return Err("方式、レート、点数、注入位置、体積、区間数を指定してください".into());
    };
    let rate: f64 = rate.parse()?;
    let cells: usize = cells.parse()?;
    let (count, at, volume) = (count.parse()?, at.parse()?, volume.parse()?);
    match (mode.as_str(), rest) {
        ("fdtd", [length, area, viscosity]) => render(
            rate,
            count,
            at,
            volume,
            upstream(
                rate,
                cells,
                length.parse()?,
                area.parse()?,
                viscosity.parse()?,
            ),
        ),
        ("waveguide", [impedance, inertance, resistance]) => {
            let z = impedance.parse()?;
            let outlet = radiation(rate, z, inertance.parse()?, resistance.parse()?);
            render(
                rate,
                count,
                at,
                volume,
                waveguide(rate, cells, z, 1.0, outlet),
            )
        }
        ("legacy", [inlet, outlet]) => {
            let reflection: f64 = outlet.parse()?;
            render(
                rate,
                count,
                at,
                volume,
                waveguide(rate, cells, 1.0, inlet.parse()?, |p| p * (1.0 + reflection)),
            )
        }
        _ => Err("指定した方式と終端の引数が一致しません".into()),
    }
}
