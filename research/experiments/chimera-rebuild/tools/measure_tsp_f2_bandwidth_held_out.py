"""TSP確認用の未使用10母音で、F2帯域幅条件による置換と欠測を測る。"""

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import subprocess

import numpy as np

import measure_tsp_f2_bandwidth_envelope as pilot
import measure_tsp_stressed_vowel_formants as base
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/tsp-f2-bandwidth-held-out.json'


def saved_case(run, path):
    root, manifest = run
    relative = path.relative_to(WORKSPACE.parents[2]).as_posix()
    expected = next(row['sha256'] for row in manifest['inputs'] if row['path'] == relative)
    snapshot = root / manifest['source_snapshot'] / relative
    if sha256(snapshot) != expected:
        raise ValueError(f'先行ケースの記録を照合できません ({relative})')
    return base.read(snapshot), snapshot


def pair(selection):
    return [selection[name][0] for name in ('f1', 'f2')] if selection['reason'] is None else None


def selection_error(actual, expected):
    if actual['reason'] != expected['reason']:
        return None
    errors = [base.max_error(actual[name], expected[name]) for name in ('f1', 'f2')]
    return max(errors) if None not in errors else None


def inspect_window(observed, reference, cfg, limit):
    poles = reference['poles']
    fixed = pilot.select(poles, cfg)
    alternate = pilot.select(poles, cfg, limit)
    alternate_independent = pilot.select(observed['poles'], cfg, limit)
    comparison, = base.compare_windows([observed], [reference], cfg)
    if reference['reason'] != fixed['reason']:
        raise ValueError('固定規則の欠測理由が保存記録と一致しません')
    available = [p for p in poles if fixed['f1'] and cfg['f2_min_gap_hz'] + fixed['f1'][0] < p[0] < cfg['f2_max_frequency_hz']]
    change = 'unchanged'
    shift = None
    if fixed['f2'] and alternate['f2'] is None:
        change = 'new_missing'
    elif fixed['f2'] != alternate['f2']:
        change = 'replaced'
        shift = alternate['f2'][0] - fixed['f2'][0]
    return {'fixed': fixed, 'bandwidth_limited': alternate, 'transition': change, 'f2_shift_hz': shift,
            'fixed_frequency_eligible_poles': available, 'initial_pole_comparison': comparison,
            'fixed_selection_error_hz': base.max_error(pair(fixed), reference['f1_f2_hz']),
            'bandwidth_limited_independent_error_hz': selection_error(alternate, alternate_independent)}


def windows(case, cfg, saved, reference, data):
    fs = cfg['sample_rate_hz'] / cfg['decimation']
    length = int(cfg['frame_seconds'] * fs)
    frames, rows, median_references = [], [], {}
    limit = case['measurement']['candidate_f2_bandwidth_limit_hz']
    for uid in case['recording_ids']:
        sources = data[uid]['source']
        waves = {voice: base.filtered_wave(sources[voice]['wave'], voice, cfg) for voice in case['voices']}
        order = cfg['order'][uid[0]]
        for token in sorted(saved['tokens'][uid], key=lambda item: item['indexes']['recording']):
            human_index = token['indexes']['recording']
            if human_index in case['exclude'].get(uid, []):
                continue
            for voice in case['voices']:
                archived = token[voice]
                index = token['indexes'][voice]
                ref = next(r for r in reference[uid]['sources'][voice] if r['index'] == index)
                interval = sources[voice]['phones'][index]
                if interval != archived['interval']:
                    raise ValueError(f'MFAの音素区間が前回と一致しません ({uid}/{voice}/{index})')
                archived_windows = {window['center']: (window, rust) for window, rust in
                                    zip(archived['windows'], ref['windows'], strict=True)}
                median_references[(uid, human_index, voice)] = ref['baseline_hz']
                for center in case['centers']:
                    before, prior_rust = archived_windows[center]
                    current = base.window(waves[voice], interval, center, order, cfg)
                    start = current['start_sample']
                    frame = waves[voice][start:start + length]
                    if start != before['start_sample'] or len(frame) != length or current['outside_phone_ms'] > 1e-9:
                        raise ValueError(f'基準窓の標本位置が一致しません ({uid}/{voice}/{index}/{center})')
                    rows.append({'utterance': uid, 'recording_phone_index': human_index, 'voice': voice,
                                 'phone_index': index, 'word': archived['word'], 'ipa': token['ipa'],
                                 'center': center, 'start_sample': start, 'interval': interval, 'order': order,
                                 **inspect_window(current, prior_rust, cfg, limit)})
                    frames.append((frame, current, prior_rust))
    return fs, rows, frames, median_references


def medians(rows, references):
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row['utterance'], row['recording_phone_index'], row['voice'])].append(row)
    records = []
    for key, group in grouped.items():
        entry = {k: group[0][k] for k in ('utterance', 'recording_phone_index', 'voice', 'word', 'ipa')}
        for name in ('fixed', 'bandwidth_limited'):
            complete = [value for row in group if (value := pair(row[name])) is not None]
            entry[name] = {'count': len(complete), 'f1_f2_hz': np.median(complete, axis=0).tolist() if complete else None}
        archived = references[key]
        expected = None if archived == [None, None] else archived
        entry['fixed_median_error_hz'] = base.max_error(entry['fixed']['f1_f2_hz'], expected)
        records.append(entry)
    return records


def diagnostic_indexes(rows, voices):
    indexes = []
    for voice in voices:
        for transition in ('replaced', 'new_missing'):
            first = next((i for i, row in enumerate(rows) if row['voice'] == voice and row['transition'] == transition), None)
            if first is not None:
                indexes.append(first)
    replaced = [i for i, row in enumerate(rows) if row['transition'] == 'replaced']
    if replaced:
        indexes.append(max(replaced, key=lambda i: abs(rows[i]['f2_shift_hz'])))
    return list(dict.fromkeys(indexes))


def near_peak(curve, grid, pole, width):
    if pole is None:
        return None
    peak = pilot.strongest_peak(curve, grid, (pole[0] - width, pole[0] + width))
    if peak is not None:
        peak['distance_to_pole_hz'] = abs(peak['frequency_hz'] - pole[0])
    return peak


def diagnostics(case, cfg, settings, fs, rows, frames, artifacts, execute):
    indexes = diagnostic_indexes(rows, case['voices'])
    grid = np.arange(0, fs / 2 + settings['spectrum_grid_hz'], settings['spectrum_grid_hz'])
    rust = pilot.fixed_spectra([frames[i][0] for i in indexes], grid, artifacts, execute,
                               orders=[rows[i]['order'] for i in indexes])
    width = case['measurement']['diagnostic_peak_half_width_hz']
    records, curves = [], []
    for i, fixed_probe in zip(indexes, rust, strict=True):
        row = rows[i]
        frame, observed, prior_rust = frames[i]
        measured, (lpc, fft) = pilot.observe({**row, 'observed': observed, 'prior_fixed': prior_rust},
                                             frame, fixed_probe, fs, grid, cfg, settings)
        _, pole_error, axis = base.compare_poles(observed, fixed_probe, cfg)
        entry = {'window_index': i, 'poles_hz_error': pole_error, 'nyquist_axis_matches': axis,
                 'lpc_envelope_db_error': measured['errors']['lpc_envelope_db'],
                 'fft_envelope_db_error': measured['errors']['fft_envelope_db']}
        for name in ('fixed', 'bandwidth_limited'):
            pole = row[name]['f2']
            entry[name] = {'lpc': near_peak(lpc, grid, pole, width), 'periodogram': near_peak(fft, grid, pole, width)}
        records.append(entry)
        curves.append({'window_index': i, 'lpc_envelope_db': lpc.tolist(), 'periodogram_db': fft.tolist()})
    (artifacts / 'diagnostic-spectra.json').write_text(json.dumps({
        'frequency_hz': grid.tolist(), 'windows': curves}, separators=(',', ':')) + '\n')
    return records


def counts(rows, tokens, voices):
    output = {}
    for voice in voices:
        selected = [row for row in rows if row['voice'] == voice]
        counts = Counter(row['transition'] for row in selected)
        for method in ('fixed', 'bandwidth_limited'):
            counts[f'{method}_complete_windows'] = sum(pair(row[method]) is not None for row in selected)
            counts[f'{method}_complete_tokens'] = sum(row[method]['count'] > 0 for row in tokens if row['voice'] == voice)
        output[voice] = {key: counts[key] for key in ('unchanged', 'replaced', 'new_missing', 'fixed_complete_windows',
            'bandwidth_limited_complete_windows', 'fixed_complete_tokens', 'bandwidth_limited_complete_tokens')}
    return output


def measure(case, cfg, settings, saved, reference, data, artifacts, execute):
    fs, rows, frames, refs = windows(case, cfg, saved, reference, data)
    tokens = medians(rows, refs)
    spectra = diagnostics(case, cfg, settings, fs, rows, frames, artifacts, execute)
    totals = counts(rows, tokens, case['voices'])
    expected = case['retained_tokens'] * len(case['voices'])
    limit = cfg['frequency_bandwidth_agreement_hz']
    new_f1 = all(row['fixed']['f1'] == row['bandwidth_limited']['f1'] for row in rows)
    changed = {voice: row['replaced'] + row['new_missing'] for voice, row in totals.items()}
    checks = {
        'registered_windows_and_tokens': len(rows) == expected * len(case['centers']) and len(tokens) == expected,
        'archived_fixed_poles_and_pairs': all(row['initial_pole_comparison']['first_different_stage'] is None for row in rows),
        'fixed_rule_and_medians': all(error is not None and error <= limit for error in
            [row['fixed_selection_error_hz'] for row in rows] + [row['fixed_median_error_hz'] for row in tokens]),
        'only_f2_changes': new_f1,
        'independent_bandwidth_limited_rule': all(row['bandwidth_limited_independent_error_hz'] is not None and
            row['bandwidth_limited_independent_error_hz'] <= limit for row in rows),
        'diagnostic_poles_and_envelopes': all(row['poles_hz_error'] is not None and row['poles_hz_error'] <= limit and
            row['lpc_envelope_db_error'] <= settings['lpc_envelope_tolerance_db'] and
            row['fft_envelope_db_error'] <= settings['periodogram_direct_dft_tolerance_db'] for row in spectra),
    }
    predictions = {'no_added_coverage': new_f1 and all(r['bandwidth_limited_complete_windows'] <= r['fixed_complete_windows']
                                                        for r in totals.values()),
                   'at_least_one_new_missing': any(r['new_missing'] for r in totals.values()),
                   'recording_more_affected': changed['recording'] > max(changed['upstream'], changed['candidate'])}
    return {'checks': checks, 'hypotheses': predictions, 'counts': totals, 'diagnostics': spectra,
            'nyquist_axis_match_count': sum(len(r['initial_pole_comparison']['nyquist_axis_matches']) for r in rows),
            'tokens': tokens, 'windows': rows, 'scipy': pilot.scipy.__version__}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = base.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise ValueError('上流の作業ツリーが登録済みの固定版と一致しません')
    baseline, exploration = (base.open_run(case[key], revision) for key in ('baseline', 'pilot'))
    prior_case, prior_path = saved_case(baseline, base.CASE)
    pilot_case, pilot_path = saved_case(exploration, pilot.CASE)
    cfg, settings = prior_case['measurement'], pilot_case['measurement']
    limit_key = 'candidate_f2_bandwidth_limit_hz'
    if (case['measurement'][limit_key] != settings[limit_key] or case['centers'] != cfg['reference_centers']
            or case['recording_ids'] != prior_case['recording_ids']
            or case['exclude'] != {pilot_case['utterance']: sorted(t['phone_index'] for t in pilot_case['tokens'])}):
        raise ValueError('登録した条件が先行ケースと一致しません')
    alignment, render = (base.open_run(prior_case[key], revision) for key in ('alignment', 'render'))
    data = base.load_inputs(prior_case, alignment, render)
    saved = base.verified_path(baseline, 'summary.json')
    fixed = base.verified_path(baseline, 'artifacts/upstream-formants.json')
    sources = [CASE, Path(__file__).resolve(), pilot.PROBE, Path(pilot.__file__), Path(base.__file__),
               prior_path, pilot_path, saved, fixed, UPSTREAM / base.TSP_SOURCE,
               UPSTREAM / 'crates/chimera/src/analysis/lpc.rs', UPSTREAM / 'crates/chimera/tests/golden_analysis.rs',
               UPSTREAM / 'Cargo.lock', WORKSPACE / 'tools/measure_uniform_tube.py',
               WORKSPACE / 'tools/measure_fan_crossing_allocations.py', WORKSPACE / 'tools/upstream_baseline.py']
    sources.extend(run[0] / 'manifest.json' for run in (baseline, exploration, alignment, render))
    sources.extend(base.verified_path(run, 'summary.json') for run in (exploration, alignment, render))
    sources.extend(voice['wave'] for row in data.values() for voice in row['source'].values())
    return record_measurement(args.run_id, CASE, sources, {
        'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
        'reference_run': baseline[0].name, 'pilot_run': exploration[0].name,
    }, lambda artifacts, execute: measure(case, cfg, settings, base.read(saved), base.read(fixed), data, artifacts, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
