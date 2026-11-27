//! 舌と唇の接触モデル。距離の閾値と係数はCHIMERA由来（MIT）。

use super::grid::smoothstep;
use super::{
    GridSample, INNER_LIP_POINTS, MAX_MEASUREMENT_RAYS, Point, Region, SagittalFrame, SagittalModel,
};

#[derive(Clone, Copy, Debug)]
pub struct RoofContact {
    pub distance_cm: f64,
    pub normal: Point,
}

#[derive(Clone, Copy, Debug)]
pub struct ContactSample {
    pub ray: GridSample,
    pub gap_cm: f64,
}

pub struct ContactGrid {
    pub samples: Vec<ContactSample>,
    pub tip: RoofContact,
    pub body: RoofContact,
}

#[derive(Default)]
pub(crate) struct ContactGridScratch {
    roof_cumulative: Vec<f64>,
    rays: Vec<GridSample>,
    pub(crate) samples: Vec<ContactSample>,
}

impl SagittalModel {
    pub fn contact_grid(&self, frame: &SagittalFrame) -> ContactGrid {
        let mut scratch = ContactGridScratch::default();
        let (tip, body) = self.contact_grid_into(frame, &mut scratch);
        ContactGrid {
            samples: scratch.samples,
            tip,
            body,
        }
    }

    pub(crate) fn contact_grid_into(
        &self,
        frame: &SagittalFrame,
        scratch: &mut ContactGridScratch,
    ) -> (RoofContact, RoofContact) {
        #[cfg(all(not(target_arch = "wasm32"), feature = "render-allocation-probe"))]
        let _allocation = super::allocation_scope(super::AllocationPhase::ContactGrid);
        let roof = Roof::new(
            &frame.outer[frame.roof.clone()],
            &mut scratch.roof_cumulative,
        );
        let tip = roof.closest(&frame.tongue[frame.tongue_tip_contact.clone()]);
        let body = roof.closest(&frame.tongue[frame.tongue_body_contact.clone()]);
        let k = self.body.scale;
        let press = fade(-0.06 * k, 0.0, tip.distance_cm.min(body.distance_cm));
        let half_span = 0.1 * k * (1.0 + press);
        let lab_open = smoothstep(frame.labiodental / 0.5);
        let lip_aperture = if lab_open < 1.0 {
            Some(frame.lip_aperture_cm + 0.3 * k * lab_open / (1.0 - lab_open))
        } else {
            None
        };
        let edge = INNER_LIP_POINTS - 1;
        let lip_edge_x = frame.upper_lip[edge].x.min(frame.lower_lip[edge].x);
        let teeth_x = self.palate[self.palate.len() - 1].x;

        self.measurement_grid_into(frame, &mut scratch.rays);
        #[cfg(all(not(target_arch = "wasm32"), feature = "render-allocation-probe"))]
        let _samples_allocation = super::allocation_scope(super::AllocationPhase::ContactSamples);
        scratch.samples.clear();
        scratch.samples.reserve(MAX_MEASUREMENT_RAYS);
        scratch
            .samples
            .extend(scratch.rays.iter().copied().map(|ray| {
                let mut gap_cm = tongue_gap(&roof, &frame.tongue, ray, half_span, k);
                if let Some(aperture) = lip_aperture
                    && matches!(ray.region, Region::Front)
                    && ray.mid.x >= teeth_x
                {
                    let depth = (lip_edge_x - ray.mid.x).max(0.0);
                    gap_cm = gap_cm.min((aperture + depth * depth / (1.2 * k)).max(0.0));
                }
                ContactSample { ray, gap_cm }
            }));

        (tip, body)
    }
}

fn tongue_gap(roof: &Roof<'_>, tongue: &[Point], ray: GridSample, half_span: f64, k: f64) -> f64 {
    let projection = roof.project(ray.outer);
    let on_roof = fade(0.15 * k, 0.25 * k, projection.distance_cm.abs());
    if on_roof == 0.0 {
        return ray.gap_cm;
    }
    let mut gap = signed_polygon_distance(tongue, ray.outer);
    if gap - half_span - projection.distance_cm.abs() <= 0.6 * k {
        for offset in [-1.0, -0.5, 0.5, 1.0] {
            let neighbor = roof.point_at(projection.arc_cm + offset * half_span);
            gap = gap.min(signed_polygon_distance(tongue, neighbor));
        }
    }
    let surface = gap.max(0.0);
    let cap = fade(0.45 * k, 0.6 * k, gap) * on_roof;
    let blend = fade(0.15 * k, 0.6 * k, gap) * on_roof;
    let capped = ray.gap_cm + (ray.gap_cm.min(surface) - ray.gap_cm) * cap;
    capped + (surface - capped) * blend
}

struct Projection {
    distance_cm: f64,
    arc_cm: f64,
    segment: usize,
}

struct Roof<'a> {
    points: &'a [Point],
    cumulative: &'a [f64],
}

impl<'a> Roof<'a> {
    fn new(points: &'a [Point], cumulative: &'a mut Vec<f64>) -> Self {
        #[cfg(all(not(target_arch = "wasm32"), feature = "render-allocation-probe"))]
        let _allocation = super::allocation_scope(super::AllocationPhase::RoofCumulative);
        cumulative.clear();
        cumulative.reserve(points.len());
        cumulative.push(0.0);
        for segment in points.windows(2) {
            cumulative.push(cumulative[cumulative.len() - 1] + (segment[1] - segment[0]).norm());
        }
        Self { points, cumulative }
    }

    fn project(&self, point: Point) -> Projection {
        let mut nearest = Projection {
            distance_cm: f64::INFINITY,
            arc_cm: 0.0,
            segment: 0,
        };
        for (index, segment) in self.points.windows(2).enumerate() {
            let edge = segment[1] - segment[0];
            let l2 = dot(edge, edge);
            if l2 < 1e-12 {
                continue;
            }
            let offset = point - segment[0];
            let t = (dot(offset, edge) / l2).clamp(0.0, 1.0);
            let distance = (point - (segment[0] + edge * t)).norm();
            if distance < nearest.distance_cm.abs() {
                let side = edge.x * offset.y - edge.y * offset.x;
                nearest = Projection {
                    distance_cm: if side < 0.0 { distance } else { -distance },
                    arc_cm: self.cumulative[index] + t * libm::sqrt(l2),
                    segment: index,
                };
            }
        }
        nearest
    }

    fn closest(&self, points: &[Point]) -> RoofContact {
        let nearest = points
            .iter()
            .map(|&point| self.project(point))
            .reduce(|a, b| if b.distance_cm < a.distance_cm { b } else { a })
            .expect("接触を測る舌の点列は空にならない");
        let edge = self.points[nearest.segment + 1] - self.points[nearest.segment];
        let norm = edge.norm();
        let length = if norm.is_finite() && norm > 0.0 {
            norm
        } else {
            1.0
        };
        RoofContact {
            distance_cm: nearest.distance_cm,
            normal: Point::new(edge.y / length, -edge.x / length),
        }
    }

    fn point_at(&self, arc_cm: f64) -> Point {
        let last = self.cumulative.len() - 1;
        let arc_cm = arc_cm.clamp(0.0, self.cumulative[last]);
        let index = self
            .cumulative
            .partition_point(|&s| s < arc_cm)
            .saturating_sub(1)
            .min(last - 1);
        let length = self.cumulative[index + 1] - self.cumulative[index];
        let fraction = if length > 1e-9 {
            ((arc_cm - self.cumulative[index]) / length).clamp(0.0, 1.0)
        } else {
            0.0
        };
        self.points[index].mix(self.points[index + 1], fraction)
    }
}

fn signed_polygon_distance(polygon: &[Point], point: Point) -> f64 {
    let mut nearest_squared = f64::INFINITY;
    let mut inside = false;
    for (&a, &b) in polygon.iter().zip(polygon.iter().cycle().skip(1)) {
        let edge = b - a;
        let offset = point - a;
        let length_squared = dot(edge, edge);
        let t = if length_squared > 1e-12 {
            (dot(offset, edge) / length_squared).clamp(0.0, 1.0)
        } else {
            0.0
        };
        let residual = offset - edge * t;
        nearest_squared = nearest_squared.min(dot(residual, residual));
        if (a.y > point.y) != (b.y > point.y) && point.x < a.x + offset.y * edge.x / edge.y {
            inside = !inside;
        }
    }
    let distance = libm::sqrt(nearest_squared);
    if inside { -distance } else { distance }
}

fn dot(a: Point, b: Point) -> f64 {
    a.x * b.x + a.y * b.y
}

fn fade(lo: f64, hi: f64, value: f64) -> f64 {
    1.0 - smoothstep((value - lo) / (hi - lo))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::anatomy::Articulation;

    #[test]
    fn contact_samples_survive_an_empty_grid_and_reflect_the_next_shape() {
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
        frame.roof = 0..2;
        for point in &mut frame.tongue {
            point.x += 100.0;
        }

        let mut scratch = ContactGridScratch::default();
        model.contact_grid_into(&frame, &mut scratch);
        let storage = scratch.samples.as_ptr();
        assert!((scratch.samples[0].gap_cm - 1.0).abs() < 1e-12);
        let mut area_scratch = Vec::with_capacity(MAX_MEASUREMENT_RAYS);
        let first_profile = model
            .area_profile_from_contacts_reusing(&frame, &scratch.samples, &mut area_scratch)
            .unwrap();
        area_scratch = first_profile.samples;
        let area_storage = area_scratch.as_ptr();

        for point in &mut frame.outer {
            point.x = 1000.0;
        }
        model.contact_grid_into(&frame, &mut scratch);
        assert!(scratch.samples.is_empty());
        assert_eq!(scratch.samples.as_ptr(), storage);
        assert!(matches!(
            model.area_profile_from_contacts_reusing(&frame, &scratch.samples, &mut area_scratch),
            Err("断面を計算できる測定点がありません")
        ));
        assert!(area_scratch.is_empty());
        assert_eq!(area_scratch.as_ptr(), area_storage);

        for point in &mut frame.outer {
            point.x = 0.75;
        }
        model.contact_grid_into(&frame, &mut scratch);
        assert_eq!(scratch.samples.as_ptr(), storage);
        let profile = model
            .area_profile_from_contacts_reusing(&frame, &scratch.samples, &mut area_scratch)
            .unwrap();
        assert_eq!(profile.samples.as_ptr(), area_storage);
        let first = &profile.samples[0];
        assert!(matches!(first.contact.ray.region, Region::Pharynx));
        assert!((first.contact.gap_cm - 1.25).abs() < 1e-12);
        assert!((first.area_cm2 - 2.0 * 1.25_f64.powf(1.4)).abs() < 1e-12);
    }

    #[test]
    fn rebuilding_a_shorter_roof_reuses_only_its_current_distances() {
        let mut cumulative = Vec::new();
        let first = [
            Point::new(0.0, 0.0),
            Point::new(3.0, 0.0),
            Point::new(3.0, 4.0),
            Point::new(9.0, 4.0),
        ];
        let roof = Roof::new(&first, &mut cumulative);
        assert_eq!(roof.cumulative, &[0.0, 3.0, 7.0, 13.0]);
        let buffer = roof.cumulative.as_ptr();
        let shorter = [
            Point::new(0.0, 0.0),
            Point::new(3.0, 4.0),
            Point::new(3.0, 4.0),
        ];
        let roof = Roof::new(&shorter, &mut cumulative);
        assert_eq!(roof.cumulative, &[0.0, 5.0, 5.0]);
        assert_eq!(roof.cumulative.as_ptr(), buffer);
        let middle = roof.point_at(2.5);
        assert_eq!([middle.x, middle.y], [1.5, 2.0]);
    }

    #[test]
    fn signed_distance_changes_sign_at_closed_boundary() {
        let polygon = [
            Point::new(0.0, 0.0),
            Point::new(2.0, 0.0),
            Point::new(2.0, 2.0),
            Point::new(0.0, 2.0),
        ];
        assert_eq!(
            signed_polygon_distance(&polygon, Point::new(0.5, 1.0)),
            -0.5
        );
        assert_eq!(signed_polygon_distance(&polygon, Point::new(0.0, 1.0)), 0.0);
        assert_eq!(
            signed_polygon_distance(&polygon, Point::new(-0.5, 1.0)),
            0.5
        );
    }
}
