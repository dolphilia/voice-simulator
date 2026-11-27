"""FK61_01の口端観測を外部ディスク上の試験ビルドへ追加する。"""

from measure_duet_mixed_lip_load_origin import LOCAL_PATCH, UPPER_PATCH
from measure_tsp_fine_variation import LOCAL, PROBE


FIELDS = (
    'volume_source_enabled', 'geometry_advances', 'old_area', 'old_length', 'old_minimum',
    'minimum', 'area_increment', 'length_increment', 'minimum_increment', 'old_volume',
    'volume', 'pole_coefficient', 'old_first_pole', 'old_second_pole', 'spill', 'first_pole',
    'second_pole', 'area_floor', 'squeeze_threshold',
)

PAIR_SHIFT = '        self.probe_lip_pair = [self.probe_lip_pair[1], [0.0; 14]];'


def edit(path, anchor, replacement):
    code = path.read_text()
    if code.count(anchor) != 1:
        raise ValueError(f'観測挿入位置を特定できません ({path.name}: {anchor.splitlines()[0]})')
    path.write_text(code.replace(anchor, replacement))


def insert_before(path, anchor, insertion):
    edit(path, anchor, insertion + anchor)


def network_observation(network, before, after):
    size = len(FIELDS)
    edit(network, '    pub probe_lip_pair: [[f64; 14]; 2],',
         f'    pub probe_lip_pair: [[f64; 14]; 2],\n    pub probe_lip_geometry: [[f64; {size}]; 2],')
    edit(network, '            probe_lip_pair: [[0.0; 14]; 2],',
         f'            probe_lip_pair: [[0.0; 14]; 2],\n            probe_lip_geometry: [[0.0; {size}]; 2],')
    edit(network, PAIR_SHIFT, PAIR_SHIFT + f'''
        self.probe_lip_geometry = [self.probe_lip_geometry[1], [0.0; {size}]];
''' + before)
    insert_before(network, '        let probe_geometry_inflow =', after)


def observe_candidate(root):
    geometry = root / 'crates/vocal-core/src/airway/network/geometry.rs'
    insert_before(geometry, '    pub(super) fn filtered_flow', '''    pub(super) fn observe(&self, node: usize) -> [f64; 11] {
        let cell = &self.cells[node];
        [u8::from(self.enabled).into(), u8::from(self.remaining > 0).into(),
            cell.volume_cm3, cell.area_increment_cm2, cell.length_increment_cm,
            cell.minimum_area_increment_cm2, self.coefficient, cell.first_pole,
            cell.filtered_flow, self.spill[node], SQUEEZE_AREA_CM2]
    }

''')
    network_observation(root / 'crates/vocal-core/src/airway/network.rs', '''        let probe_before = self.probe_lip_node.map(|node| {
            (node, self.sections[node], self.moving_areas.observe(node))
        });''', '''        if let Some((node, old, before)) = probe_before {
            let [enabled, advances, old_volume, da, dl, dm, coefficient, first, second, ..] = before;
            let after = self.moving_areas.observe(node);
            self.probe_lip_geometry[1] = [enabled, advances, old.area_cm2, old.length_cm,
                old.minimum_area_cm2, self.sections[node].minimum_area_cm2, da, dl, dm,
                old_volume, after[2], coefficient, first, second, after[9], after[7],
                after[8], MIN_CELL_AREA_CM2, after[10]];
        }
''')


def observe_upstream(root):
    network_observation(root / 'crates/chimera/src/airway/network.rs', '''        let probe_before = self.probe_lip_node.map(|node| {
            (node, self.area[node], self.dx[node], self.amin[node],
                self.vol[node], self.vol_src1[node], self.vol_src2[node])
        });''', '''        if let Some((node, area, length, minimum, volume, first, second)) = probe_before {
            self.probe_lip_geometry[1] = [u8::from(vol_on).into(), 1.0, area, length,
                minimum, self.amin[node], self.area_step[node], self.dx_step[node],
                self.amin_step[node], volume, self.vol[node], self.vol_lp_coef, first,
                second, self.spill[node], self.vol_src1[node], self.vol_src2[node],
                min_a, sq];
        }
''')


def prepare(root, fixed, window, execute):
    target = root / 'tools' / (PROBE if fixed else LOCAL).name
    patch = UPPER_PATCH if fixed else LOCAL_PATCH
    execute(['git', 'apply', '--include=crates/*', str(patch)], cwd=root)
    if fixed:
        observe_upstream(root)
        edit(target, '    voice.schedule(&score.gestures);', '''    voice.schedule(&score.gestures);
    voice.airway.net.probe_lip_node = Some(voice.airway.oral.last_node());''')
    else:
        observe_candidate(root)
        edit(target, '    spoken.set_score(gestures)?;', '''    spoken.set_score(gestures)?;
    spoken.enable_lip_load_observation();''')
    anchor = 'fn render_source(' if fixed else '    let mut trace = BufWriter::new(File::create_new(trace)?);'
    code = target.read_text()
    start = code.index(anchor)
    begin, end = window
    net = 'voice.airway.net' if fixed else 'spoken.airway().network'
    open_loop = '    for frame in 0..frames {'
    code = code[:start] + code[start:].replace(open_loop, '''    let path = std::env::var_os("CHIMERA_PROBE_LIP_WINDOW").ok_or("口端状態の保存先がありません")?;
    let mut lip_trace = BufWriter::new(File::create_new(path)?);
''' + open_loop, 1)
    pcm = '        pcm.write_all(&sample[0].to_le_bytes())?;' if fixed else '        pcm.write_all(&out.pcm.to_le_bytes())?;'
    code = code[:start] + code[start:].replace(pcm, pcm + f'''
        if ({begin // 2}..{end // 2}).contains(&frame) {{
            for (load, geometry) in {net}.probe_lip_pair.iter().zip(&{net}.probe_lip_geometry) {{
                tsp_fine_trace::write_row(&mut lip_trace, load)?;
                tsp_fine_trace::write_row(&mut lip_trace, geometry)?;
            }}
        }}
''', 1)
    code = code[:start] + code[start:].replace('    pcm.flush()?;', '    lip_trace.flush()?;\n    pcm.flush()?;', 1)
    target.write_text(code)
    return target
