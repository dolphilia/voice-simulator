use vocal_core::airway::{TubeGeometry, UniformTube, WallParameters};

const REFERENCE_TUBE: TubeGeometry = TubeGeometry {
    length_cm: 17.5,
    area_cm2: 3.0,
    cells: 40,
    sample_rate_hz: 96_000,
};

#[test]
fn undriven_tube_stays_at_rest() {
    let mut tube = UniformTube::new(REFERENCE_TUBE).unwrap();
    for _ in 0..256 {
        let obs = tube.step(0.0);
        assert_eq!(obs.inlet_pressure_dyn_cm2, 0.0);
        assert_eq!(obs.outlet_pressure_dyn_cm2, 0.0);
        assert_eq!(obs.radiation_flow_cm3_s, 0.0);
        assert_eq!(obs.radiation_flow_derivative_cm3_s2, 0.0);
    }
}

#[test]
fn rejects_unstable_time_step() {
    let slow_geometry = TubeGeometry {
        sample_rate_hz: 48_000,
        ..REFERENCE_TUBE
    };
    assert!(UniformTube::new(slow_geometry).is_err());
}

#[test]
fn wall_radiation_weights_output_without_changing_acoustic_state() {
    let wall = WallParameters {
        mass_g_cm2: 1.5,
        resistance_dyn_s_cm3: 1600.0,
        stiffness_dyn_cm3: 300_000.0,
        radiation_fraction: 0.0,
    };
    let mut no_wall_radiation = UniformTube::with_wall(REFERENCE_TUBE, wall).unwrap();
    let mut wall_radiation = UniformTube::with_wall(
        REFERENCE_TUBE,
        WallParameters {
            radiation_fraction: 0.25,
            ..wall
        },
    )
    .unwrap();
    let mut seen_wall_motion = false;
    for index in 0..256 {
        let drive = if index == 0 { 96_000.0 } else { 0.0 };
        let dry = no_wall_radiation.step(drive);
        let radiating = wall_radiation.step(drive);
        let observations = radiating.wall.unwrap();
        seen_wall_motion |= observations.total_wall_flow_cm3_s != 0.0;
        assert_eq!(dry.inlet_pressure_dyn_cm2, radiating.inlet_pressure_dyn_cm2);
        assert_eq!(
            dry.outlet_pressure_dyn_cm2,
            radiating.outlet_pressure_dyn_cm2
        );
        assert_eq!(
            observations.wall_radiation_flow_cm3_s,
            0.25 * observations.total_wall_flow_cm3_s
        );
        assert_eq!(
            radiating.radiation_flow_cm3_s,
            dry.radiation_flow_cm3_s + observations.wall_radiation_flow_cm3_s
        );
    }
    assert!(seen_wall_motion);
}
