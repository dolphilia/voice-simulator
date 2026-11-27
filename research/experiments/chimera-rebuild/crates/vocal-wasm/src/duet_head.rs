//! 保存された調音行を発声器の時間更新を通さず形状へ戻す。

use std::{cell::RefCell, ptr};
use vocal_core::{
    anatomy::{Articulation, BodyMix, Point, SagittalModel},
    articulators::ARTICULATOR_COUNT,
};

struct Head {
    model: SagittalModel,
    scale: f64,
    axes: [f64; ARTICULATOR_COUNT],
    coordinates: Vec<f64>,
}

thread_local! {
    // 声部ごとに独立した WebAssembly インスタンスを使う。
    static HEAD: RefCell<Option<Head>> = const { RefCell::new(None) };
}

#[unsafe(no_mangle)]
pub extern "C" fn vocal_duet_head_init(female: f64, child: f64) -> *mut f64 {
    if ![female, child]
        .into_iter()
        .all(|value| (0.0..=1.0).contains(&value))
    {
        return ptr::null_mut();
    }
    let mix = BodyMix::new(female, child);
    HEAD.with_borrow_mut(|head| {
        head.insert(Head {
            model: SagittalModel::new(mix),
            scale: mix.parameters().scale,
            axes: [0.0; ARTICULATOR_COUNT],
            coordinates: Vec::new(),
        })
        .axes
        .as_mut_ptr()
    })
}

#[unsafe(no_mangle)]
pub extern "C" fn vocal_duet_head_compute() -> usize {
    HEAD.with_borrow_mut(|slot| {
        let Some(head) = slot.as_mut() else {
            return 0;
        };
        if !head.axes.iter().all(|value| value.is_finite()) {
            return 0;
        }
        let frame = head
            .model
            .compute(Articulation::from_axis_values(head.axes));
        let paths: [&[Point]; 11] = [
            &frame.outer,
            &frame.inner,
            &frame.tongue,
            &frame.velum,
            &frame.upper_lip,
            &frame.lower_lip,
            &frame.upper_teeth,
            &frame.lower_teeth,
            &frame.jaw_bone,
            &frame.epiglottis,
            head.model.nasal_cavity(),
        ];
        let output = &mut head.coordinates;
        output.clear();
        output.extend([
            head.scale,
            frame.lip_width_cm,
            frame.glottis.x,
            frame.glottis.y,
        ]);
        for path in paths {
            output.push(path.len() as f64);
            for point in path {
                output.extend([point.x, point.y]);
            }
        }
        // 輪郭と同じ姿勢で計算した、接触補正後の測定線。
        if let Ok(profile) = head.model.area_profile(&frame) {
            output.push(profile.samples.len() as f64);
            for sample in profile.samples {
                output.extend_from_slice(&sample.measurement_values());
            }
        } else {
            output.push(0.0);
        }
        if output.iter().all(|value| value.is_finite()) {
            output.len()
        } else {
            0
        }
    })
}

#[unsafe(no_mangle)]
pub extern "C" fn vocal_duet_head_points() -> *const f64 {
    HEAD.with_borrow(|head| {
        head.as_ref()
            .map_or(ptr::null(), |head| head.coordinates.as_ptr())
    })
}
