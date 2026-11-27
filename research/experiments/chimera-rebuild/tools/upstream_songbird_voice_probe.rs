//! 上流の公開レンダーと、同じ制御値を受け取る観測用気道を進める。

use chimera::airway::decimator::Decimator;
use chimera::creatures::{CreatureVoice, songbird};
use chimera::math::{PI, exp};
use serde_json::Value;
use std::env;
use std::fs;
use std::io::{self, BufWriter, Write};

fn parameters(input: &Value) -> [(usize, f64); 9] {
    let keys = [
        "pitch_hz",
        "interval_semitones",
        "voices",
        "drive",
        "tension",
        "pressure_kpa",
        "purity",
        "oec_cm3",
        "gape",
    ];
    std::array::from_fn(|index| {
        (
            index,
            input[keys[index]].as_f64().expect("比較ケースの制御値"),
        )
    })
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let input = env::args().nth(1).ok_or("比較ケースが必要です")?;
    if input == "--flute-definition" || input == "--songbird-definitions" {
        let definition = songbird::def();
        let output = io::stdout().lock();
        if input == "--flute-definition" {
            serde_json::to_writer(
                output,
                &definition.calls[definition.call_index("flute").unwrap()],
            )?;
        } else {
            serde_json::to_writer(output, &definition.calls)?;
        }
        return Ok(());
    }
    let observe_syrinx = env::args().nth(2).as_deref() == Some("--observe-syrinx");
    let json: Value = serde_json::from_slice(&fs::read(input)?)?;
    let case = &json["songbird_voice"];
    let rate = case["sample_rate_hz"].as_f64().ok_or("レートが必要です")?;
    let frames = case["frames"].as_u64().ok_or("フレーム数が必要です")? as usize;
    let level = case["level"].as_f64().ok_or("レベルが必要です")?;
    let events = case["events"].as_array().ok_or("イベント列が必要です")?;
    let observe_call_id = case["observe_call_id"] == true;
    let observe_call = observe_call_id
        || events
            .iter()
            .any(|event| event["play_call"].is_object() || event["stop_call"] == true);
    let mut events = events.iter().peekable();
    let def = Box::leak(Box::new(songbird::def()));
    let mut voice = CreatureVoice::new(def, rate, &parameters(&case["controls"]));
    voice.level = level;
    let mut telemetry = voice.new_telemetry();
    let factor = (voice.fs / rate) as usize;
    let block = 64 * factor;
    let dt = block as f64 / voice.fs;
    let mut observer = def.create(voice.fs);
    let gain = observer.gain() * level;
    observer.control(voice.values(), 0.0, dt);
    let tube = |name| {
        observer
            .tubes()
            .iter()
            .find(|(id, _)| *id == name)
            .map(|(_, tube)| *tube)
    };
    let syrinx_nodes = [
        tube("bronchusL").ok_or("左気管支がありません")?.last_node(),
        tube("bronchusR").ok_or("右気管支がありません")?.last_node(),
    ];
    let trachea = tube("trachea").ok_or("気管がありません")?.first_node();
    let net = observer.net_mut().expect("観測用鳴禽の気道");
    let syrinx_ports = if observe_syrinx {
        let graph = net.linear_elements();
        let find = |node| {
            graph
                .a
                .iter()
                .zip(&graph.b)
                .position(|(&a, &b)| a == node && b == trachea)
                .ok_or("鳴管のポートがありません")
        };
        Some([find(syrinx_nodes[0])?, find(syrinx_nodes[1])?])
    } else {
        None
    };
    net.snap_to_targets();
    let sac = net.tubes[net
        .tube_names
        .iter()
        .position(|name| name == "air sac")
        .unwrap()]
    .first_node();
    let mut openings = Vec::with_capacity(2);
    let mut decimator = Decimator::new(factor);
    let pole = exp(-2.0 * PI * 12.0 / rate);
    let (mut previous_input, mut previous_filtered) = (0.0_f64, 0.0_f64);
    let mut output = BufWriter::new(io::stdout().lock());
    write!(
        output,
        concat!(
            "frame,internal_sample,gate,pitch_hz,interval_semitones,voices,drive,tension,",
            "pressure_kpa,purity,oec_cm3,gape,sac_pressure_dyn_cm2,left_opening,right_opening,",
            "radiation_0,radiation_1,radiation_2,radiation_3,decimated,dc_removed,pcm_f32"
        )
    )?;
    if observe_call {
        write!(
            output,
            concat!(
                ",control_clock_seconds,active_call,target_pitch_hz,target_interval_semitones,target_voices,",
                "target_drive,target_tension,target_pressure_kpa,target_purity,target_oec_cm3,target_gape"
            )
        )?;
    }
    if observe_call_id {
        write!(output, ",call_id")?;
    }
    if observe_syrinx {
        write!(
            output,
            concat!(
                ",gate_target,left_port_area_cm2,right_port_area_cm2,",
                "left_port_flow_cm3_s,right_port_flow_cm3_s"
            )
        )?;
    }
    let mut gate_target = 0.0;
    writeln!(output)?;
    for frame in 0..frames {
        if let Some(event) = events.next_if(|event| event["frame"].as_u64() == Some(frame as u64)) {
            if let Some(gate) = event["gate"].as_f64() {
                voice.set_gate(gate);
                gate_target = gate;
            }
            if event["controls"].is_object() {
                voice.set_params(&parameters(&event["controls"]));
            }
            let call = &event["play_call"];
            if let Some(id) = call["id"].as_str() {
                voice.play_call_id(
                    id,
                    call["pitch_hz"].as_f64(),
                    call["amplitude"].as_f64().unwrap_or(1.0),
                );
            }
            if event["stop_call"] == true {
                voice.stop_call();
            }
        }
        // PCMは実際の公開レンダーから取得し、観測用気道は制御境界の値を追う。
        let mut pcm = [0.0_f32];
        voice.render(&mut pcm);
        if frame.is_multiple_of(64) {
            voice.telemetry(&mut telemetry);
            observer.control(voice.values(), telemetry.gate, dt);
            observer
                .net_mut()
                .expect("観測用鳴禽の気道")
                .begin_block(block);
            chimera::airway::network::tiny(&mut previous_input);
            chimera::airway::network::tiny(&mut previous_filtered);
        }
        let mut radiation = [0.0; 4];
        for sample in &mut radiation[..factor] {
            *sample = observer.sample();
            decimator.push(*sample);
        }
        observer.source_state(&mut openings);
        let decimated = decimator.value;
        let scaled = decimated * gain;
        let filtered = scaled - previous_input + pole * previous_filtered;
        previous_input = scaled;
        previous_filtered = filtered;
        write!(
            output,
            "{frame},{},{}",
            (frame + 1) * factor - 1,
            telemetry.gate
        )?;
        for &value in voice.values() {
            write!(output, ",{value}")?;
        }
        let pressure = observer.net().expect("観測用鳴禽の気道").p[sac];
        for value in [pressure, openings[0].1, openings[1].1]
            .into_iter()
            .chain(radiation)
            .chain([decimated, filtered])
        {
            write!(output, ",{value}")?;
        }
        write!(output, ",{}", pcm[0])?;
        if observe_call {
            write!(
                output,
                ",{},{}",
                voice.clock,
                u8::from(voice.active_call().is_some())
            )?;
            for value in voice.targets() {
                write!(output, ",{value}")?;
            }
        }
        if observe_call_id {
            let id = voice
                .active_call()
                .map_or(0, |name| def.call_index(name).unwrap() + 1);
            write!(output, ",{id}")?;
        }
        if let Some([left, right]) = syrinx_ports {
            let net = observer.net().ok_or("観測用鳴禽の気道がありません")?;
            write!(
                output,
                ",{gate_target},{},{},{},{}",
                net.port_area[left], net.port_area[right], net.u[left], net.u[right],
            )?;
        }
        writeln!(output)?;
    }
    output.flush()?;
    Ok(())
}
