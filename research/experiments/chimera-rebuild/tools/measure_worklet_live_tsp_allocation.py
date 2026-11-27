"""確認用07の英語計画、開始ABI、描画量子の割り当てを照合する。"""

import argparse
import csv
import gzip
import json
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
from scipy.io import wavfile

from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_speech_timing import read
from measure_uniform_tube import candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE
from measure_worklet_fixed import ROOT


CASE = WORKSPACE / 'cases/worklet-live-tsp-allocation-44100.json'
PLANNER_CASE = WORKSPACE / 'cases/worklet-live-tsp-planner-allocation-44100.json'
PREWARM_CASE = WORKSPACE / 'cases/worklet-live-tsp-planner-prewarm-44100.json'
DIRECT_REPORT_CASE = WORKSPACE / 'cases/worklet-live-tsp-planner-direct-report-44100.json'
DIRECT_TEXT_PLAN_CASE = WORKSPACE / 'cases/worklet-live-tsp-planner-direct-text-plan-44100.json'
REPORT_BUFFER_CASE = WORKSPACE / 'cases/worklet-live-tsp-planner-report-buffer-44100.json'
TEST = 'tests::speech_allocation::english_tsp_allocation_profile'
DICTIONARY = WORKSPACE / 'data/cmudict.txt.gz'
PHASE_NAMES = ('dictionary_index', 'speech_plan', 'speech_value', 'score_words', 'report_value', 'report_json')
REFERENCE_NAMES = ('plan.json', 'planner-counts.json', 'allocations-by-quantum.csv',
                   'plain.f32le', 'plain-observations.f64le', 'plain-glottal.f64le', 'plain-tract.f64le')


def same_bits(a, b, dtype):
    return a.shape == b.shape and a.astype(dtype, copy=False).tobytes() == b.astype(dtype, copy=False).tobytes()


def compare_draw(out, spec):
    plain, traced = (read(out / f'{mode}-counts.json') for mode in ('plain', 'traced'))
    columns = traced['phase_names']
    assert plain['phase_names'] == columns and len(set(columns)) == len(columns)
    rows = []
    for start, total, trace in zip(range(0, spec['output_frames'], spec['quantum_frames']),
                                   traced['total_by_quantum'], traced['phase_counts'], strict=True):
        phases = dict(zip(columns, trace, strict=True))
        count = min(spec['output_frames'] - start, spec['quantum_frames'])
        rows.append({'output_frame': start, 'output_frames': count, 'allocations': total,
                     'outside_control': total - phases['control']['allocations'],
                     **{f'{phase}_calls': item['calls'] for phase, item in phases.items()},
                     **{f'{phase}_allocations': item['allocations'] for phase, item in phases.items()}})
    with (out / 'allocations-by-quantum.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    stride = spec['control_output_frames']
    setup = traced['setup']
    planning = read(out / 'planner-counts.json')
    checks = {
        'plain_and_traced_setup_match': plain['setup'] == setup,
        'plain_and_traced_allocations_match': plain['total_by_quantum'] == traced['total_by_quantum'],
        'plain_does_not_count_phases': all(x['calls'] == x['allocations'] == 0
                                           for row in plain['phase_counts'] for x in row),
        'counts_are_nonnegative': all(value >= 0 for row in rows for value in row.values()),
        'control_schedule_matches': all(row['control_calls'] == row['apply_calls'] == row['begin_tract_block_calls']
                                        == (row['output_frames'] + stride - 1) // stride for row in rows),
        'planner_command_and_trace_setup_allocate': planning['english_plan'] > 0
                                                     and setup['start_score_prepared'] > 0 and setup['trace_setup'] > 0,
    }
    phases = {name: {kind: sum(row[f'{name}_{kind}'] for row in rows) for kind in ('calls', 'allocations')}
              for name in columns}
    count = sum(traced['total_by_quantum'])
    result = {'planner_allocations': planning, 'setup_allocations': setup, 'render_allocations': count,
              'quanta': len(rows), 'last_quantum_frames': rows[-1]['output_frames'], 'phase_totals': phases,
              'nonzero_quanta': [{'output_frame': row['output_frame'], 'allocations': row['allocations']}
                                 for row in rows if row['allocations']],
              'predicted_zero_render_allocations': count == 0}
    return checks, result


def compare_signals(out, spec, browser, wave, upper):
    frames = spec['output_frames']
    states = np.asarray(browser['observations'], dtype='<f8')
    tract = browser['tract']
    geometry = np.asarray(tract['rows'], dtype='<f8')
    acoustics = np.asarray(tract['acoustics']['rows'], dtype='<f8')
    tract_rows = np.concatenate((geometry, acoustics[:, 1:]), axis=1)
    refs = {'observations': states[:, 1:], 'glottal': np.asarray(browser['glottal']['values'], dtype='<f8'),
            'tract': tract_rows}
    rate, recorded = wavfile.read(wave)
    pcm, traced = (np.fromfile(out / f'{mode}.f32le', dtype='<f4') for mode in ('plain', 'traced'))
    assert pcm.shape == traced.shape == recorded.shape == (frames,)
    upstream = np.fromfile(upper, dtype='<f4')
    assert upstream.shape == pcm.shape and np.isfinite(upstream).all()
    delta = np.abs(pcm.astype('f8') - upstream)
    first = int(np.flatnonzero(pcm)[0])
    plan = read(out / 'plan.json')
    checks = {
        'pcm_format_and_length': rate == spec['output_rate_hz'] and recorded.dtype == np.float32,
        'pcm_is_finite': bool(np.isfinite(pcm).all()),
        'pcm_matches_plain_and_traced': same_bits(pcm, traced, '<f4'),
        'pcm_matches_live_browser': same_bits(pcm, recorded, '<f4'),
        'pcm_matches_fixed_upstream': bool(np.max(delta) <= spec['upstream_pcm_absolute_tolerance']),
        'speech_onset_matches': first == spec['first_nonzero_frame'] and not np.any(pcm[:spec['initial_silence_frames']]),
        'speech_plan_matches': plan['plan']['speech'] == browser['speech'] and plan['gestures'] == browser['gestures'],
        'browser_tract_sample_positions_agree': np.array_equal(geometry[:, 0], acoustics[:, 0]),
    }
    observations = {}
    for name, ref in refs.items():
        a, b = (np.fromfile(out / f'{mode}-{name}.f64le', dtype='<f8') for mode in ('plain', 'traced'))
        if name == 'observations':
            a, b = a.reshape(-1, 23), b.reshape(-1, 23)
            compared = a[:, :ref.shape[1]]
            checks['observation_frames_match'] = np.array_equal(a[:, 0] - 1, states[:, 0])
        else:
            compared = a.reshape(ref.shape)
        checks[f'{name}_matches_plain_and_traced'] = same_bits(a, b, '<f8')
        checks[f'{name}_matches_live_browser'] = same_bits(compared, ref, '<f8')
        observations[name] = {'shape': list(ref.shape), 'max_abs_error': float(np.max(np.abs(compared - ref)))}
    return checks, {'first_nonzero_frame': first, 'upstream_pcm_max_abs_error': float(np.max(delta)),
                    'browser_observations': observations}


def compare_planner_phases(out, reference, unprimed=None, direct_reference=None, direct_phase='report_value'):
    report = read(out / 'planner-phases.json')
    names = report['phase_names']
    phases = {name: dict(zip(names, report[name]['phases'], strict=True)) for name in ('cold', 'repeat')}
    cold, repeat = phases['cold'], phases['repeat']
    totals = {name: report[name]['total'] for name in phases}
    direct = report['direct_dictionary']
    entries = set()
    for line in gzip.decompress(DICTIONARY.read_bytes()).decode('utf-8').split('\n'):
        word, tab, _ = line.partition('\t')
        if word and tab:
            entries.add(word)
    checks = {
        'planner_phase_names_match': tuple(names) == PHASE_NAMES,
        'planner_phases_account_for_abi': all(sum(phases[name].values()) == totals[name] for name in phases),
        'planner_phase_counts_nonnegative': all(count >= 0 for counts in phases.values() for count in counts.values()),
        'cold_planner_abi_matches_outer_count': totals['cold'] == read(out / 'planner-counts.json')['english_plan'],
        'dictionary_index_matches_direct_measurement': cold['dictionary_index'] == repeat['dictionary_index']
                                                       == direct['allocations'],
        'direct_dictionary_entry_count_matches_tsv': direct['entries'] == len(entries),
        'repeat_plan_matches_cold': (out / 'plan.json').read_bytes() == (out / 'repeat-plan.json').read_bytes(),
        'repeat_score_matches_cold': (out / 'cold-score.f64le').read_bytes() == (out / 'repeat-score.f64le').read_bytes(),
        'saved_native_artifacts_match': all((out / name).read_bytes() == saved.read_bytes()
                                            for name, saved in reference.items()),
    }
    json_steps = ('speech_value', 'report_value', 'report_json')
    json_allocations = sum(cold[name] for name in json_steps)
    predictions = {
        'json_accounts_for_majority_of_cold_allocations': 2 * json_allocations > totals['cold'],
        'repeat_only_saves_the_score_buffer': repeat == cold | {'score_words': cold['score_words'] - 1}
                                             and totals['cold'] - totals['repeat'] == 1,
    }
    result = {'planner_phase_allocations': phases, 'planner_phase_totals': totals,
              'cold_json_allocations': json_allocations, 'dictionary_index_reference': direct,
              'planner_predictions': predictions}
    if direct_reference is not None:
        previous = read(direct_reference['summary.json'])['planner_phase_allocations']
        check = {
            'report_value': 'direct_report_plan_and_score_match',
            'speech_value': 'direct_text_plan_artifacts_match',
            'report_json': 'reused_report_buffer_artifacts_match',
        }[direct_phase]
        checks[check] = all(
            (out / name).read_bytes() == saved.read_bytes()
            for name, saved in direct_reference.items() if name != 'summary.json')
        result['direct_report_reductions'] = {mode: {name: previous[mode][name] - phases[mode][name]
                                                    for name in names} for mode in phases}
        allowed_differences = ('report_value', 'report_json') if direct_phase == 'report_value' else (direct_phase,)
        result['planner_predictions'] = {
            'report_serialization_does_not_allocate_more': all(
                phases[mode]['report_json'] <= previous[mode]['report_json'] for mode in phases),
            'other_planner_phases_match': all(phases[mode][name] == previous[mode][name]
                                              for mode in phases for name in names
                                              if name not in allowed_differences),
        }
        if direct_phase == 'report_json':
            transitions = read(out / 'planner-report-transitions.json')
            checks.update(compare_report_transitions(out, names, transitions))
            result['planner_predictions'].update(
                cold_report_json_allocations_match_reference=cold['report_json'] == previous['cold']['report_json'],
                repeat_report_json_allocations_are_zero=repeat['report_json'] == 0,
                transition_report_json_allocations_are_zero=all(
                    row['phases'][names.index('report_json')] == 0
                    for row in transitions),
            )
        else:
            result['planner_predictions'][f'{direct_phase}_allocations_are_zero'] = all(
                counts[direct_phase] == 0 for counts in phases.values())
    elif unprimed is None:
        checks['cold_planner_abi_matches_saved_total'] = totals['cold'] == read(reference['planner-counts.json'])['english_plan']
    else:
        previous = read(unprimed['summary.json'])['planner_phase_allocations']
        prewarm = read(out / 'planner-prewarm.json')
        result['core_plan_prewarm'] = prewarm
        result['cold_allocation_difference_from_unprimed'] = {name: previous['cold'][name] - cold[name] for name in names}
        checks['prewarmed_plan_and_score_match_unprimed'] = all(
            (out / name).read_bytes() == unprimed[name].read_bytes() for name in ('plan.json', 'cold-score.f64le'))
        predictions['core_prewarm_accounts_for_cold_difference'] = (
            prewarm == {name: previous['cold'][name] for name in ('dictionary_index', 'speech_plan')}
            and cold == previous['repeat'] | {'score_words': previous['cold']['score_words']}
            and repeat == previous['repeat'])
    return checks, result


def compare_report_transitions(out, names, transitions):
    short, invalid, restored = transitions
    original = (out / 'plan.json').read_bytes()
    long_plan = json.loads(original)
    short_plan = json.loads(short['report'])
    original_words = (out / 'cold-score.f64le').stat().st_size // 8
    words_per_gesture = original_words // len(long_plan['gestures'])
    return {
        'report_transition_order_and_lengths_match': [short['name'], invalid['name'], restored['name']]
                                                    == ['short', 'invalid_utf8', 'restored']
        and all(row['length'] == len(row['report'].encode('utf-8')) for row in transitions)
        and 0 < invalid['length'] < short['length'] < restored['length'] == len(original),
        'short_report_contains_its_own_plan_and_score': short_plan['plan']['speech']['phrases'][0]['words'] == ['a']
        and 0 < short['score_words'] == len(short_plan['gestures']) * words_per_gesture < original_words,
        'invalid_input_replaces_report_and_clears_score': invalid['report'] == '{"error":"英語入力はUTF-8で指定してください"}'
        and invalid['score_words'] == 0,
        'original_report_and_score_are_restored': restored['report'].encode('utf-8') == original
        and restored['score_matches_original'] and restored['score_words'] == original_words,
        'transition_allocations_account_for_abi': all(
            len(row['phases']) == len(names) and sum(row['phases']) == row['total']
            for row in transitions),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    options = parser.add_mutually_exclusive_group()
    options.add_argument('--planner-phases', action='store_true', help='英語計画ABIの各工程も計数する')
    options.add_argument('--prewarm-planner', action='store_true', help='コア側の英語計画だけ先行実行して計数する')
    options.add_argument('--direct-report', action='store_true', help='報告の直接出力を基準の計画と比較する')
    options.add_argument('--direct-text-plan', action='store_true', help='英語計画の直接出力を比較する')
    options.add_argument('--reuse-report-buffer', action='store_true', help='計画JSONの出力領域の再利用を比較する')
    args = parser.parse_args()
    variant = next((path for enabled, path in (
        (args.prewarm_planner, PREWARM_CASE),
        (args.direct_report, DIRECT_REPORT_CASE),
        (args.direct_text_plan, DIRECT_TEXT_PLAN_CASE),
        (args.reuse_report_buffer, REPORT_BUFFER_CASE),
    ) if enabled), None)
    case_path = variant or (PLANNER_CASE if args.planner_phases else CASE)
    case = read(PLANNER_CASE) | read(case_path) if variant else read(case_path)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    baseline = run_manifest(case['baseline'], case['baseline_case'], revision)
    if baseline[1]['status'] != 'pass':
        parser.error('保存済みの通常Workletの比較が合格している必要があります')
    fixture, browser, wave, upper = [verified_path(baseline, f'artifacts/{name}') for name in (
        'browser-case.json', 'browser.json', 'browser.wav', 'upstream.f32le')]
    sources = [case_path, Path(__file__).resolve(), fixture, browser, wave, upper, baseline[0] / 'manifest.json',
               DICTIONARY, *candidate_sources()]
    reference = {}
    unprimed = None
    direct_reference = None
    if args.planner_phases or variant:
        saved = run_manifest(case['allocation_reference_run'], case['allocation_reference_case'], revision)
        if saved[1]['status'] != 'pass' or read(CASE)['measurement'] != case['measurement']:
            parser.error('基準の割り当て測定が合格し、計測条件が一致している必要があります')
        reference = {name: verified_path(saved, f'artifacts/{name}') for name in REFERENCE_NAMES}
        sources.extend([CASE, saved[0] / 'manifest.json', *reference.values()])
    if variant:
        previous = run_manifest(case['planner_reference_run'], case['planner_reference_case'], revision)
        if previous[1]['status'] != 'pass':
            parser.error('先行処理なしの計画工程の比較が合格している必要があります')
        names = ('plan.json', 'cold-score.f64le', 'repeat-score.f64le')
        if args.direct_text_plan or args.reuse_report_buffer:
            names += ('repeat-plan.json',) + REFERENCE_NAMES[2:]
            sources.append(DIRECT_TEXT_PLAN_CASE if args.reuse_report_buffer else DIRECT_REPORT_CASE)
        planner_reference = {name: verified_path(previous, f'artifacts/{name}') for name in names}
        planner_reference['summary.json'] = verified_path(previous, 'summary.json')
        sources.extend([PLANNER_CASE, previous[0] / 'manifest.json', *planner_reference.values()])
        if args.prewarm_planner:
            unprimed = planner_reference
        else:
            direct_reference = planner_reference
        # この比較では、計画ABIの件数そのものが観測対象になる。
        reference.pop('planner-counts.json')

    def measure(out, execute):
        shutil.copyfile(fixture, out / 'input.json')
        flags = ['CHIMERA_SPEECH_PLAN_PHASES=1'] if reference else []
        if args.prewarm_planner:
            flags.append('CHIMERA_SPEECH_PLAN_PREWARM=1')
        if args.reuse_report_buffer:
            flags.append('CHIMERA_SPEECH_REPORT_TRANSITIONS=1')
        execute(['env', f'CHIMERA_SPEECH_ALLOCATION_PROBE_OUTPUT={out}', *flags, 'cargo', 'test', '--release', '--locked',
                 '--offline', '-p', 'vocal-wasm', '--features', 'render-allocation-probe', '--lib',
                 TEST, '--', '--exact', '--nocapture'], stdout=out / 'allocation-probe.log')
        draw_checks, draw = compare_draw(out, case['measurement'])
        signal_checks, signal = compare_signals(out, case['measurement'], read(browser), wave, upper)
        phase = 'report_json' if args.reuse_report_buffer else 'speech_value' if args.direct_text_plan else 'report_value'
        planner_checks, planner = compare_planner_phases(
            out, reference, unprimed, direct_reference, phase) if reference else ({}, {})
        return draw | signal | planner | {'checks': draw_checks | signal_checks | planner_checks}

    return record_measurement(args.run_id, case_path, sources, {
        'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
        'analysis_command': [sys.executable, *sys.argv],
    }, measure, command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
