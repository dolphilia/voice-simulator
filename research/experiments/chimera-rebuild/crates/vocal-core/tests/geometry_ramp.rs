use vocal_core::airway::network::{AirwayNetwork, Boundaries, Port, Section};

#[test]
fn immediate_port_update_keeps_other_geometry_ramps_active() {
    let section = Section {
        length_cm: 0.5,
        area_cm2: 1.0,
        minimum_area_cm2: 1.0,
        perimeter_factor: 1.0,
        viscous_factor: 1.0,
        wall: None,
    };
    let port = Port {
        nodes: [0, 1],
        length_cm: 0.5,
        area_cm2: 0.0,
        entrance_loss: 0.0,
        expansion_loss: 0.0,
        slit_width_cm: 0.0,
        include_half_sections: true,
        extra_resistance: 0.0,
    };
    let mut network = AirwayNetwork::new(
        96_000,
        &[section; 3],
        &[],
        Boundaries {
            radiation_nodes: &[],
            fixed_pressure_nodes: &[],
            ports: &[
                port,
                Port {
                    nodes: [0, 2],
                    ..port
                },
            ],
        },
    )
    .unwrap();

    let areas = [[1.5, 1.0], [1.0, 1.0], [1.0, 1.0]];
    network
        .set_geometry_targets(&areas, Some(&[0.75, 0.5, 0.5]), &[(0, 0.5), (1, 0.5)], 2)
        .unwrap();
    network.step(0, 0.0);
    assert_eq!(network.section(0).length_cm, 0.625);
    assert_eq!(network.port_area(0), Some(0.25));
    assert_eq!(network.port_area(1), Some(0.25));

    // 失敗した次の目標設定が、進行中の補間と衝突しないことを調べる。
    assert!(
        network
            .set_geometry_targets(&areas, Some(&[0.1, 0.5, 0.5]), &[(0, 0.0)], 2)
            .is_err()
    );
    network.set_port_area(0, 0.125).unwrap();
    network.step(0, 0.0);
    assert_eq!(network.section(0).length_cm, 0.75);
    assert_eq!(network.section(0).area_cm2, 1.5);
    assert_eq!(network.port_area(0), Some(0.125));
    assert_eq!(network.port_area(1), Some(0.5));

    network.step(0, 0.0);
    assert_eq!(network.section(0).length_cm, 0.75);
    assert_eq!(network.port_area(1), Some(0.5));
}
