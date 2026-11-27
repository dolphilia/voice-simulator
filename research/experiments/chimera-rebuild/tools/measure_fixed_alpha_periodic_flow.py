"""保存した声門流量を固定 /ɑ/ に再入力し、口端の複素比を照合する。"""

import argparse
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

import numpy as np

import measure_fixed_alpha_mean_flow as mean
from measure_fan_crossing_allocations import run_manifest, verified_path
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-alpha-periodic-flow.json'
ARMS = ('coupled', 'lf')
MODES = ('periodic', 'full')
JOBS = ('dc', *(f'{arm}-{mode}' for arm in ARMS for mode in MODES))
RESPONSES = ('pressure_pharynx_entry', 'pressure_junction', 'pressure_lips',
             'flow_oral_link', 'flow_lips', 'flow_walls')
EVIDENCE = ('replay-traces.npz', 'capture.json', *(f'{job}.json' for job in JOBS))
READ = mean.impulse.harmonic.read
LF = mean.impulse.harmonic.lf
FIELDS = mean.TRACE_FIELDS
EDITIONS = mean.EDITIONS


def archive_inputs(study):
    output = {}
    for key, spec in study['references'].items():
        run, header = record = run_manifest(spec['run'], spec['case'], study['upstream_revision'])
        manifest = run / 'manifest.json'
        if header['status'] != 'pass' or sha256(manifest) != spec['sha256']:
            raise ValueError(f'保存実行の判定またはハッシュが一致しません ({run.name})')
        output[f'{key}-manifest.json'] = manifest
        if key == 'voiced':
            output['source.npz'] = verified_path(record, 'artifacts/radiation-observations.npz')
            continue
        output['mean-summary.json'] = verified_path(record, 'summary.json')
        row, = [item for item in header['inputs'] if item['path'].endswith(f'/cases/{spec["case"]}.json')]
        case = run / header['source_snapshot'] / row['path']
        if sha256(case) != row['sha256']:
            raise ValueError('保存された定常流ケースのハッシュが一致しません')
        output['mean-case.json'] = case
        archive = mean.archive_inputs(READ(case))
        for name in ('large-case.json', 'upstream-geometry.csv', *mean.impulse.harmonic.NETWORK_FILES):
            output[name] = archive[name]
    return output


def drive_cases(study, sources, traces):
    cfg = study['measurement']
    begin, end = cfg['steady_window_samples']
    start = cfg['warmup_samples']
    block = end - begin
    interval = start + block * cfg['periodic_blocks']
    layout = READ(sources['large-case.json'])
    q_index = LF.OBSERVED.index(LF.Q)
    for job in JOBS:
        case = {**layout, 'id': f'{study["id"]}-{job}', 'hypothesis': study['hypothesis']}
        case['fixed_airway'] = {'sample_count': interval, 'sample_rate_hz': cfg['internal_rate_hz'],
                               'impulse_volume_cm3': 0, 'steady_flow_cm3_s': cfg['steady_flow_cm3_s']}
        if job != 'dc':
            arm, mode = job.split('-')
            flow = traces[f'{arm}_upstream'][:, q_index]
            if mode == 'periodic':
                wave, onset = flow[begin:end], start
            else:
                wave, onset = flow, 0
                case['fixed_airway'].update(sample_count=len(flow), steady_flow_cm3_s=0)
            case['fixed_airway_periodic_flow'] = {'start_sample': onset, 'flow_cm3_s': [repr(float(x)) for x in wave]}
        yield job, case


def capture(study, sources, out, execute):
    with np.load(sources['source.npz'], allow_pickle=False) as original:
        capture_cases(study, sources, out, execute, drive_cases(study, sources, original),
                      full_history_jobs=tuple(f'{arm}-full' for arm in ARMS))


def capture_cases(study, sources, out, execute, cases, *, full_history_jobs=()):
    cfg = study['measurement']
    begin, end = cfg['steady_window_samples']
    block = end - begin
    start = cfg['warmup_samples']
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'airway_adversarial',
             'steady_flow_through_a_short_constriction_obeys_bernoulli_with_jet_loss'], cwd=UPSTREAM,
            stdout=out / 'upstream-kinetic-test.log')
    probe = mean.shared.build_upstream_probe(mean.sagittal.PROBE, out, execute, cargo_args=('--offline',))
    cli = ['cargo', 'run', '--locked', '--offline', '--release', '-p', 'vocal-cli', '--']
    pose = mean.sagittal.pose_controls(READ(sources['large-case.json']))
    results, meta = {}, {}
    with TemporaryDirectory(prefix='periodic-csv-', dir=out) as temporary:
        scratch = Path(temporary)
        for job, case in cases:
            target = out / f'{job}.json'
            target.write_text(json.dumps(case, ensure_ascii=False, separators=(',', ':')) + '\n')
            shape = case['fixed_airway']
            count = shape['sample_count']
            raw = {}
            for edition in EDITIONS:
                path = scratch / f'{edition}.csv'
                if edition == 'candidate':
                    execute([*cli, 'render', str(target), str(path)])
                else:
                    args = [shape['sample_rate_hz'], count]
                    if replay := case.get('fixed_airway_periodic_flow'):
                        stimulus = scratch / 'flow.txt'
                        stimulus.write_text('\n'.join(replay['flow_cm3_s']) + '\n')
                        command = '--fixed-airway-periodic'
                        args.extend((replay['start_sample'], shape['steady_flow_cm3_s'], stimulus))
                    else:
                        command = '--fixed-airway-bias'
                        args.extend((0, 0, shape['steady_flow_cm3_s']))
                    execute([str(probe), command, *map(str, args), *pose], cwd=UPSTREAM, stdout=path)
                raw[edition] = mean.fixed.read_trace(path, FIELDS, count)
                path.unlink()
                if job in full_history_jobs:
                    results[f'{job}_{edition}'] = raw[edition]
                    continue
                results[f'{job}_{edition}'] = raw[edition][-2 * block:].copy()
                results[f'{job}_{edition}_start'] = raw[edition][start:start + cfg['after_onset_samples_to_keep']].copy()
            peak = abs(raw['upstream']).max(axis=0)
            error = abs(raw['candidate'] - raw['upstream']) / np.where(peak > 0, peak, 1.0)
            exceeded = np.flatnonzero((error >= cfg['upstream_trace_peak_relative_error_lt']).any(axis=1))
            meta[job] = {'samples': count, 'upstream_peak_relative_error': error.max(axis=0).tolist(),
                         'first_sample_over_tolerance': int(exceeded[0]) if exceeded.size else None}
            if job not in full_history_jobs:
                meta[job]['prefix_sha256'] = {edition: mean.sha_array(raw[edition][:start]) for edition in EDITIONS}
    np.savez_compressed(out / 'replay-traces.npz', **results)
    (out / 'capture.json').write_text(json.dumps(meta, indent=2) + '\n')


def linear_prediction(study, sources):
    cfg = study['measurement']
    nodes, branches, source = mean.impulse.source_elements(sources)
    _, geometry = mean.fixed.read_upper_geometry(sources['upstream-geometry.csv'])
    rate = cfg['internal_rate_hz']
    compliance, active = mean.impulse.compliance_floor(nodes, branches, source, rate)
    path = mean.airway_path(branches, active, source)
    branches[path[:, 2], 4] += 2 * mean.drag_on_path(path, geometry) * cfg['steady_flow_cm3_s']
    response = mean.impulse.discrete_response(cfg['frequencies_hz'], rate, nodes, branches, source, compliance, active)
    return response, compliance[source['inject']], len(path)


def transfer(projection, bins, response, source):
    count = len(source)
    augmented = np.column_stack((response, source))
    direct = projection @ augmented / count
    fft = np.fft.rfft(augmented, axis=0)[bins] / count
    error = float(abs(fft - direct).max() / abs(direct).max())
    return direct[:, :-1] / direct[:, -1:], error


def first_difference(candidate, reference, tolerance):
    error = abs(candidate - reference)
    maximum = float(abs(reference).max())
    exceed = np.flatnonzero(error > tolerance * maximum)
    return {'first_sample': int(exceed[0]) if exceed.size else None,
            'peak_relative_error': float(error.max() / maximum) if maximum else None}


def analyze_arm(study, arm, original, trace, capture_meta, projection, bins, model, compliance, hops):
    cfg = study['measurement']
    begin, end = cfg['steady_window_samples']
    block = end - begin
    q = original[f'{arm}_upstream'][:, LF.OBSERVED.index(LF.Q)]
    history = original[f'{arm}_upstream']
    columns = [FIELDS.index(name) for name in RESPONSES]
    matching = [RESPONSES.index(name) for name in mean.RESPONSE_FIELDS]
    lip = RESPONSES.index('flow_lips')
    steady = cfg['steady_flow_cm3_s']
    q_window = q[begin:end] - steady
    original_lip = history[begin:end, LF.OBSERVED.index(LF.LIP)]
    original_ratio, old_fft_error = transfer(projection, bins, original_lip[:, None], q_window)
    checks = {'archive_mean_flow': abs(float(q[begin:end].mean()) - steady) < cfg['steady_mean_match_abs_lt_cm3_s']}
    values = {}
    for edition in EDITIONS:
        periodic = trace[f'{arm}-periodic_{edition}']
        full = trace[f'{arm}-full_{edition}']
        dc = trace[f'dc_{edition}']
        difference = (periodic - dc)[:, columns]
        start = trace[f'{arm}-periodic_{edition}_start'] - trace[f'dc_{edition}_start']
        prefix = f'{edition}/'
        checks[prefix + 'same_state_before_periodic_drive'] = (
            capture_meta[f'{arm}-periodic']['prefix_sha256'][edition] == capture_meta['dc']['prefix_sha256'][edition])
        expected = q_window[0] / (compliance * cfg['internal_rate_hz'])
        checks[prefix + 'causal_injection_and_lip_arrival'] = (
            abs(start[0, FIELDS.index('pressure_pharynx_entry')] - expected)
            < cfg['first_inlet_pressure_relative_error_lt'] * abs(expected)
            and np.all(start[:hops, FIELDS.index('flow_lips')] == 0)
            and np.any(start[hops:, FIELDS.index('flow_lips')]))
        a, first = transfer(projection, bins, difference[:block], q_window)
        b, last = transfer(projection, bins, difference[block:], q_window)
        whole, whole_error = transfer(projection, bins, full[begin:end, columns], q_window)
        periodic_error = float(abs(a / b - 1).max())
        checks[prefix + 'late_blocks_converge'] = periodic_error < cfg['settled_harmonic_complex_relative_change_lt']
        checks[prefix + 'fft_and_direct_fourier'] = max(first, last, whole_error, old_fft_error) < cfg['dft_relative_error_lt']
        earliest = {}
        for key, field in [('pressure_supra_dyn_cm2', 'pressure_pharynx_entry'), (LF.LIP, 'flow_lips'),
                           ('nose_flow_cm3_s', 'flow_nose'), (LF.RAD, 'radiation_derivative')]:
            earliest[key] = first_difference(full[:, FIELDS.index(field)], history[:, LF.OBSERVED.index(key)],
                                             cfg['original_trace_first_difference_peak_relative_gt'])
        values[edition] = {
            'last_two_block_complex_relative_error': periodic_error,
            'first_inlet_pressure_change_dyn_cm2': float(start[0, FIELDS.index('pressure_pharynx_entry')]),
            'whole_history_first_differences': earliest,
            'relative_periodic_vs_linear_at_all_observers': abs(b[:, matching] / model - 1).tolist(),
            'periodic_frequency_response': [[mean.impulse.harmonic.pair(item) for item in row] for row in b],
            'whole_history_frequency_response': [[mean.impulse.harmonic.pair(item) for item in row] for row in whole],
        }
    rows = []
    close = True
    nonlinear = False
    for i, f in enumerate(cfg['frequencies_hz']):
        periodic = complex(*values['candidate']['periodic_frequency_response'][i][lip])
        whole = complex(*values['candidate']['whole_history_frequency_response'][i][lip])
        voiced = original_ratio[i, 0]
        reference = model[i, mean.RESPONSE_FIELDS.index('flow_lips')]
        periodic_error = float(abs(periodic / voiced - 1))
        close &= periodic_error < cfg['hypothesized_max_relative_complex_lip_error_vs_voiced']
        residual = float(abs(periodic / reference - 1))
        nonlinear |= residual > cfg['observable_periodic_vs_linear_complex_relative_gt']
        rows.append({
            'frequency_hz': f,
            'transfer': {key: mean.impulse.harmonic.pair(value) for key, value in (
                ('linear_at_mean', reference), ('periodic', periodic), ('whole_history', whole), ('original', voiced))},
            'periodic_over_linear_at_mean': mean.impulse.ratio(periodic, reference),
            'periodic_over_original': mean.impulse.ratio(periodic, voiced),
            'whole_history_over_original': mean.impulse.ratio(whole, voiced),
            'periodic_relative_complex_error_to_original': periodic_error,
            'whole_history_relative_complex_error_to_original': float(abs(whole / voiced - 1)),
            'linear_relative_complex_error_to_original': float(abs(reference / voiced - 1)),
        })
    return checks, {'editions': values, 'frequencies': rows, 'hypotheses': {
        'periodic_deviation_from_linear_is_detectable': bool(nonlinear),
        'periodic_lip_transfer_close_to_original_at_both_frequencies': bool(close)}}


def analyze(study, sources, out):
    cfg = study['measurement']
    begin, end = cfg['steady_window_samples']
    block = end - begin
    fs = cfg['internal_rate_hz']
    frequency = np.array(cfg['frequencies_hz'])
    bins = (frequency * block // fs).astype(int)
    projection = np.exp(-2j * np.pi / fs * np.outer(frequency, np.arange(block)))
    capture_meta = READ(out / 'capture.json')
    model, compliance, hops = linear_prediction(study, sources)
    archived = READ(sources['mean-summary.json'])['time_domain']['voiced_mean']['edition']['upstream']['frequency_response']
    prior = np.array([[complex(*part) for part in row] for row in archived])
    checks = {
        'registered_integer_cycles_and_fft_bins': (
            cfg['f0_hz'] * block == cfg['cycles_per_block'] * fs and np.array_equal(bins * fs / block, frequency)),
        'independent_linear_prediction_reproduces_mean_flow_response': bool(
            np.all(abs(model / prior - 1) < cfg['linear_model_previous_relative_error_lt'])),
    }
    arms = {}
    with (
        np.load(sources['source.npz'], allow_pickle=False) as original,
        np.load(out / 'replay-traces.npz', allow_pickle=False) as trace,
    ):
        for job, case in drive_cases(study, sources, original):
            meta = capture_meta[job]
            checks[f'{job}/input_shape_and_upstream_full_series'] = (
                case == READ(out / f'{job}.json') and meta['samples'] == case['fixed_airway']['sample_count']
                and meta['first_sample_over_tolerance'] is None
                and max(meta['upstream_peak_relative_error']) < cfg['upstream_trace_peak_relative_error_lt'])
        for arm in ARMS:
            condition, arms[arm] = analyze_arm(
                study, arm, original, trace, capture_meta, projection, bins, model, compliance, hops)
            checks.update({f'{arm}/{key}': value for key, value in condition.items()})
    return {'checks': {key: bool(value) for key, value in checks.items()}, 'conditions': arms,
            'response_fields': list(RESPONSES), 'all_trace_comparisons': capture_meta}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('英数字で始まる実行IDを指定してください')
    study = READ(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    sources = archive_inputs(study)

    def measure(out, execute):
        capture(study, sources, out, execute)
        return analyze(study, sources, out)

    inputs = [CASE, Path(__file__), *sources.values(), *mean.shared.candidate_sources(), mean.sagittal.PROBE,
              *(Path(module.__file__) for module in (mean, mean.impulse, mean.fixed, mean.sagittal, mean.shared)),
              UPSTREAM / 'crates/chimera/src/airway/network.rs', UPSTREAM / 'crates/chimera/src/voice/human_voice.rs',
              UPSTREAM / 'crates/chimera/tests/airway_adversarial.rs']
    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return mean.shared.record_measurement(args.run_id, CASE, inputs, details, measure, command=None,
                                          input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
