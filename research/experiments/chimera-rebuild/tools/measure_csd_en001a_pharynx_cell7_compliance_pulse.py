"""CSDの咽頭セル7で、第1標本のコンプライアンス交換を出力まで照合する。"""

import argparse
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np

import measure_csd_en001a_pharynx_cell7_first_block as block
from tsp_fk61_lip_observation import edit, insert_before, PAIR_SHIFT


source, tsp, radiation = block.source, block.tsp, block.radiation
output = block.prior
CASE = radiation.WORKSPACE / 'cases/csd-en001a-pharynx-cell7-compliance-pulse.json'
MODES = source.MODES
CONDITIONS = ('native', 'initial_only', 'compliance_only')
FIELDS = ('wall_cm3_s', 'lip_cm3_s', 'nose_cm3_s', 'total_cm3_s', radiation.RADIATION)
INITIAL = ('native_c', 'used_c', 'old_pressure', 'inflow')
FILES = (*source.FILES, 'network.npz')
MASK = 'CHIMERA_CSD_COMPLIANCE_PULSE'


def patch_network(root, fixed, measure, donor):
    name = ('crates/chimera/src/airway/network.rs' if fixed else 'crates/vocal-core/src/airway/network.rs')
    path = root / name
    original = path.read_text()
    node, window = measure['focus_node'], measure['observed_pressure_samples']
    member = '    pub probe_lip_node: Option<usize>,'
    initializer = '            probe_lip_node: None,'
    edit(path, member, member + '\n    probe_compliance_sample: usize,')
    edit(path, initializer, initializer + '\n            probe_compliance_sample: 0,')
    insert_before(path, PAIR_SHIFT, f'''        let probe_compliance = self.probe_lip_node == Some({node});
        let probe_n = self.probe_compliance_sample;
        if probe_compliance {{
            self.probe_compliance_sample += 1;
        }}
        let mut probe_initial = [0.0f64; {len(INITIAL)}];
''')
    if fixed:
        update = '                self.p[k] += (t / c) * self.flow_sum[k];'
        index, compliance, previous, inflow = 'k', 'c', 'self.p[k]', 'self.flow_sum[k]'
        pressure = 'self.p'
        end = '        self.rad_prev_total = rad_total;'
        emit = '            let radios = [wall_rad_sum, self.rad_u[0], self.rad_u[1], rad_total, out];'
    else:
        update = '                self.pressure[node] += self.dt / compliance * inflow;'
        index, compliance, previous, inflow = 'node', 'compliance', 'self.pressure[node]', 'inflow'
        pressure = 'self.pressure'
        end = '        self.previous_radiation_flow = radiation_flow;'
        emit = '''            let mut loads = self.radiators.iter().flatten();
            let lip = loads.next().expect("口端放射").flow;
            let nose = loads.next().expect("鼻端放射").flow;
            assert!(loads.next().is_none());
            let radios = [wall_radiation, lip, nose, radiation_flow, derivative];'''
    bits = np.float64(donor).view(np.uint64)
    insert_before(path, update, f'''                let {compliance} = if probe_compliance && probe_n == 0 && {index} == {node} {{
                    let supplied = if std::env::var_os("{MASK}").is_some() {{
                        f64::from_bits(0x{bits:016x})
                    }} else {{
                        {compliance}
                    }};
                    probe_initial = [{compliance}, supplied, {previous}, {inflow}];
                    supplied
                }} else {{
                    {compliance}
                }};
''')
    insert_before(path, end, f'''        if probe_compliance {{
            use std::io::Write as _;
            let mut stream = std::io::stdout().lock();
            if probe_n == 0 {{
                assert!(probe_initial[0] > 0.0, "対象の内部節点で圧力を更新していません");
                for x in [{pressure}.len() as f64].into_iter().chain(probe_initial) {{
                    stream.write_all(&x.to_le_bytes()).expect("初期値を観測できません");
                }}
            }}
{emit}
            for x in radios {{
                stream.write_all(&x.to_le_bytes()).expect("放射を観測できません");
            }}
            if probe_n < {window} {{
                for x in &{pressure} {{
                    stream.write_all(&x.to_le_bytes()).expect("節点圧力を観測できません");
                }}
            }}
        }}
''')
    return output.diff(original, path, name)


def read_network(path, count, window, nodes):
    raw = np.fromfile(path, dtype='<f8')
    head = len(INITIAL) + 1
    split = head + window * (len(FIELDS) + nodes)
    if (len(raw) != split + (count - window) * len(FIELDS)
            or raw[0] != nodes or not np.isfinite(raw).all()):
        raise ValueError(f'放射または節点圧力の観測数・値が不正です ({path.name})')
    early = raw[head:split].reshape(window, len(FIELDS) + nodes)
    return {'initial': raw[1:head], 'pressure': early[:, len(FIELDS):],
            'radiation': np.concatenate([early[:, :len(FIELDS)], raw[split:].reshape(-1, len(FIELDS))])}


def read_pressures(path, window):
    with path.open() as stream:
        rows = np.loadtxt((line for line in stream if line.partition(',')[0].isdecimal()),
                          delimiter=',', usecols=(0, 1, len(block.observe_cells.FIELDS) - 1), ndmin=2)
    pressures = rows.reshape(window, -1, 3)
    nodes = pressures.shape[1]
    if not (np.all(pressures[:, :, 0] == np.arange(window)[:, None])
            and np.all(pressures[:, :, 1] == np.arange(nodes)) and np.isfinite(pressures).all()):
        raise ValueError(f'保存済みの節点圧力を同定できません ({path.name})')
    return pressures[:, :, 2]


def read_block(run, name, condition, window, focus):
    path = tsp.verified_path(run, f'artifacts/{name}_{condition}-block.csv')
    marker = f'compliance,0,{focus},'
    with path.open() as stream:
        compliance = next((float(line.strip().split(',')[3])
                           for line in stream if line.startswith(marker)), None)
    if compliance is None or compliance <= 0:
        raise ValueError(f'標本0のコンプライアンスがありません ({path.name})')
    return read_pressures(path, window), compliance


def study_inputs(study):
    rev = study['upstream_revision']
    baseline, reference = (tsp.open_run(study[key], rev) for key in ('block', 'output'))
    block_case, blk = radiation.saved_case(baseline, block.CASE)
    ref_case, out = radiation.saved_case(reference, output.CASE)
    stage, coeff, centerline, render = (
        tsp.open_run(case[key], rev) for case, key in ((ref_case, 'config'), (ref_case, 'coefficients'),
                                                       (block_case, 'centerline'), (block_case, 'render')))
    config, cfg = radiation.saved_case(stage, source.lip.CONFIG)
    paths = {'spec': tsp.verified_path(render, 'artifacts/candidate-short-128.json'),
             'config': cfg, 'coefficients': tsp.verified_path(coeff, 'artifacts/coefficients.json'),
             'reference': tsp.verified_path(reference, 'artifacts/output-trace.npz'),
             'pcm': tsp.verified_path(baseline, 'artifacts/pcm-digests.json'),
             'snapshots': tsp.verified_path(baseline, 'artifacts/observations.json'),
             'block_case': blk, 'output_case': out,
             **{f'{label}_manifest': run[0] / 'manifest.json' for label, run in
                (('output', reference), ('stage', stage), ('coeff', coeff), ('render', render))}}
    return baseline, centerline, block_case, config, paths


def capture(study, out, execute, baseline, centerline, block_case, paths):
    m = study['measurement']
    count = m['frames'] * (m['internal_sample_rate_hz'] // m['sample_rate_hz'])
    window = m['observed_pressure_samples']
    originals = {name: read_block(baseline, name, 'initial_only', window, m['focus_node']) for name in MODES}
    renderer = block_case | {'measurement': block_case['measurement'] | {'conditions': m['conditions']}}
    with TemporaryDirectory(prefix='csd-compliance-pulse-', dir=out.parent / 'tmp') as directory:
        scratch = Path(directory)

        def instrument(root, fixed):
            name = 'upstream' if fixed else 'candidate'
            return patch_network(root, fixed, m, originals[name][1])

        def command(argv, name, condition):
            if condition == 'compliance_only':
                argv = [argv[0], f'{MASK}=1', *argv[1:]]
            return argv, scratch / f'{name}_{condition}.f64le'

        source.capture(renderer, paths['spec'], centerline, out, execute,
                       block_observer=instrument, render_observer=command)
        captured = {}
        for name in MODES:
            for condition in CONDITIONS:
                key = f'{name}_{condition}'
                parsed = read_network(scratch / f'{key}.f64le', count, window, originals[name][0].shape[1])
                captured.update({f'{key}_{field}': value for field, value in parsed.items()})
        np.savez_compressed(out / 'network.npz', **captured)


def replay(rows, cfg, coeff, gain, measure, fixed):
    sources = dict(zip(FIELDS, rows.T, strict=True))
    rate = measure['internal_sample_rate_hz']
    total, derivative = radiation.radiation_from_components(sources, rate, fixed)
    state_trim = None
    if fixed:
        step = output.UPSTREAM_CONTROL_OUTPUT_FRAMES * (rate // measure['sample_rate_hz'])
        previous = total[step - 1:-1:step]
        derivative[step::step] = (total[step::step]
                                 - np.where(np.abs(previous) < output.UPSTREAM_TINY, 0.0, previous)) * rate
        state_trim = (step, output.UPSTREAM_TINY)
    stages, pcm = output.pcm.replay(derivative, coeff, gain, cfg, state_trim=state_trim)
    same = output.prefix.load.same_bits
    return stages, pcm, same(total, sources['total_cm3_s']) and same(derivative, sources[radiation.RADIATION])


def differences(left, right):
    delta = right.astype(np.float64) - left
    return output.full.metrics(delta) | {'unequal': int(np.count_nonzero(delta))}


def contrasts(a, b, left, right, left_pcm, right_pcm):
    earlier = a['pressure']
    later = b['pressure']
    starts = {}
    for node, (base, trial) in enumerate(zip(earlier.T, later.T, strict=True)):
        changed = np.flatnonzero(base != trial)
        if changed.size:
            starts[str(node)] = int(changed[0])
    return {
        'pressure_first_by_node': starts,
        'radiation': {field: differences(base, trial) for field, base, trial in
                      zip(FIELDS, a['radiation'].T, b['radiation'].T, strict=True)},
        'output': {key: differences(base, trial) for key, base, trial in
                   zip(output.pcm.COLUMNS[2:], left.T, right.T, strict=True)},
        'pcm': differences(left_pcm, right_pcm),
    }


def analyze(study, out, baseline, config, paths):
    m = study['measurement']
    node, window = m['focus_node'], m['observed_pressure_samples']
    gain = tsp.read(paths['spec'])['song_voice']['voice']['output_gain']
    coeff, proof, snapshots = (tsp.read(p) for p in (paths['coefficients'], out / 'pcm-digests.json',
                                                    out / 'observations.json'))
    expected, saved = (tsp.read(paths[name]) for name in ('pcm', 'snapshots'))
    checks, report = {}, {}
    same = output.prefix.load.same_bits
    with (np.load(out / 'network.npz', allow_pickle=False) as network,
          np.load(out / 'pcm.npz', allow_pickle=False) as pcm,
          np.load(paths['reference'], allow_pickle=False) as prior):
        for name in MODES:
            fixed = name == 'upstream'
            reference_key = 'upstream_normal' if fixed else 'research_normal'
            indices = [output.SOURCE_FIELDS.index(key) for key in FIELDS]
            data, stages, waves, record = {}, {}, {}, {}
            for condition in CONDITIONS:
                key = f'{name}_{condition}'
                waves[condition] = pcm[key]
                current = {field: network[f'{key}_{field}'] for field in ('initial', 'pressure', 'radiation')}
                data[condition] = current
                init = dict(zip(INITIAL, map(float, current['initial']), strict=True))
                record[condition] = init | {'new_pressure': float(current['pressure'][0, node])}
                rendered = proof[name][condition]
                checks[f'{key}_pcm_length_and_score'] = (
                    rendered['pcm'] == source.lip.pcm_digest(waves[condition]) and len(waves[condition]) == m['frames']
                    and rendered['plan'] == expected[name]['native']['plan'])
                if condition != 'compliance_only':
                    pressures, c = read_block(baseline, name, condition, window, node)
                    checks[f'{key}_archived_pcm_pressure_and_shape'] = (
                        rendered == expected[name][condition] and snapshots[name][condition] == saved[name][condition]
                        and same(pressures, current['pressure']) and init['native_c'] == init['used_c'] == c)
                values, predicted, upstream_physics = replay(current['radiation'], config, coeff[name], gain, m, fixed)
                stages[condition] = values
                checks[f'{key}_radiation_and_pcm_replayed'] = upstream_physics and source.lip.bit_equal(
                    predicted, waves[condition])
            checks[f'{name}_native_radiation_matches_prior'] = same(
                data['native']['radiation'], prior[f'{reference_key}_source'][:, indices])
            control, area, pulse = (record[key] for key in CONDITIONS)
            calculated = pulse['old_pressure'] + ((1 / m['internal_sample_rate_hz']) / pulse['used_c']) * pulse['inflow']
            a, b = (data[c]['pressure'][0] for c in ('native', 'compliance_only'))
            changed = np.flatnonzero(a != b).tolist()
            checks[f'{name}_single_exchange_local_pressure'] = (
                pulse['native_c'] == control['native_c'] and pulse['used_c'] == area['used_c']
                and pulse['used_c'] != pulse['native_c'] and pulse['old_pressure'] == control['old_pressure']
                and pulse['inflow'] == control['inflow'] and pulse['new_pressure'] == calculated
                and changed == [node] and pulse['new_pressure'] == area['new_pressure']
                and snapshots[name]['compliance_only']['0'] == snapshots[name]['native']['0'])
            comparisons = {f'{left}_to_{right}': contrasts(
                data[left], data[right], stages[left], stages[right], waves[left], waves[right])
                for left, right in (('native', 'initial_only'), ('native', 'compliance_only'),
                                    ('initial_only', 'compliance_only'))}
            effect = comparisons['native_to_compliance_only']['radiation']
            lip, wall = (effect[key]['first_nonzero_frame'] for key in ('lip_cm3_s', 'wall_cm3_s'))
            report[name] = {'sample_zero': record, 'comparisons': comparisons, 'hypotheses': {
                'first_local_pressure_reproduced': checks[f'{name}_single_exchange_local_pressure'],
                'lip_causal_minimum': lip is None or lip >= m['lip_node'] - node,
                'wall_before_lip': wall is not None and (lip is None or wall < lip),
                'whole_pcm_requires_more_than_one_update': comparisons['initial_only_to_compliance_only']['pcm']['unequal'] > 0,
            }}
    return {'checks': checks, 'sides': report}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    ws, upper = radiation.WORKSPACE, radiation.UPSTREAM
    study = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=upper, text=True).strip()
    if revision != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=upper):
        parser.error('変更のない固定上流版が必要です')
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('試験ビルドにCHIMERA_RUN_STORAGE=rtl9210bを指定してください')
    baseline, centerline, block_case, config, paths = study_inputs(study)
    manifest = tsp.read(baseline[0] / 'manifest.json')
    inputs = [CASE, Path(__file__).resolve(), *paths.values(),
              *(run[0] / 'manifest.json' for run in (baseline, centerline)),
              *(ws.parents[2] / item['path'] for item in manifest['inputs']),
              *(tsp.verified_path(baseline, f'artifacts/{name}_{condition}-block.csv')
                for name in MODES for condition in CONDITIONS[:2]),
              Path(output.__file__), Path(output.full.__file__), Path(output.pcm.__file__)]

    def measure(out, execute):
        capture(study, out, execute, baseline, centerline, block_case, paths)
        return analyze(study, out, baseline, config, paths)

    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return radiation.record_measurement(args.run_id, CASE, list(dict.fromkeys(inputs)), details, measure,
                                        command=None, input_root=ws.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
