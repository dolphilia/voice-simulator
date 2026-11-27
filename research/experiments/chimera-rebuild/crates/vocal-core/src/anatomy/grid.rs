//! 輪郭から隙間を測る半極座標格子。配置と係数はCHIMERA由来（MIT）。

use super::{Point, RADIANS, SagittalFrame, SagittalModel, direction};

const MAX_RAY_CROSSINGS: usize = 64;
const REAR_RAYS: u32 = 12;
const FAN_RAYS: u32 = 31;
const FRONT_RAYS: u32 = 6;
pub const MAX_MEASUREMENT_RAYS: usize = (REAR_RAYS + FAN_RAYS + FRONT_RAYS) as usize;

#[derive(Clone, Copy, Debug)]
#[repr(u8)]
pub enum Region {
    Pharynx = 1,
    Oral = 2,
    Front = 3,
}

#[derive(Clone, Copy, Debug)]
pub struct GridSample {
    pub inner: Point,
    pub outer: Point,
    pub mid: Point,
    pub gap_cm: f64,
    pub region: Region,
}

impl GridSample {
    fn new(inner: Point, outer: Point, gap_cm: f64, region: Region) -> Self {
        Self {
            inner,
            outer,
            mid: inner.mix(outer, 0.5),
            gap_cm,
            region,
        }
    }
}

impl SagittalModel {
    pub fn measurement_grid(&self, frame: &SagittalFrame) -> Vec<GridSample> {
        let mut samples = Vec::new();
        self.measurement_grid_into(frame, &mut samples);
        samples
    }

    pub(super) fn measurement_grid_into(
        &self,
        frame: &SagittalFrame,
        samples: &mut Vec<GridSample>,
    ) {
        #[cfg(all(not(target_arch = "wasm32"), feature = "render-allocation-probe"))]
        let _allocation = super::allocation_scope(super::AllocationPhase::MeasurementGrid);
        samples.clear();
        samples.reserve(MAX_MEASUREMENT_RAYS);
        let k = self.body.scale;
        let sample = |ray, region, limit, fan| measure(ray, frame, region, limit * k, fan, k);
        let back_center = self.body.point(2.6, 6.95);
        let front_center = self.body.point(5.0, 6.85);
        let start_y = frame.glottis.y + self.body.epilarynx_length_cm() + 0.12 * k;
        samples.extend((0..REAR_RAYS).filter_map(|index| {
            let height = interpolate(
                start_y,
                back_center.y,
                f64::from(index) / f64::from(REAR_RAYS),
            );
            let ray = Ray {
                origin: Point::new(4.6 * k, height),
                direction: Point::new(-1.0, 0.0),
            };
            sample(ray, Region::Pharynx, 9.0, false)
        }));
        samples.extend((0..FAN_RAYS).filter_map(|index| {
            let fraction = f64::from(index) / f64::from(FAN_RAYS - 1);
            let angle = interpolate(180.0, 36.0, fraction);
            let origin = back_center.mix(front_center, smoothstep((fraction - 0.45) / 0.55));
            let ray = Ray {
                origin,
                direction: direction(angle * RADIANS),
            };
            let region = if angle > 150.0 {
                Region::Pharynx
            } else {
                Region::Oral
            };
            sample(ray, region, 8.0, true)
        }));

        let lower_lip = frame.lower_lip[super::INNER_LIP_POINTS - 1];
        let upper_lip = frame.upper_lip[super::INNER_LIP_POINTS - 1];
        let x_start = self.palate[self.palate.len() - 1].x + 0.03 * k;
        let x_end = (x_start + 0.3 * k).max(lower_lip.x.min(upper_lip.x) - 0.04 * k);
        samples.extend((0..FRONT_RAYS).filter_map(|index| {
            let x = interpolate(x_start, x_end, f64::from(index) / f64::from(FRONT_RAYS - 1));
            let ray = Ray {
                origin: Point::new(x, 4.0 * k),
                direction: Point::new(0.0, 1.0),
            };
            let measured = sample(ray, Region::Front, 8.0, false)?;
            let forward = x - lower_lip.x;
            if forward <= 0.0 {
                return Some(measured);
            }
            // 下唇の端より前は外面を延長し、引き込みの進行とともに開口を広げる。
            let edge_face_y = (lower_lip.y - forward * 4.0 / 3.0).min(measured.outer.y);
            let open = smoothstep((frame.labiodental - 0.7) / (1.0 - 0.7))
                * smoothstep(forward / (0.1 * k));
            let y = interpolate(edge_face_y, measured.outer.y - 3.5 * k, open);
            Some(GridSample::new(
                Point::new(x, y),
                measured.outer,
                measured.outer.y - y,
                Region::Front,
            ))
        }));
    }
}

#[derive(Clone, Copy)]
struct Ray {
    origin: Point,
    direction: Point,
}

#[derive(Clone, Copy)]
struct Crossing {
    distance: f64,
    leaves_tissue: bool,
}

impl Ray {
    fn point_at(self, distance: f64) -> Point {
        self.origin + self.direction * distance
    }

    fn crossings(self, contour: &[Point], limit: f64) -> impl Iterator<Item = Crossing> + '_ {
        contour
            .windows(2)
            .filter_map(move |segment| {
                let a = segment[0] - self.origin;
                let b = segment[1] - self.origin;
                // 線上の頂点は正側に含める。かすめるときの入口と出口が対になる。
                if (cross(self.direction, a) >= 0.0) == (cross(self.direction, b) >= 0.0) {
                    return None;
                }
                let edge = segment[1] - segment[0];
                let determinant = cross(self.direction, edge);
                if determinant.abs() < 1e-15 {
                    return None;
                }
                let distance = cross(a, edge) / determinant;
                (distance >= 0.0 && distance <= limit).then_some(Crossing {
                    distance,
                    leaves_tissue: determinant < 0.0,
                })
            })
            .take(MAX_RAY_CROSSINGS)
    }

    fn nearest(self, contour: &[Point], limit: f64) -> Option<f64> {
        self.crossings(contour, limit)
            .map(|hit| hit.distance)
            .reduce(f64::min)
    }

    #[cfg(feature = "labial-crossing-thickness")]
    fn lower_lip_floor(self, inner: &[Point], lip: &[Point], roof: f64, far: f64) -> Option<f64> {
        let mut hits = self.crossings(inner, far).filter(|hit| hit.distance < far);
        let (Some(a), Some(b), Some(c), None) =
            (hits.next(), hits.next(), hits.next(), hits.next())
        else {
            return None;
        };
        let mut hits = [a, b, c];
        hits.sort_by(|a, b| a.distance.total_cmp(&b.distance));
        let [base, lower, higher] = hits;
        let (entry, exit) = if higher.leaves_tissue {
            (lower, higher)
        } else {
            (higher, lower)
        };
        if !base.leaves_tissue
            || entry.leaves_tissue
            || !exit.leaves_tissue
            || entry.distance > exit.distance
            || exit.distance >= roof
        {
            return None;
        }

        // 下唇内面の進入〜退出だけを組織の厚さとして数える。
        let matches = |hit: Crossing| {
            self.crossings(lip, roof)
                .any(|lip| lip.leaves_tissue == hit.leaves_tissue && lip.distance == hit.distance)
        };
        (matches(entry) && matches(exit))
            .then_some(base.distance + (exit.distance - entry.distance))
    }

    fn fan_floor(self, inner: &[Point], roof: f64, scale: f64) -> f64 {
        let far = roof + 1.5 * scale;
        let mut hits = [Crossing {
            distance: 0.0,
            leaves_tissue: false,
        }; MAX_RAY_CROSSINGS];
        let mut count = 0;
        for (index, hit) in self.crossings(inner, far).enumerate() {
            let mut pos = index;
            // 等距離では移動しない。+0.0と-0.0も同じ距離として扱う。
            while pos > 0 && hits[pos - 1].distance > hit.distance {
                hits[pos] = hits[pos - 1];
                pos -= 1;
            }
            hits[pos] = hit;
            count = index + 1;
        }
        let hits = &hits[..count];
        let (floor, start) = if let Some(first) = hits.first().filter(|hit| hit.leaves_tissue) {
            (first.distance, 1)
        } else {
            let reversed = Ray {
                origin: self.origin,
                direction: self.direction * -1.0,
            };
            let back = 2.5 * scale;
            (-reversed.nearest(inner, back).unwrap_or(back), 0)
        };
        let mut tissue_cm = 0.0;
        let mut remaining = &hits[start..];
        while let Some(entry) = remaining.first().filter(|hit| hit.distance < roof) {
            if entry.leaves_tissue {
                remaining = &remaining[1..];
            } else {
                let end = remaining.get(1).map_or(far, |hit| hit.distance).min(roof);
                tissue_cm += end - entry.distance;
                remaining = &remaining[remaining.len().min(2)..];
            }
        }
        floor + tissue_cm
    }
}

fn measure(
    ray: Ray,
    frame: &SagittalFrame,
    region: Region,
    limit: f64,
    fan: bool,
    scale: f64,
) -> Option<GridSample> {
    let roof = ray.nearest(&frame.outer, limit)?;
    let floor = if fan {
        ray.fan_floor(&frame.inner, roof, scale)
    } else {
        let limit = roof + 1.5 * scale;
        ray.crossings(&frame.inner, limit)
            .map(|hit| hit.distance)
            .filter(|&distance| distance < limit)
            .reduce(f64::max)
            .unwrap_or_else(|| (roof - 3.5 * scale).max(0.0))
    };
    #[cfg(feature = "labial-crossing-thickness")]
    let floor = if matches!(region, Region::Front)
        && ray.origin.x <= frame.lower_lip[super::INNER_LIP_POINTS - 1].x
    {
        ray.lower_lip_floor(
            &frame.inner,
            &frame.lower_lip[..super::INNER_LIP_POINTS],
            roof,
            roof + 1.5 * scale,
        )
        .unwrap_or(floor)
    } else {
        floor
    };
    Some(GridSample::new(
        ray.point_at(floor.min(roof)),
        ray.point_at(roof),
        (roof - floor).max(0.0),
        region,
    ))
}

fn cross(a: Point, b: Point) -> f64 {
    a.x * b.y - a.y * b.x
}

fn interpolate(a: f64, b: f64, t: f64) -> f64 {
    a + (b - a) * t
}

pub(super) fn smoothstep(t: f64) -> f64 {
    let t = t.clamp(0.0, 1.0);
    t * t * (3.0 - 2.0 * t)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::anatomy::Articulation;

    const RAY: Ray = Ray {
        origin: Point::new(0.0, -5.0),
        direction: Point::new(0.0, 1.0),
    };

    #[test]
    fn measurement_grid_reuses_storage_after_a_frame_with_no_crossings() {
        let model = SagittalModel::adult_male();
        let mut frame = model.frame_buffer();
        model.compute_into(Articulation::neutral(), &mut frame);
        frame.inner.clear();
        frame
            .inner
            .extend([Point::new(2.0, -100.0), Point::new(2.0, 100.0)]);
        frame.outer.clear();
        frame
            .outer
            .extend([Point::new(1.0, -100.0), Point::new(1.0, 100.0)]);

        let mut samples = Vec::new();
        model.measurement_grid_into(&frame, &mut samples);
        let storage = samples.as_ptr();
        assert!(samples.len() <= MAX_MEASUREMENT_RAYS);
        for sample in &samples[..REAR_RAYS as usize] {
            assert!((sample.gap_cm - 1.0).abs() < 1e-12);
        }

        frame.outer.clear();
        model.measurement_grid_into(&frame, &mut samples);
        assert!(samples.is_empty());
        assert_eq!(storage, samples.as_ptr());

        frame
            .outer
            .extend([Point::new(0.75, -100.0), Point::new(0.75, 100.0)]);
        model.measurement_grid_into(&frame, &mut samples);
        assert_eq!(storage, samples.as_ptr());
        for sample in &samples[..REAR_RAYS as usize] {
            assert!(matches!(sample.region, Region::Pharynx));
            assert!((sample.gap_cm - 1.25).abs() < 1e-12);
            assert!((sample.mid.x - 1.375).abs() < 1e-12);
        }
    }

    #[test]
    fn grazing_vertex_has_no_unpaired_crossings() {
        for side in [-1.0, 1.0] {
            let touch = [
                Point::new(side, -1.0),
                Point::new(0.0, 0.0),
                Point::new(side, 1.0),
            ];
            let hits: Vec<_> = RAY.crossings(&touch, 10.0).collect();
            if let [entry, exit] = hits.as_slice() {
                assert_eq!(entry.distance, exit.distance);
                assert_ne!(entry.leaves_tissue, exit.leaves_tissue);
            } else {
                assert!(hits.is_empty());
            }
        }
        let through = [
            Point::new(-1.0, -1.0),
            Point::new(0.0, 0.0),
            Point::new(1.0, 1.0),
        ];
        assert_eq!(RAY.crossings(&through, 10.0).count(), 1);
    }

    #[test]
    fn fan_excludes_a_second_layer_of_tissue() {
        let inner = [
            Point::new(-1.0, 0.0),
            Point::new(1.0, 0.0),
            Point::new(1.0, 1.0),
            Point::new(-1.0, 1.0),
            Point::new(-1.0, 2.0),
            Point::new(1.0, 2.0),
        ];
        // 最初の出口は距離5 cm。途中の組織1 cm分を内側の測定点に加える。
        assert_eq!(RAY.fan_floor(&inner, 9.0, 1.0), 6.0);
    }

    #[cfg(feature = "labial-crossing-thickness")]
    #[test]
    fn lip_fold_counts_thickness_and_keeps_the_contact_rule() {
        let inner = [
            Point::new(-1.0, 0.0),
            Point::new(1.0, 0.0),
            Point::new(1.0, 1.0),
            Point::new(-1.0, 1.0),
            Point::new(-1.0, 2.0),
            Point::new(1.0, 2.0),
        ];
        assert_eq!(
            RAY.lower_lip_floor(&inner, &inner[2..], 9.0, 10.5),
            Some(6.0)
        );
        assert_eq!(RAY.lower_lip_floor(&inner, &inner[2..], 7.0, 8.5), None);
        assert_eq!(RAY.lower_lip_floor(&inner, &inner[3..], 9.0, 10.5), None);

        let touch = [
            inner[0],
            inner[1],
            inner[2],
            Point::new(0.0, 2.0),
            Point::new(1.0, 3.0),
        ];
        assert_eq!(
            RAY.lower_lip_floor(&touch, &touch[2..], 9.0, 10.5),
            Some(5.0)
        );
    }

    #[test]
    fn fan_keeps_contour_order_at_equal_distances() {
        let a = Point::new(-1.0, 0.0);
        let b = Point::new(1.0, 0.0);
        // 退出が先なら距離5 cmから外壁までの組織を足す。
        assert_eq!(RAY.fan_floor(&[a, b, a], 9.0, 1.0), 9.0);
        // 進入が先なら厚さは0 cmで、逆向きの探索は−2.5 cmに達する。
        assert_eq!(RAY.fan_floor(&[b, a, b], 9.0, 1.0), -2.5);
    }

    #[test]
    fn fan_limits_crossings_before_sorting_and_handles_no_crossing() {
        // 65件の交差を作り、64件目の進入を退出のない層として扱う。
        let inner: [Point; 66] = std::array::from_fn(|i| {
            let x = if i % 2 == 0 { -1.0 } else { 1.0 };
            // 65件目は手前へ折り返すので、距離で並べ替える前の打ち切りが必要。
            let y = if i == 65 { -63.0 } else { i as f64 };
            Point::new(x, y)
        });
        assert_eq!(RAY.crossings(&inner, 81.5).count(), 64);
        assert_eq!(RAY.fan_floor(&inner, 80.0, 1.0), 48.0);
        assert_eq!(RAY.fan_floor(&[], 9.0, 1.0), -2.5);
    }
}
