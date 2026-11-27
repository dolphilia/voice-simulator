//! 人間の矢状面モデル。ランドマークと係数はCHIMERA由来（Jameson Hodge、MIT）。
//! 固定版とライセンスの所在は研究ワークスペースの読解ノートと LICENSE-CHIMERA を参照。

use std::f64::consts::{PI, TAU};
use std::ops::{Add, Mul, Range, Sub};

#[cfg(all(not(target_arch = "wasm32"), feature = "render-allocation-probe"))]
use crate::render_allocation_probe::{Phase as AllocationPhase, scope as allocation_scope};

mod area;
mod body;
mod contact;
mod grid;
mod resample;
pub use area::{AreaProfile, AreaSample};
pub use body::{BodyMix, BodyName, BodyParameters};
pub(crate) use contact::ContactGridScratch;
pub use contact::{ContactGrid, ContactSample, RoofContact};
pub use grid::{GridSample, MAX_MEASUREMENT_RAYS, Region};
pub use resample::{ResampledTract, TractCell, TubeProfile};

#[derive(Clone, Copy, Debug, Default)]
pub struct Point {
    pub x: f64,
    pub y: f64,
}

impl Point {
    pub const fn new(x: f64, y: f64) -> Self {
        Self { x, y }
    }

    fn norm(self) -> f64 {
        libm::hypot(self.x, self.y)
    }

    fn mix(self, other: Self, fraction: f64) -> Self {
        self + (other - self) * fraction
    }
}

impl Add for Point {
    type Output = Self;

    fn add(self, rhs: Self) -> Self {
        Self::new(self.x + rhs.x, self.y + rhs.y)
    }
}

impl Sub for Point {
    type Output = Self;

    fn sub(self, rhs: Self) -> Self {
        Self::new(self.x - rhs.x, self.y - rhs.y)
    }
}

impl Mul<f64> for Point {
    type Output = Self;

    fn mul(self, factor: f64) -> Self {
        Self::new(self.x * factor, self.y * factor)
    }
}

#[derive(Clone, Copy, Debug)]
pub struct Articulation {
    pub jaw_cm: f64,
    pub tongue_body_cm: Point,
    pub tongue_tip_cm: Point,
    pub tongue_root_cm: f64,
    pub tip_curl: f64,
    pub dorsum: f64,
    pub lip_aperture_cm: f64,
    pub lip_protrusion_cm: f64,
    pub lip_spread: f64,
    pub labiodental: f64,
    pub velum_cm2: f64,
    pub larynx_cm: f64,
    pub lateral: f64,
    pub epilarynx: f64,
    pub ventricular: f64,
}

impl Articulation {
    /// 固定上流の中立姿勢。体型変更時の調音位置を初期化する。
    pub fn neutral() -> Self {
        let jaw_cm = 0.6;
        let tongue_body_cm = Point::new(2.9, 6.85);
        Self {
            jaw_cm,
            tongue_body_cm,
            tongue_tip_cm: resting_tip(jaw_cm, tongue_body_cm),
            tongue_root_cm: 0.0,
            tip_curl: 0.0,
            dorsum: 0.0,
            lip_aperture_cm: 0.7,
            lip_protrusion_cm: 0.2,
            lip_spread: 0.5,
            labiodental: 0.0,
            velum_cm2: -0.15,
            larynx_cm: 0.0,
            lateral: 0.0,
            epilarynx: 0.0,
            ventricular: 0.0,
        }
    }
}

pub(crate) fn resting_tip(jaw_cm: f64, body_cm: Point) -> Point {
    let axis = Point::new(-2.5, 10.5);
    let offset = Point::new(6.45, 7.35) - axis;
    let angle = -jaw_cm / 9.84;
    let (sine, cosine) = (libm::sin(angle), libm::cos(angle));
    let rotated_x = axis.x + offset.x * cosine - offset.y * sine;
    let rotated_y = axis.y + offset.x * sine + offset.y * cosine;
    Point::new(
        rotated_x + 0.30 * (body_cm.x - 2.9),
        rotated_y + 0.35 * (body_cm.y - 6.85),
    )
}

#[derive(Default)]
pub struct SagittalFrame {
    pub outer: Vec<Point>,
    pub inner: Vec<Point>,
    pub tongue: Vec<Point>,
    pub velum: Vec<Point>,
    pub velum_port_cm2: f64,
    pub upper_lip: Vec<Point>,
    pub lower_lip: Vec<Point>,
    pub upper_teeth: [Point; 5],
    pub lower_teeth: [Point; 4],
    pub jaw_bone: [Point; 7],
    pub epiglottis: [Point; 3],
    pub glottis: Point,
    pub tongue_center: Point,
    pub tongue_radius_cm: f64,
    pub tip: Point,
    labiodental: f64,
    lip_aperture_cm: f64,
    pub lip_width_cm: f64,
    lateral: f64,
    epilarynx: f64,
    ventricular: f64,
    roof: Range<usize>,
    tongue_body_contact: Range<usize>,
    tongue_tip_contact: Range<usize>,
}

pub struct SagittalModel {
    body: BodyParameters,
    pharynx: Vec<Point>,
    palate: Vec<Point>,
    nasal_cavity: Vec<Point>,
}

const CONDYLE: Point = Point::new(-2.5, 10.5);
pub(crate) const INNER_LIP_POINTS: usize = 7;
const OUTER_LIP_POINTS: usize = 6;
const VELUM_POINTS: usize = 11;
const TONGUE_ROOT_POINTS: usize = 9;
const TONGUE_ARC_POINTS: usize = 32;
const TONGUE_BLADE_POINTS: usize = 7;
const TONGUE_UNDERSIDE_POINTS: usize = 6;
const FLOOR_POINTS: usize = 3;
const TONGUE_OUTLINE_POINTS: usize = TONGUE_ROOT_POINTS
    + (TONGUE_ARC_POINTS - 1)
    + (TONGUE_BLADE_POINTS - 1)
    + (TONGUE_UNDERSIDE_POINTS - 1)
    + (FLOOR_POINTS - 1);
const RADIANS: f64 = PI / 180.0;

impl SagittalModel {
    pub fn adult_male() -> Self {
        Self::new(BodyName::Male.into())
    }

    pub fn new(mix: BodyMix) -> Self {
        let body = mix.parameters();
        let pharynx = template_spline(
            body,
            [
                [-1.0, -1.5],
                [-1.1, 1.5],
                [-1.2, 3.6],
                [-1.3, 5.6],
                [-1.38, 7.5],
                [-1.33, 8.9],
                [-1.05, 10.1],
                [-0.45, 10.9],
                [0.4, 11.3],
            ],
            4,
        );
        let palate = template_spline(
            body,
            [
                [1.0, 9.6],
                [1.8, 9.92],
                [2.7, 10.18],
                [3.6, 10.3],
                [4.4, 10.25],
                [5.1, 10.05],
                [5.7, 9.72],
                [6.15, 9.36],
                [6.5, 9.05],
                [6.78, 8.7],
                [6.98, 8.3],
                [7.12, 7.95],
            ],
            3,
        );
        let nasal_cavity = template_spline(
            body,
            [
                [1.0, 9.75],
                [2.5, 10.8],
                [5.0, 11.2],
                [7.3, 10.6],
                [8.0, 10.1],
            ],
            4,
        );
        Self {
            body,
            pharynx,
            palate,
            nasal_cavity,
        }
    }

    pub fn palate(&self) -> &[Point] {
        &self.palate
    }

    pub fn nasal_cavity(&self) -> &[Point] {
        &self.nasal_cavity
    }

    pub fn compute(&self, a: Articulation) -> SagittalFrame {
        let mut frame = self.frame_buffer();
        self.compute_into(a, &mut frame);
        frame
    }

    pub(crate) fn frame_buffer(&self) -> SagittalFrame {
        // 咽頭の切り詰めで追加する交点は、除かれた点の位置を一つ使う。
        let outer_points =
            self.pharynx.len() + VELUM_POINTS + (self.palate.len() - 1) + INNER_LIP_POINTS;
        // 喉頭蓋2点、舌根の交点、舌と口腔底、下歯列3点、下唇の順。
        let inner_points = 3 + TONGUE_OUTLINE_POINTS + 3 + INNER_LIP_POINTS;
        let lip_points = INNER_LIP_POINTS + (OUTER_LIP_POINTS - 1);
        SagittalFrame {
            outer: Vec::with_capacity(outer_points),
            inner: Vec::with_capacity(inner_points),
            tongue: Vec::with_capacity(TONGUE_OUTLINE_POINTS),
            velum: Vec::with_capacity(2 * VELUM_POINTS),
            upper_lip: Vec::with_capacity(lip_points),
            lower_lip: Vec::with_capacity(lip_points),
            ..SagittalFrame::default()
        }
    }

    /// 同じ座標と点順で輪郭を書き直し、制御周期の間で領域を再利用する。
    pub(crate) fn compute_into(&self, a: Articulation, frame: &mut SagittalFrame) {
        #[cfg(all(not(target_arch = "wasm32"), feature = "render-allocation-probe"))]
        let _allocation = allocation_scope(AllocationPhase::Contour);
        let SagittalFrame {
            outer,
            inner,
            tongue: back,
            upper_lip,
            lower_lip,
            velum,
            ..
        } = frame;
        let body = self.body;
        let k = body.scale;
        let condyle = body.point(CONDYLE.x, CONDYLE.y);
        let jaw_radius = (body.point(6.95, 7.75) - condyle).norm();
        let angle = -a.jaw_cm.clamp(-0.2, 3.0) * k / jaw_radius;
        let (sin, cos) = (libm::sin(angle), libm::cos(angle));
        let jaw = |x, y| {
            let d = body.point(x, y) - condyle;
            condyle + Point::new(d.x * cos - d.y * sin, d.x * sin + d.y * cos)
        };
        let lower_teeth = [
            jaw(6.45, 6.55),
            jaw(6.72, 7.15),
            jaw(6.95, 7.75),
            jaw(7.12, 7.45),
        ];
        let floor: [Point; FLOOR_POINTS] = [jaw(5.7, 6.15), jaw(6.2, 6.25), lower_teeth[0]];
        let tongue = Tongue::build(body, a, floor[0]);
        lips(
            body,
            a,
            self.palate[self.palate.len() - 1],
            &jaw,
            upper_lip,
            lower_lip,
        );
        let velum_sides = self.velum(a.velum_cm2);
        let uvula = velum_sides[VELUM_POINTS - 1].0;
        let wall_end_y = uvula.y - 0.3 * k;
        outer.clear();
        if let Some(end) = self.pharynx.iter().position(|p| p.y >= wall_end_y) {
            outer.extend_from_slice(&self.pharynx[..end]);
            if end > 0 {
                outer.push(at_height(
                    self.pharynx[end - 1],
                    self.pharynx[end],
                    wall_end_y,
                ));
            }
        } else {
            outer.extend_from_slice(&self.pharynx);
        }
        let roof_start = outer.len();
        outer.extend(velum_sides.iter().rev().map(|&(oral, _)| oral));
        outer.extend_from_slice(&self.palate[1..]);
        let roof = roof_start..outer.len();
        outer.extend_from_slice(&upper_lip[..INNER_LIP_POINTS]);

        back.clear();
        back.extend_from_slice(&tongue.root);
        let root_len = back.len();
        back.extend_from_slice(&tongue.arc[1..]);
        let tongue_body_contact = root_len - 1..back.len();
        inner.clear();
        inner.extend_from_slice(&tongue.epiglottis[..2]);
        let join_y = tongue.epiglottis[1].y + 0.05 * k;
        if let Some(start) = back.iter().position(|p| p.y > join_y) {
            if start > 0 {
                inner.push(at_height(back[start - 1], back[start], join_y));
            }
            let first = start + usize::from(start >= root_len);
            inner.extend_from_slice(&back[first..]);
        }
        let tip_start = back.len() + 1;
        back.extend_from_slice(&tongue.blade[1..]);
        let tongue_tip_contact = tip_start..back.len() + 2;
        back.extend_from_slice(&tongue.underside[1..]);
        back.extend_from_slice(&floor[1..]);
        inner.extend_from_slice(&tongue.blade[1..]);
        inner.extend_from_slice(&tongue.underside[1..]);
        inner.extend_from_slice(&floor[1..]);
        inner.extend_from_slice(&lower_teeth[1..]);
        inner.extend_from_slice(&lower_lip[..INNER_LIP_POINTS]);

        velum.clear();
        velum.extend(velum_sides.iter().map(|&(_, nasal)| nasal));
        velum.extend(velum_sides.iter().rev().map(|&(oral, _)| oral));
        frame.velum_port_cm2 = a.velum_cm2.max(0.0) * k * k;
        frame.lower_teeth = lower_teeth;
        frame.upper_teeth = [
            body.point(6.15, 9.36),
            body.point(6.78, 8.7),
            body.point(7.12, 7.95),
            body.point(7.38, 8.7),
            body.point(7.4, 9.3),
        ];
        frame.jaw_bone = [
            jaw(7.25, 6.75),
            jaw(7.4, 5.4),
            jaw(6.4, 4.6),
            jaw(3.5, 4.4),
            jaw(1.2, 5.2),
            jaw(-0.6, 7.4),
            jaw(-1.9, 9.6),
        ];
        frame.epiglottis = tongue.epiglottis;
        frame.glottis = body.point(0.0, 0.0) + Point::new(0.0, a.larynx_cm * k);
        frame.tongue_center = tongue.center;
        frame.tongue_radius_cm = body.tongue_radius * k;
        frame.tip = tongue.tip;
        frame.labiodental = a.labiodental.clamp(0.0, 1.0);
        frame.lip_aperture_cm = a.lip_aperture_cm * k;
        frame.lip_width_cm = (1.1 + (body.lip_width - 1.1) * a.lip_spread.clamp(0.0, 1.0)) * k;
        frame.lateral = a.lateral;
        frame.epilarynx = a.epilarynx;
        frame.ventricular = a.ventricular;
        frame.roof = roof;
        frame.tongue_body_contact = tongue_body_contact;
        frame.tongue_tip_contact = tongue_tip_contact;
    }

    fn velum(&self, port_cm2: f64) -> [(Point, Point); VELUM_POINTS] {
        let k = self.body.scale;
        let opening = (port_cm2 / 1.2).clamp(0.0, 1.0);
        let angle = (194.0 + 46.0 * opening) * RADIANS;
        let forward = direction(angle);
        let normal = Point::new(-forward.y, forward.x);
        let hinge = self.body.point(1.0, 9.75);
        std::array::from_fn(|index| {
            let t = index as f64 / (VELUM_POINTS - 1) as f64;
            let sag_cm = libm::sin(t * PI) * k * (0.3 * opening - 0.12);
            let center = hinge + forward * (2.8 * k * t) - Point::new(0.0, sag_cm);
            let thickness = normal * ((0.48 - 0.2 * t) * k);
            let blend = (1.0 - t / 0.35).max(0.0);
            (
                (center + thickness).mix(self.palate[0], blend * blend),
                center - thickness,
            )
        })
    }
}

struct Tongue {
    center: Point,
    tip: Point,
    root: [Point; TONGUE_ROOT_POINTS],
    arc: [Point; TONGUE_ARC_POINTS],
    blade: [Point; TONGUE_BLADE_POINTS],
    underside: [Point; TONGUE_UNDERSIDE_POINTS],
    epiglottis: [Point; 3],
}

impl Tongue {
    fn build(body: BodyParameters, a: Articulation, frenulum: Point) -> Self {
        let k = body.scale;
        let radius = body.tongue_radius * k;
        let larynx = a.larynx_cm * k;
        let center = body.point(a.tongue_body_cm.x, a.tongue_body_cm.y);
        let moved = center - body.point(2.9, 6.85);
        let valley = body.point(0.75, 3.3)
            + Point::new(
                0.45 * moved.x + a.tongue_root_cm * k,
                0.3 * moved.y + 0.55 * larynx,
            );
        let epiglottis = [
            body.point(0.3, 2.4) + Point::new(0.0, larynx),
            body.point(0.0, 4.5)
                + Point::new(0.35 * (valley.x - 0.75 * k), 0.8 * larynx + 0.15 * moved.y),
            valley,
        ];
        let rear_angle = 200.0 * RADIANS;
        let rear = center + direction(rear_angle) * radius;
        let handle = (rear - valley).norm() / 3.0;
        let root = bezier([
            valley,
            valley + Point::new(0.08 * k, handle),
            rear - tangent_down(rear_angle) * handle,
            rear,
        ]);
        let tip_goal = body.point(a.tongue_tip_cm.x, a.tongue_tip_cm.y);
        let offset = tip_goal - center;
        let dist = offset.norm();
        let tip = if dist > 0.0 && dist < 1.05 * radius {
            center + offset * (1.05 * radius / dist)
        } else {
            tip_goal
        };
        let ray = tip - center;
        let ray_angle = libm::atan2(ray.y, ray.x);
        let ray_length = ray.norm();
        let tangent_angle = if ray_length > 1.0001 * radius {
            ray_angle + libm::acos(radius / ray_length)
        } else {
            ray_angle
        };
        let front_angle = rear_angle - (rear_angle - tangent_angle).rem_euclid(TAU);
        let mut arc: [Point; TONGUE_ARC_POINTS] = std::array::from_fn(|index| {
            let theta = rear_angle
                + (front_angle - rear_angle) * index as f64 / (TONGUE_ARC_POINTS - 1) as f64;
            center + direction(theta) * radius
        });
        let front = arc[arc.len() - 1];
        let curl = a.tip_curl.clamp(0.0, 1.0);
        let control = front
            + tangent_down(front_angle) * (0.5 * (tip - front).norm())
            + Point::new(0.0, (0.18 + 0.5 * curl) * k);
        let mut blade = bezier([front, control, tip]);
        if a.dorsum > 0.0 {
            for point in arc.iter_mut().chain(&mut blade[1..6]) {
                let fraction = (point.x - center.x) / (tip.x - center.x).max(1e-6);
                if 0.0 < fraction && fraction < 1.0 {
                    let weight = libm::sin(PI * libm::pow(fraction, 0.8));
                    point.y -= a.dorsum * 0.9 * k * weight * weight;
                }
            }
        }
        let underside = bezier([tip, tip + Point::new(-0.3 - 0.4 * curl, -0.6) * k, frenulum]);
        Self {
            center,
            tip,
            root,
            arc,
            blade,
            underside,
            epiglottis,
        }
    }
}

fn lips(
    body: BodyParameters,
    a: Articulation,
    incisor: Point,
    jaw: &impl Fn(f64, f64) -> Point,
    upper: &mut Vec<Point>,
    lower: &mut Vec<Point>,
) {
    let k = body.scale;
    let protrusion = a.lip_protrusion_cm.clamp(-0.2, 1.6) * k;
    let spreading = a.lip_spread.clamp(0.0, 1.0);
    let lab = a.labiodental.clamp(0.0, 1.0);
    let front_x = body.point(8.15 + 0.12 * (1.0 - spreading), 0.0).x + 0.95 * protrusion;
    let middle_y = (7.85 - 0.3 * a.jaw_cm) * k;
    let aperture = a.lip_aperture_cm * k;
    let upper_edge = Point::new(
        front_x - 0.15 * k,
        middle_y + 0.35 * aperture + 0.35 * lab * k,
    )
    .mix(incisor + Point::new(0.55, 0.45) * k, 0.7 * lab);
    let lower_edge = Point::new(front_x - 0.25 * k, middle_y - 0.65 * aperture)
        .mix(incisor + Point::new(0.05 * k, -aperture.max(-0.1)), lab);
    let upper_base = body.point(7.32, 8.35);
    let lower_base = jaw(7.12, 7.45);
    upper.clear();
    upper.extend_from_slice(&bezier::<_, INNER_LIP_POINTS>([
        upper_base,
        upper_base + Point::new(0.3 * k + protrusion * 0.4, 0.05 * k),
        upper_edge + Point::new(-0.35, 0.12) * k,
        upper_edge,
    ]));
    lower.clear();
    lower.extend_from_slice(&bezier::<_, INNER_LIP_POINTS>([
        lower_base,
        lower_base + Point::new(0.25 * k + protrusion * 0.3, -0.05 * k),
        lower_edge + Point::new(-0.3, -0.12) * k,
        lower_edge,
    ]));
    upper.extend_from_slice(
        &bezier::<_, OUTER_LIP_POINTS>([
            upper_edge,
            upper_edge + Point::new(0.25, 0.35) * k,
            body.point(8.3, 9.6),
            body.point(7.9, 10.4),
        ])[1..],
    );
    lower.extend_from_slice(
        &bezier::<_, OUTER_LIP_POINTS>([
            lower_edge,
            lower_edge + Point::new(0.3, -0.4) * k,
            jaw(8.1, 6.3),
            jaw(7.6, 5.6),
        ])[1..],
    );
}

fn direction(angle: f64) -> Point {
    Point::new(libm::cos(angle), libm::sin(angle))
}

fn tangent_down(angle: f64) -> Point {
    Point::new(libm::sin(angle), -libm::cos(angle))
}

fn at_height(a: Point, b: Point, height: f64) -> Point {
    a.mix(b, ((height - a.y) / (b.y - a.y).max(1e-9)).clamp(0.0, 1.0))
}

fn bezier<const N: usize, const SAMPLES: usize>(controls: [Point; N]) -> [Point; SAMPLES] {
    std::array::from_fn(|index| {
        let t = index as f64 / (SAMPLES - 1) as f64;
        let mut layer = controls;
        for remaining in (1..N).rev() {
            for i in 0..remaining {
                layer[i] = layer[i].mix(layer[i + 1], t);
            }
        }
        layer[0]
    })
}

fn template_spline<const N: usize>(
    body: BodyParameters,
    template: [[f64; 2]; N],
    samples_per_segment: usize,
) -> Vec<Point> {
    let points = template.map(|[x, y]| body.point(x, y));
    let tangent =
        |index: usize| (points[(index + 1).min(N - 1)] - points[index.saturating_sub(1)]) * 0.5;
    let mut curve = Vec::with_capacity((N - 1) * samples_per_segment + 1);
    for i in 0..N - 1 {
        let (m0, m1) = (tangent(i), tangent(i + 1));
        for j in 0..samples_per_segment {
            let t = j as f64 / samples_per_segment as f64;
            let u = 1.0 - t;
            curve.push(
                points[i] * (u * u * (1.0 + 2.0 * t))
                    + m0 * (t * u * u)
                    + points[i + 1] * (t * t * (3.0 - 2.0 * t))
                    - m1 * (t * t * u),
            );
        }
    }
    curve.push(points[N - 1]);
    curve
}
