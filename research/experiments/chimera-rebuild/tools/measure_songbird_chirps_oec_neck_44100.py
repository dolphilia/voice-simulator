"""鳴禽の気管側首部について、流量の最初の差を局所的に照合する。"""

import argparse
import itertools
import math
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from measure_songbird_airway import FIELDS, PROBE
from measure_songbird_chirps_beak_load import DENSITY, ROOT, beak_fields
from measure_songbird_chirps_beak_tip_inflow import UPPER_NETWORK, UPPER_SONGBIRD, solve
from measure_songbird_chirps_beak_tip_inflow_44100 import registered_artifacts
from measure_songbird_chirps_oec_pressure_44100 import CANDIDATE_OEC, CONDITIONS, OEC
from measure_songbird_chirps_terminal_numerator_44100 import PREFIX_PATCHES, first_offset, same_bits
from measure_songbird_chirps_volume_rate_propagation_44100 import build_and_render, stage_candidate
from measure_songbird_syrinx import load_trace
from measure_speech_timing import read, write
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/songbird-chirps-oec-neck-44100.json'
BASE_ID = 'songbird-chirps-terminal-numerator-44100'
TRACHEA_PRESSURE, TRACHEA_AREA, TRACHEA_LENGTH, NECK_AREA, NOISE = NECK_FIELDS = (
    'trachea_end_pressure_dyn_cm2', 'trachea_end_area_cm2', 'trachea_end_cell_length_cm',
    'oec_neck_area_cm2', 'oec_neck_noise_pressure_dyn_cm2',
)
CAVITY_PRESSURE, CAVITY_AREA, CAVITY_LENGTH, FLOW = (
    'oec_pressure_dyn_cm2', 'oec_area_cm2', OEC[0], OEC[1],
)


def impedance(row, neck, *, upstream):
    ends = tuple(float(row[key]) for key in (TRACHEA_AREA, CAVITY_AREA))
    lengths = tuple(float(row[key]) for key in (TRACHEA_LENGTH, CAVITY_LENGTH))
    return port_impedance(float(row[NECK_AREA]), ends, lengths, neck, upstream=upstream)


def port_impedance(area, end_areas, lengths, port, *, upstream, multiply_left_half=False):
    length = port['length_cm']
    inverse = 1 / area
    half_density = 0.5 * DENSITY
    inverse_ends = tuple(1 / value for value in end_areas)
    if upstream:
        half_terms = [size * reciprocal for size, reciprocal in zip(lengths, inverse_ends, strict=True)]
    else:
        half_terms = [size / value for size, value in zip(lengths, end_areas, strict=True)]
        if multiply_left_half:
            half_terms[0] = lengths[0] * inverse_ends[0]
    inertance = DENSITY * length * inverse + half_density * sum(half_terms)
    viscosity = math.sqrt(DENSITY * 1.86e-4 * (math.tau * port['viscosity_reference_hz']) / 2)
    resistance = viscosity * 2 * math.sqrt(math.pi) * length * math.sqrt(area)
    resistance = (resistance * inverse * inverse if upstream else resistance * (inverse * inverse))
    entry = port['entrance_loss'] * half_density
    entry = entry * inverse * inverse if upstream else entry * (inverse * inverse)
    losses = []
    for downstream_inverse in reversed(inverse_ends):
        jump = max(0.0, inverse - downstream_inverse)
        expansion = half_density * (jump * jump)
        losses.append(entry + port['expansion_loss'] * expansion)
    return inertance, resistance, *losses


def evaluate(terms):
    drive = terms['pressure_difference'] + terms['noise_pressure'] + terms['normalized_momentum']
    linear = terms['normalized_inertance'] + terms['resistance']
    loss = terms['forward_loss'] if drive >= 0 else terms['reverse_loss']
    denominator, flow = solve(drive, linear, loss)
    return {'drive': drive, 'linear': linear, 'loss': loss, 'denominator': denominator, 'flow': flow}


def replay(trace, start, rate, neck, *, upstream, multiply_momentum=False, multiply_linear=False):
    dt = 1 / rate
    old_inertance, *_ = impedance(trace[start - 1], neck, upstream=upstream)
    result = []
    for prior, now in zip(trace[start - 1:-1], trace[start:], strict=True):
        inertance, resistance, forward, reverse = impedance(now, neck, upstream=upstream)
        carried = min(old_inertance, inertance)
        old_flow = float(prior[FLOW])
        a, b = float(prior[TRACHEA_PRESSURE]), float(prior[CAVITY_PRESSURE])
        momentum = (carried * old_flow) * rate if upstream or multiply_momentum else (carried / dt) * old_flow
        terms = {'pressure_difference': a - b, 'noise_pressure': float(now[NOISE]),
                 'normalized_momentum': momentum,
                 'normalized_inertance': inertance * rate if upstream or multiply_linear else inertance / dt,
                 'resistance': resistance, 'forward_loss': forward, 'reverse_loss': reverse}
        initial = {'trachea_pressure': a, 'cavity_pressure': b, 'previous_flow': old_flow,
                   'previous_inertance': old_inertance, 'current_inertance': inertance}
        result.append({'previous_state': initial, 'terms': terms, 'result': evaluate(terms), 'observed': float(now[FLOW])})
        old_inertance = inertance
    return result


def diagnose(candidate, upstream, offset, rate, *, pressure_keys=('trachea_pressure', 'cavity_pressure')):
    if offset is None:
        return None
    c, u = candidate[offset], upstream[offset]
    base, reference = c['terms'], u['terms']
    previous = c['previous_state']
    carried = min(previous['previous_inertance'], previous['current_inertance'])
    changes = [key for key in base if base[key].hex() != reference[key].hex()]
    swaps = {}
    for size in range(1, len(changes) + 1):
        for keys in itertools.combinations(changes, size):
            swapped = base | {key: reference[key] for key in keys}
            flow = evaluate(swapped)['flow']
            swaps['+'.join(keys)] = {'flow': flow, 'matches_upstream': flow.hex() == u['observed'].hex()}
    time_order = evaluate(base | {'normalized_inertance': previous['current_inertance'] * rate,
                                  'normalized_momentum': (carried * previous['previous_flow']) * rate})
    pressure_swaps = {}
    for key in pressure_keys:
        states = previous | {key: u['previous_state'][key]}
        updated = evaluate(base | {'pressure_difference': states[pressure_keys[0]] - states[pressure_keys[1]]})
        pressure_swaps[key] = {'flow': updated['flow'], 'matches_upstream': updated['flow'].hex() == u['observed'].hex()}
    return {'offset': offset, 'candidate': c, 'upstream': u, 'different_terms': changes, 'term_swaps': swaps,
            'pressure_swaps': pressure_swaps, 'time_order_only': {
                'result': time_order, 'matches_upstream': time_order['flow'].hex() == u['observed'].hex()}}


def prefix_columns_match(extended, archived):
    old = archived.read_bytes().splitlines()
    new = extended.read_bytes().splitlines()
    columns = old[0].count(b',') + 1
    return len(new) <= len(old) and all(
        b','.join(row.split(b',')[:columns]) == previous
        for row, previous in zip(new, old[:len(new)], strict=True))


def measure(case, saved, baseline_inputs, patches, snapshot, copies, out, execute):
    rate, window = case['sample_rate_hz'], case['observation_internal_samples']
    settings, paths = {}, {}
    for name in CONDITIONS:
        config = read(baseline_inputs[f'{name}.json'])
        settings[name] = out / f'{name}.json'
        paths[name] = out / f'{name}-candidate.csv'
        bird = config['songbird_airway']
        event, = bird['events']
        start = case['condition_control_samples'][name]
        if (bird['sample_rate_hz'], bird['control_block_samples'], event['sample'], bird['breath_gate'],
                event['breath_gate'], bird['observe_oec'], bird['observe_beak']) != (rate, start, start, 0, 0, True, True):
            raise ValueError(f'鳴禽の固定ケースと観測条件が一致しません ({name})')
        bird['sample_count'] = start + window
        bird['observe_oec_neck'] = True
        write(settings[name], config)

    with TemporaryDirectory(prefix='oec-neck-', dir=out.parent) as temporary:
        scratch = Path(temporary)
        work = scratch / 'candidate'
        stage_candidate(snapshot, copies, work)
        for patch in patches:
            execute(['git', 'apply', '--check', str(patch)], cwd=work)
            execute(['git', 'apply', str(patch)], cwd=work)
        binary = build_and_render(work, scratch / 'target', settings, paths, execute)
    probe = build_upstream_probe(PROBE, out, execute, extra_libraries=('serde_json',), cargo_args=('--offline',))
    baseline_build = read(saved['summary.json'])['build']
    checks = {'preceding_patches_match_baseline': [sha256(path) for path in patches] ==
              [*baseline_build['preceding_patch_sha256'], baseline_build['inlet_patch_sha256']]}
    common = FIELDS + beak_fields(6) + OEC
    all_replays, results = {}, {}
    for name, config in settings.items():
        start = case['condition_control_samples'][name]
        files = {'candidate': paths[name], 'upstream': out / f'{name}-upstream.csv'}
        execute([str(probe), str(config)], cwd=UPSTREAM, stdout=files['upstream'])
        archived = {'candidate': saved[f'artifacts/{name}-terminal-numerator.csv'],
                    'upstream': baseline_inputs[f'{name}-upstream.csv']}
        traces, all_replays[name] = {}, {}
        for side, path in files.items():
            checks[f'{name}/{side}/earlier_columns_match'] = prefix_columns_match(path, archived[side])
            fields = common + (CANDIDATE_OEC if side == 'candidate' else ()) + NECK_FIELDS
            trace = traces[side] = load_trace(path, fields, start + window)
            series = all_replays[name][side] = replay(trace, start, rate, case['neck'], upstream=side == 'upstream')
            checks[f'{name}/{side}/neck_flow_bit_replayed'] = all(
                row['observed'].hex() == row['result']['flow'].hex() for row in series)
            checks[f'{name}/{side}/fixed_open_neck_without_noise'] = bool(
                (trace[NECK_AREA] == case['neck']['area_cm2']).all() and (trace[NOISE] == 0).all())
            if name == 'no_tracking':
                checks[f'{name}/{side}/flow_and_pressures_zero'] = all(
                    (trace[key] == 0).all() for key in (FLOW, TRACHEA_PRESSURE, CAVITY_PRESSURE))
        candidate, upstream = (traces[side][start:] for side in files)
        offsets = {key: first_offset(candidate[key], upstream[key])
                   for key in (FLOW, TRACHEA_PRESSURE, CAVITY_PRESSURE, TRACHEA_AREA, CAVITY_AREA)}
        checks[f'{name}/geometry_bit_equal'] = all(same_bits(candidate[key], upstream[key])
                                                   for key in (TRACHEA_AREA, TRACHEA_LENGTH,
                                                               CAVITY_AREA, CAVITY_LENGTH, NECK_AREA))
        checks[f'{name}/earlier_first_flow_difference_reproduced'] = offsets[FLOW] == case['expected_first_flow_differences'][name]
        diagnosis = diagnose(all_replays[name]['candidate'], all_replays[name]['upstream'], offsets[FLOW], rate)
        results[name] = {'first_difference': offsets, 'first_flow_diagnosis': diagnosis}
    write(out / 'neck-flow-replay.json', all_replays)
    matched = results['matched_time']['first_flow_diagnosis']
    hypotheses = {'previous_cavity_pressure_and_neck_flow_equal': all(
        matched['candidate']['previous_state'][key].hex() == matched['upstream']['previous_state'][key].hex()
        for key in ('cavity_pressure', 'previous_flow')),
        'time_order_on_its_own_restores_matched_time_flow': matched['time_order_only']['matches_upstream']}
    return {'checks': checks, 'hypotheses': hypotheses, 'sample_rate_hz': rate, 'window': window,
            'candidate_binary_sha256': binary, 'conditions': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    names = ('summary.json', 'artifacts/terminal-numerator.patch',
             *(f'artifacts/{name}-terminal-numerator.csv' for name in CONDITIONS))
    manifest, saved = registered_artifacts(case['baseline'], BASE_ID, revision, names)
    baseline_inputs = {}
    for name in (*PREFIX_PATCHES, 'oec-sum-order.patch',
                 *(f'{name}{suffix}' for name in CONDITIONS for suffix in ('.json', '-upstream.csv'))):
        entry, = (row for row in read(manifest)['inputs'] if row['path'].endswith(f'/artifacts/{name}'))
        path = ROOT / entry['path']
        if path.stat().st_size != entry['bytes'] or sha256(path) != entry['sha256']:
            parser.error(f'先行実行の入力が保存時と一致しません ({name})')
        baseline_inputs[name] = path
    patches = [*(baseline_inputs[name] for name in (*PREFIX_PATCHES, 'oec-sum-order.patch')),
               saved['artifacts/terminal-numerator.patch']]
    copies = [*candidate_sources(), WORKSPACE / 'data/cmudict.txt.gz', WORKSPACE / 'data/mandarin.txt.gz']
    tools = [WORKSPACE / 'tools' / name for name in (
        'measure_songbird_airway.py', 'measure_songbird_chirps_beak_load.py', 'measure_songbird_chirps_beak_tip_inflow.py',
        'measure_songbird_chirps_beak_tip_inflow_44100.py', 'measure_songbird_chirps_oec_pressure_44100.py',
        'measure_songbird_chirps_terminal_numerator_44100.py', 'measure_songbird_chirps_volume_rate_propagation_44100.py',
        'measure_songbird_syrinx.py', 'measure_speech_timing.py', 'measure_uniform_tube.py')]
    inputs = [CASE, Path(__file__), PROBE, manifest, *saved.values(), *baseline_inputs.values(), *copies,
              *tools, UPPER_NETWORK, UPPER_SONGBIRD, UPSTREAM / 'crates/chimera/tests/airway_adversarial.rs']
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    snapshot = WORKSPACE / 'runs' / args.run_id / 'artifacts/source'
    return record_measurement(args.run_id, CASE, inputs, details,
                              lambda out, execute: measure(case, saved, baseline_inputs, patches, snapshot, copies, out, execute),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
