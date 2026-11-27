//! 固定上流版の公開状態から、軟壁一様管の比較用系列を取り出す。

use chimera::airway::network::{AirwayNetwork, Area, TubeSpec};
use chimera::physics::WallParams;
use std::error::Error;
use std::io::{self, BufWriter, Write};

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    let [
        rate,
        length,
        area,
        cells,
        impulse_at,
        volume,
        samples,
        mass,
        resistance,
        stiffness,
        fraction,
    ] = args.as_slice()
    else {
        return Err("軟壁の比較ケースの11項目を指定してください".into());
    };
    let rate: f64 = rate.parse()?;
    let impulse_at: usize = impulse_at.parse()?;
    let volume: f64 = volume.parse()?;
    let samples: usize = samples.parse()?;
    let fraction: f64 = fraction.parse()?;
    let wall = WallParams {
        mass: mass.parse()?,
        resistance: resistance.parse()?,
        stiffness: stiffness.parse()?,
    };
    let mut network = AirwayNetwork::new(rate);
    let tube = network.add_tube(
        TubeSpec::new(
            "probe",
            cells.parse()?,
            length.parse()?,
            Area::Uniform(area.parse()?),
        )
        .wall(Some(wall))
        .radiating(fraction),
    );
    let inlet = tube.first_node();
    let outlet = tube.last_node();
    let radiation = network.add_radiation(outlet);
    network.finalize();
    network.begin_block(1);
    let mut output = BufWriter::new(io::stdout().lock());
    writeln!(
        output,
        "sample,inlet_flow_cm3_s,inlet_pressure_dyn_cm2,outlet_pressure_dyn_cm2,radiation_flow_cm3_s,radiation_flow_derivative_cm3_s2,inlet_wall_flow_cm3_s,outlet_wall_flow_cm3_s,total_wall_flow_cm3_s,wall_radiation_flow_cm3_s,inlet_branch_flow_cm3_s,outlet_branch_flow_cm3_s"
    )?;
    for sample in 0..samples {
        let input = if sample == impulse_at {
            volume * rate
        } else {
            0.0
        };
        network.ext_flow[inlet] = input;
        let derivative = network.step();
        let wall_total: f64 = network.wall_u.iter().sum();
        let wall_radiation: f64 = network.wall_u.iter().map(|flow| flow * fraction).sum();
        let flow = network.radiated_flow(radiation) + wall_radiation;
        writeln!(
            output,
            "{sample},{input},{},{},{flow},{derivative},{},{},{wall_total},{wall_radiation},{},{}",
            network.p[inlet],
            network.p[outlet],
            network.wall_u[inlet],
            network.wall_u[outlet],
            network.u[tube.branch(0)],
            network.u[tube.branch(tube.n - 2)]
        )?;
    }
    output.flush()?;
    Ok(())
}
