"""CSDの最初の口端流量を制御目標、体積源、放射負荷から照合する。"""

import argparse
from itertools import combinations
import json
import math
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np

import measure_csd_en001a_two_phrase_pcm_rounding as prior
from measure_fixed_voice_release_lip_load import INPUTS, OUTPUTS, replay
import tsp_fk61_lip_observation as observer


lip, tsp, radiation, song = prior.lip, prior.tsp, prior.radiation, prior.song
CASE = radiation.WORKSPACE / 'cases/csd-en001a-first-lip-load.json'
MODES = ('upstream', 'candidate')
TARGET_FIELDS = ('target_area_cm2', 'target_length_cm', 'target_minimum_cm2')
FIELDS = (*lip.LOAD_FIELDS, *observer.FIELDS, 'node', *TARGET_FIELDS)
SAVED_FILES = ('lip-observations.json', 'pcm-digests.json', 'upstream-observation.patch', 'candidate-observation.patch')
TESTS = {'upstream': ('chimera', 'airway', 'airway_adversarial'), 'candidate': ('vocal-core', 'geometry_ramp')}
GROUPS = {'inflow': ('inflow',), 'load_geometry': ('compliance', 'inertance', 'resistance'),
          'history': ('old_pressure', 'old_inertance_flow'), 'arithmetic_order': ()}


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def patch_network(root, fixed, execute):
    patch = observer.UPPER_PATCH if fixed else observer.LOCAL_PATCH
    names = (['crates/chimera/src/airway/network.rs'] if fixed else
             ['crates/vocal-core/src/airway/network.rs', 'crates/vocal-core/src/airway/network/geometry.rs',
              'crates/vocal-core/src/voice.rs'])
    original = {name: (root / name).read_text() for name in names}
    execute(['git', 'apply', '--include=crates/*', str(patch)], cwd=root)
    if fixed:
        observer.observe_upstream(root)
    else:
        observer.observe_candidate(root)
    net = root / names[0]
    observer.edit(net, '    pub probe_lip_node: Option<usize>,',
                  '    pub probe_lip_node: Option<usize>,\n    pub probe_lip_target: [f64; 3],')
    observer.edit(net, '            probe_lip_node: None,',
                  '            probe_lip_node: None,\n            probe_lip_target: [0.0; 3],')
    if fixed:
        observer.insert_before(net, '        let inv = 1.0 / js_max(1.0, samples as f64);', '''        if let Some(k) = self.probe_lip_node {
            self.probe_lip_target = [self.area_target[k], self.dx_target[k], self.amin_target[k]];
        }
''')
    else:
        observer.insert_before(net, '        self.port_area_increments_cm2.fill(0.0);', '''        if let Some(k) = self.probe_lip_node {
            self.probe_lip_target = [areas_cm2[k][0], lengths_cm.map_or(self.sections[k].length_cm, |dx| dx[k]),
                areas_cm2[k][1]];
        }
''')
    return ''.join(prior.diff(original[name], root / name, name) for name in names)


def patch_upstream(path, frames):
    original = path.read_text()
    observer.insert_before(path, '    let mut one = [0.0f32];', '''    let mut lip_trace = std::env::var_os("CHIMERA_CSD_LIP_TRACE")
        .map(File::create_new).transpose()?.map(BufWriter::new);
    let lips = voice.airway.oral.last_node();
    if lip_trace.is_some() {
        voice.airway.net.probe_lip_node = Some(lips);
    }
''')
    observer.insert_before(path, '        pcm.write_all(&one[0].to_le_bytes())?;', f'''        if let Some(out) = &mut lip_trace
            && frame < {frames}
        {{
            let net = &mut voice.airway.net;
            for (load, geometry) in net.probe_lip_pair.iter().zip(&net.probe_lip_geometry) {{
                for value in load.iter().chain(geometry).copied()
                    .chain([lips as f64]).chain(net.probe_lip_target)
                {{
                    out.write_all(&value.to_le_bytes())?;
                }}
            }}
            if frame + 1 == {frames} {{
                net.probe_lip_node = None;
                out.flush()?;
            }}
        }}
''')
    return prior.diff(original, path, 'tools/' + song.PROBE.name)


def patch_candidate(path, samples):
    original = path.read_text()
    anchor = '''            pcm::write(
                || {
                    step_audio(&mut voice, &mut pattern)
                        .map(|s| s.radiation.radiation_flow_derivative_cm3_s2)
                },
'''
    observer.edit(path, anchor, f'''            let mut lip_trace = std::env::var_os("CHIMERA_CSD_LIP_TRACE")
                .map(File::create_new).transpose()?.map(BufWriter::new);
            if lip_trace.is_some() {{
                voice.enable_lip_load_observation();
            }}
            let mut sample = 0;
            pcm::write(
                || {{
                    let next = step_audio(&mut voice, &mut pattern)?.radiation.radiation_flow_derivative_cm3_s2;
                    if let Some(out) = &mut lip_trace
                        && sample < {samples}
                    {{
                        let net = &voice.airway().network;
                        let lips = voice.airway().lips;
                        for value in net.probe_lip_pair[1].iter().chain(&net.probe_lip_geometry[1]).copied()
                            .chain([lips as f64]).chain(net.probe_lip_target)
                        {{
                            out.write_all(&value.to_le_bytes())
                                .map_err(|_| "口端の観測を書き出せません")?;
                        }}
                        sample += 1;
                        if sample == {samples} {{
                            out.flush().map_err(|_| "口端の観測を確定できません")?;
                        }}
                    }}
                    Ok(next)
                }},
''')
    return prior.diff(original, path, prior.RESEARCH)


def read_rows(path, count):
    rows = np.fromfile(path, dtype='<f8').reshape(-1, len(FIELDS))
    if len(rows) != count or not np.isfinite(rows).all() or not (rows[:, 0] == 1).all():
        raise ValueError('指定区間の口端負荷を採取できませんでした')
    return [dict(zip(FIELDS, row.tolist(), strict=True)) for row in rows]


def run(exe, files, spec, measure, execute, fixed, *, trace=None):
    wav, plan, state = files
    env = ['env', f'CHIMERA_CSD_LIP_TRACE={trace}'] if trace else []
    if fixed:
        execute([*env, str(exe), str(spec), 'matched', str(wav), str(state), str(plan)])
        return np.fromfile(wav, dtype='<f4')
    execute([*env, str(exe), 'render-pcm', str(spec), str(wav), '--no-trace', str(measure['block_frames'])])
    execute([str(exe), 'inspect', str(spec)], stdout=plan)
    return song.samples(wav, measure['sample_rate_hz'], measure['frames'])


def capture(study, spec, out, execute):
    m = study['measurement']
    begin, end = m['comparison_internal_samples']
    factor = m['internal_sample_rate_hz'] // m['sample_rate_hz']
    if begin != 0 or end <= 0 or end % factor:
        raise ValueError('口端を冒頭から完全な出力フレームで採取してください')
    traces, proof = {}, {}
    with TemporaryDirectory(prefix='csd-first-lip-', dir=out.parent / 'tmp') as directory:
        scratch = Path(directory)
        for name in MODES:
            root = scratch / name
            root.mkdir()
            fixed = name == 'upstream'
            if fixed:
                archive = scratch / 'upper.tar'
                execute(['git', 'archive', study['upstream_revision']], cwd=radiation.UPSTREAM, stdout=archive)
                execute(['tar', '-xf', str(archive), '-C', str(root)])
            else:
                test = radiation.WORKSPACE / 'crates/vocal-core/tests/geometry_ramp.rs'
                lip.copy_inputs((*radiation.candidate_sources(), lip.EMBEDDED_DICTIONARY,
                                 radiation.WORKSPACE / 'data/cmudict.txt.gz', test), root)
            target = root / 'target'
            flags = ('--offline', '--target-dir', str(target))
            package, *tests = TESTS[name]
            execute(['cargo', 'test', '--locked', '--release', *flags, '-p', package,
                     *(arg for test in tests for arg in ('--test', test))], cwd=root, stdout=out / f'{name}-tests.log')
            normal_files = tuple(scratch / f'{name}-normal.{ext}' for ext in ('wav', 'json', 'csv'))
            if fixed:
                stock = lip.build_upstream_probe(song.PROBE, scratch, execute, upstream=root, cargo_args=flags,
                                                 extra_libraries=('serde_json',))
            else:
                stock = lip.build_pcm_cli(False, root, flags, execute)
            ordinary = run(stock, normal_files, spec, m, execute, fixed)
            diff = patch_network(root, fixed, execute)
            if fixed:
                source = scratch / 'upstream_csd_first_lip_probe.rs'
                source.write_bytes(song.PROBE.read_bytes())
                diff += patch_upstream(source, end // factor)
                exe = lip.build_upstream_probe(source, scratch, execute, upstream=root, cargo_args=flags,
                                               extra_libraries=('serde_json',))
            else:
                diff += patch_candidate(root / prior.RESEARCH, end)
                exe = lip.build_pcm_cli(False, root, flags, execute)
            (out / f'{name}-observation.patch').write_text(diff)
            sampled_files = tuple(scratch / f'{name}-observed.{ext}' for ext in ('wav', 'json', 'csv'))
            trace = scratch / f'{name}-lip.f64le'
            observed = run(exe, sampled_files, spec, m, execute, fixed, trace=trace)
            traces[name] = read_rows(trace, end)
            proof[name] = {'ordinary': lip.pcm_digest(ordinary), 'observed': lip.pcm_digest(observed),
                           'ordinary_plan': tsp.read(normal_files[1]), 'observed_plan': tsp.read(sampled_files[1])}
    save(out / 'lip-observations.json', traces)
    save(out / 'pcm-digests.json', proof)


def bits_equal(actual, expected):
    return actual.hex() == expected.hex()


def swaps(events, rate, focus):
    results = {}
    for dest, src in (MODES, MODES[::-1]):
        source, target = (lip.load_inputs(events[name][focus]) for name in (src, dest))
        observed = target['lip_flow']
        wanted = source['lip_flow']
        gap = abs(wanted - observed)
        rows = []
        for count in (1, len(GROUPS)):
            for groups in combinations(GROUPS, count):
                additions = {key: source[key] for group in groups for key in GROUPS[group]}
                order = (src if 'arithmetic_order' in groups else dest) == 'upstream'
                result = replay(target | additions, rate, order)['lip_flow']
                rows.append({'groups': groups, 'lip_flow_cm3_s': result, 'matches_donor': bits_equal(result, wanted),
                             'residual_to_donor_cm3_s': result - wanted,
                             'recovered_fraction': 1.0 - abs(result - wanted) / gap if gap else None})
        results[dest] = rows
    return results


def analyze(study, out, reference):
    m = study['measurement']
    start, stop = m['comparison_internal_samples']
    focus, rate = m['focus_internal_sample'] - start, m['internal_sample_rate_hz']
    block = prior.UPSTREAM_CONTROL_OUTPUT_FRAMES * (rate // m['sample_rate_hz'])
    traces = tsp.read(out / 'lip-observations.json')
    proof = tsp.read(out / 'pcm-digests.json')
    prior_proof = tsp.read(tsp.verified_path(reference, 'artifacts/pcm-digests.json'))
    prior_names = dict(zip(MODES, prior.CONDITIONS, strict=True))
    archive = {}
    replays, geometry = {}, {}
    with np.load(tsp.verified_path(reference, 'artifacts/output-trace.npz'), allow_pickle=False) as saved:
        for name, rows in traces.items():
            old = prior_names[name]
            fixed = name == 'upstream'
            expected = saved[f'{old}_source'][start:stop, prior.SOURCE_FIELDS.index('lip_cm3_s')]
            trace = np.array([row['lip_flow_cm3_s'] for row in rows], dtype='<f8')
            plan = f'artifacts/{"upstream" if fixed else "research"}-plan.json'
            archive[name] = {'pcm': proof[name]['ordinary'] == proof[name]['observed']
                             == prior_proof[old]['observed'] == lip.pcm_digest(saved[f'{old}_pcm'])
                             and proof[name]['ordinary']['frames'] == m['frames'],
                             'plan': proof[name]['ordinary_plan'] == proof[name]['observed_plan']
                             == tsp.read(tsp.verified_path(reference, plan)),
                             'lip_flow': prior.prefix.load.same_bits(expected, trace)}
            geometry[name] = [lip.geometry(row, rate, fixed) for row in rows]
            pole = -math.expm1(-math.tau * m['volume_source_cutoff_hz'] / rate)
            prev, next_row = rows
            increments = {'area_increment': 'old_area', 'length_increment': 'old_length',
                          'minimum_increment': 'old_minimum'}
            replays[name] = {
                'control_target_to_increment': all(bits_equal(
                    (prev[target] - prev[initial]) * (1.0 / block), prev[key])
                    and bits_equal(prev[key], next_row[key])
                    for (key, initial), target in zip(increments.items(), TARGET_FIELDS, strict=True)),
                'geometry_and_filter': all(all(g[k] for k in ('matches_dimensions_and_volume',
                                                             'matches_filter', 'matches_geometry_inflow'))
                                           for g in geometry[name]),
                'volume_and_filter_history': all(bits_equal(prev[a], next_row[b]) for a, b in (
                    ('area_cm2', 'old_area'), ('minimum', 'old_minimum'), ('length_cm', 'old_length'),
                    ('volume', 'old_volume'), ('first_pole', 'old_first_pole'), ('second_pole', 'old_second_pole'))),
                'volume_pole_coefficient': all(abs(row['pole_coefficient'] - pole)
                                               <= m['volume_pole_absolute_tolerance'] for row in rows),
                'load_coefficients': all(load_coefficients(row) for row in rows),
                'load': all(lip.solve_matches(row, rate, fixed) for row in rows),
            }
    event = {name: traces[name][focus] for name in MODES}
    exchanges = swaps(traces, rate, focus)
    changed = {field: next((start + i for i, (up, candidate) in enumerate(zip(*traces.values(), strict=True))
                            if up[field] != candidate[field]), None)
               for field in FIELDS}
    hypotheses = {
        'first_load_starts_at_rest': all(
            row['old_pressure_dyn_cm2'] == row['old_inertance_flow_cm3_s'] == 0.0
            and row['geometry_inflow_cm3_s'] == row['before_wall_inflow_cm3_s'] == row['inflow_cm3_s']
            for row in event.values()),
        'geometry_flow_explains_first_lip_delta': all(
            rows[0]['recovered_fraction'] is not None
            and rows[0]['recovered_fraction'] >= m['minimum_flow_exchange_recovery']
            for rows in exchanges.values()),
        'volume_difference_precedes_lip_delta': all(changed[key] == m['focus_internal_sample']
                                                    for key in ('spill', 'second_pole', 'inflow_cm3_s', 'lip_flow_cm3_s')),
    }
    return {
        'checks': {
            'ordinary_and_observed_song_and_prior_trace_match': all(all(row.values()) for row in archive.values()),
            'first_control_geometry_and_filter_replayed': all(all(row[key] for key in (
                'control_target_to_increment', 'geometry_and_filter', 'volume_and_filter_history',
                'volume_pole_coefficient')) for row in replays.values()),
            'load_coefficients_and_update_replayed': all(row['load_coefficients'] and row['load'] for row in replays.values()),
            'full_input_exchange_reconstructs_donor': all(rows[-1]['matches_donor'] for rows in exchanges.values()),
        },
        'archive_matches': archive, 'replays': replays, 'hypotheses': hypotheses, 'first_differences': changed,
        'geometry_replay': geometry, 'first_volume_rounding': lip.volume_rounding(event, rate),
        'focus_lip_flow_cm3_s': {name: row['lip_flow_cm3_s'] for name, row in event.items()},
        'load_exchanges_at_focus': exchanges,
    }


def load_coefficients(row):
    density, speed, pi = 0.00114, 35000.0, math.pi
    area = max(row['area_cm2'], 1e-4)
    return all(bits_equal(value, row[key]) for value, key in (
        (row['volume'] / (density * speed * speed), 'compliance_cm5_dyn'),
        ((8.0 * density) / (3.0 * pi * math.sqrt(pi * area)), 'inertance_g_cm4'),
        ((128.0 * density * speed) / (9.0 * pi * pi * area), 'resistance_dyn_s_cm5'),
    ))


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
    reference, render = (tsp.open_run(study[key], revision) for key in ('reference', 'render'))
    spec = tsp.verified_path(render, 'artifacts/candidate-short-128.json')
    input_files = ['output-trace.npz', 'pcm-digests.json', 'upstream-plan.json', 'research-plan.json']
    inputs = [CASE, Path(__file__).resolve(), Path(prior.__file__), Path(observer.__file__),
              Path(lip.__file__), Path(lip.replay.__code__.co_filename).resolve(),
              Path(song.__file__), Path(radiation.__file__),
              observer.UPPER_PATCH, observer.LOCAL_PATCH, song.PROBE, spec,
              *(run[0] / 'manifest.json' for run in (reference, render)),
              *(tsp.verified_path(reference, f'artifacts/{name}') for name in input_files),
              *prior.prefix.capture_dependencies(),
              ws / 'crates/vocal-core/tests/geometry_ramp.rs',
              *(upper / 'crates/chimera/tests' / f'{test}.rs' for test in TESTS['upstream'][1:])]

    def measure(out, execute):
        capture(study, spec, out, execute)
        return analyze(study, out, reference)

    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return radiation.record_measurement(args.run_id, CASE, inputs, details, measure, command=None, input_root=ws.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
