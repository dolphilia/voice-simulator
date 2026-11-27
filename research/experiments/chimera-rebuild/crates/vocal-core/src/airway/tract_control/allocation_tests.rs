use std::{
    alloc::{GlobalAlloc, Layout, System},
    cell::Cell,
    hint::black_box,
};

use serde_json::{Value, json};

use super::{SagittalModel, TractSampling};
use crate::{
    anatomy::{Articulation, BodyName, Point},
    phonetics::{ipa_plan, speech::male_speech_gestures},
    voice::{ArticulatedVoice, FixedVoiceSettings},
};

struct CountingAllocator;

thread_local! {
    static ALLOCATIONS: Cell<usize> = const { Cell::new(0) };
}

#[global_allocator]
static ALLOCATOR: CountingAllocator = CountingAllocator;

unsafe impl GlobalAlloc for CountingAllocator {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let _ = ALLOCATIONS.try_with(|count| count.set(count.get() + 1));
        unsafe { System.alloc(layout) }
    }

    unsafe fn realloc(&self, ptr: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        let _ = ALLOCATIONS.try_with(|count| count.set(count.get() + 1));
        unsafe { System.realloc(ptr, layout, size) }
    }

    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        unsafe { System.dealloc(ptr, layout) }
    }
}

fn counted<T>(call: impl FnOnce() -> T) -> (T, usize) {
    let before = ALLOCATIONS.with(Cell::get);
    let value = black_box(call());
    (value, ALLOCATIONS.with(Cell::get) - before)
}

#[test]
fn profile_geometry_allocations() {
    let study: Value = serde_json::from_str(include_str!(
        "../../../../../cases/contour-buffer-reuse.json"
    ))
    .unwrap();
    let input: Value =
        serde_json::from_str(include_str!("../../../../../cases/bilabial-p.json")).unwrap();
    let input = &input["speech_voice"];
    let setup = &study["inputs"];
    let p = &input["posture"];
    let scalar = |name: &str| p[name].as_f64().unwrap_or(0.0);
    let point = |name: &str| Point::new(p[name][0].as_f64().unwrap(), p[name][1].as_f64().unwrap());
    let posture = Articulation {
        jaw_cm: scalar("jaw_cm"),
        tongue_body_cm: point("tongue_body_cm"),
        tongue_tip_cm: point("tongue_tip_cm"),
        tongue_root_cm: scalar("tongue_root_cm"),
        tip_curl: scalar("tip_curl"),
        dorsum: scalar("dorsum"),
        lip_aperture_cm: scalar("lip_aperture_cm"),
        lip_protrusion_cm: scalar("lip_protrusion_cm"),
        lip_spread: scalar("lip_spread"),
        labiodental: scalar("labiodental"),
        velum_cm2: scalar("velum_cm2"),
        larynx_cm: scalar("larynx_cm"),
        lateral: scalar("lateral"),
        epilarynx: scalar("epilarynx"),
        ventricular: scalar("ventricular"),
    };
    let voice_cfg = |name: &str| input["voice"][name].as_f64().unwrap();
    let settings = FixedVoiceSettings {
        pressure_cm_h2o: voice_cfg("pressure_cm_h2o"),
        gate: voice_cfg("gate"),
        f0_hz: voice_cfg("f0_hz"),
        breathiness: voice_cfg("breathiness"),
        tension: voice_cfg("tension"),
    };
    let internal_rate = setup["internal_rate_hz"].as_u64().unwrap() as u32;
    let control_samples = setup["control_internal_samples"].as_u64().unwrap();
    assert_eq!(
        input["internal_sample_rate_hz"].as_u64(),
        Some(u64::from(internal_rate))
    );
    let mut voice =
        ArticulatedVoice::for_speech(internal_rate, control_samples as usize, posture, settings)
            .unwrap();
    let plan = ipa_plan::plan(
        input["input"]["text"].as_str(),
        None,
        setup["start_seconds"].as_f64(),
        input["input"]["rate"].as_f64().unwrap(),
    )
    .unwrap();
    assert_eq!(plan.utterances.len(), 1);
    let utterance = &plan.utterances[0];
    voice
        .set_score(
            male_speech_gestures(&utterance.timing, utterance.start_seconds, settings.f0_hz)
                .unwrap(),
        )
        .unwrap();

    let model = SagittalModel::adult_male();
    let sampling = TractSampling::for_body(internal_rate, BodyName::Male.parameters()).unwrap();
    let mut frame = model.frame_buffer();
    let mut rows = Vec::new();
    let mut cursor = 0;
    for tick in setup["profile_control_frames"].as_array().unwrap() {
        let tick = tick.as_u64().unwrap();
        let target = tick * control_samples;
        for _ in cursor..target {
            voice.step().unwrap();
        }
        let (_, control) = counted(|| voice.step().unwrap());
        cursor = target + 1;
        let posture = voice.articulators().posture();
        let (_, contour) = counted(|| {
            model.compute_into(posture, &mut frame);
            black_box(&frame);
        });
        let (contacts, contact) = counted(|| model.contact_grid(&frame));
        let (profile, area) = counted(|| {
            model
                .area_profile_from_contacts(&frame, &contacts.samples)
                .unwrap()
        });
        let (raw, resample) = counted(|| sampling.resample(&profile).unwrap());
        let (_, copy_limited) = counted(|| raw.clone());
        rows.push(json!({
            "control_frame": tick,
            "internal_sample": target,
            "posture": format!("{posture:?}"),
            "control_step": control,
            "contour": contour,
            "contact": contact,
            "area": area,
            "resample": resample,
            "copy_limited": copy_limited,
        }));
    }
    println!("tract_stage_allocations={}", json!(rows));
}
