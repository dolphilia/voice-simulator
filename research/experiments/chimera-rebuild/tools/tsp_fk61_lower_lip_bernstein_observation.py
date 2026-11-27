"""下唇内面だけをBernstein基底で評価し、通常の発話を観測する。"""

from difflib import unified_diff

import tsp_fk61_node_volume_observation as volume
import tsp_fk61_ray43_observation as ray
from tsp_fk61_lip_observation import edit, insert_before


ANATOMY = 'crates/vocal-core/src/anatomy.rs'


def apply_curve(root):
    path = root / ANATOMY
    before = path.read_text()
    anchor = '    lower.extend_from_slice(&bezier::<_, INNER_LIP_POINTS>([\n        lower_base,'
    edit(path, anchor, anchor.replace('bezier::<_, INNER_LIP_POINTS>', 'research_lower_lip'))
    insert_before(path, 'fn template_spline<const N', '''// CHIMERA (MIT) の geom::bezier3 と同じ順で、下唇内面だけを評価する。
fn research_lower_lip(points: [Point; 4]) -> [Point; INNER_LIP_POINTS] {
    let [p0, p1, p2, p3] = points;
    std::array::from_fn(|index| {
        let t = index as f64 / (INNER_LIP_POINTS - 1) as f64;
        let u = 1.0 - t;
        let a = u * u * u;
        let b = 3.0 * u * u * t;
        let c = 3.0 * u * t * t;
        let d = t * t * t;
        p0 * a + p1 * b + p2 * c + p3 * d
    })
}

''')
    return ''.join(unified_diff(before.splitlines(keepends=True), path.read_text().splitlines(keepends=True),
                                fromfile='a/' + ANATOMY, tofile='b/' + ANATOMY))


def prepare(root, measure, execute):
    volume.prepare(root, False, measure['comparison_internal_samples'], execute)
    return ray.prepare(root, False, measure['completed_frames'], trial=True)
