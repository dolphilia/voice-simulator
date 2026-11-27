"""TSPの同じ本文で、MFAの語間と口腔断面・放射を同じフレーム軸へ置く。"""

import argparse
import gzip
import json
from pathlib import Path
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/tsp-coat-to-closure.json'
PROBE = WORKSPACE / 'tools/upstream_tsp_closure_probe.rs'
DICT = UPSTREAM / 'public/data/cmudict.txt.gz'
VOICES = ('upstream', 'candidate')


def read(path):
    return json.loads(path.read_text())


def gap(path, words, rate):
    tiers = read(path)['tiers']
    tokens = [(a, b, label) for a, b, label in tiers['words']['entries'] if label not in ('', 'sil', 'sp', '<eps>')]
    (left, right), = [(a, b) for a, b in zip(tokens, tokens[1:]) if [a[2], b[2]] == words]
    return [round(t * rate) for t in (left[1], right[0])]


def runs(mask, offset):
    changes = np.flatnonzero(np.diff(np.r_[False, mask, False])) + offset
    return changes.reshape(-1, 2).tolist()


def overlap(spans, bounds):
    a, b = bounds
    return sum(max(0, min(right, b) - max(left, a)) for left, right in spans)


def plan_comparison(case, candidate, upper):
    speech = case['speech']
    tol = case['measurement']['plan_tolerance_seconds']
    phrase, = candidate['speech']['phrases']
    timings = phrase['timing']['segments']
    native = [[p['start_seconds'], p['end_seconds']] for p in timings]
    expected = []
    selected = []
    for index, delay in zip(speech['planned_stop_input_indexes'], speech['closure_delay_seconds'], strict=True):
        (position, row), = [(i, p) for i, p in enumerate(timings) if p['input_index'] == index]
        if row['segment']['ipa'] != 't' or timings[position - 1]['input_index'] != index - 1:
            raise ValueError('登録した連続する /t/ の計画が見つかりません')
        a, b = native[position]
        placed = a + min(delay, max(0, b - a - speech['minimum_stop_seconds']))
        expected.append([placed - speech['closure_lead_seconds'],
                         max(placed + speech['minimum_hold_seconds'], b - speech['release_lead_seconds'])])
        selected.append([a, b])
    # 各 /t/ の主ジェスチャーを選び、弱い舌体ジェスチャーと区別する。
    low, high = selected[0][0] - .06, selected[-1][1]
    def main_gestures(plan):
        return [[g['t0'], g['t1']] for g in plan['gestures']
                if g['label'] == 't' and low <= g['t0'] < high and g['strength'] == 40]

    candidate_gestures, upper_gestures = map(main_gestures, (candidate, upper))
    equal_plans = ([p['segment']['ipa'] for p in timings] == [p['ipa'] for p in upper['segments']]
                   and np.allclose(native, [[p['t0'], p['t1']] for p in upper['segments']], rtol=0, atol=tol))
    checked = all(len(rows) == len(expected) and np.allclose(rows, expected, rtol=0, atol=tol)
                  for rows in (candidate_gestures, upper_gestures))
    vowel = [p for p in timings if p['input_index'] == speech['previous_vowel_input_index']]
    a, b = case['measurement']['preceding_vowel_reference_frames']
    rate = case['measurement']['output_rate_hz']
    return {
        'same_ipa_and_times': bool(equal_plans),
        'closure_gesture_equation': bool(checked),
        'reference_within_preceding_vowel': vowel[0]['start_seconds'] <= a / rate < b / rate <= vowel[-1]['end_seconds'],
        'planned_stop_seconds': selected,
        'predicted_gesture_seconds': expected,
        'upstream_gesture_seconds': upper_gestures,
        'candidate_gesture_seconds': candidate_gestures,
        'predicted_gesture_overlap_ms': 1000 * max(0, min(x[1] for x in expected) - max(x[0] for x in expected)),
    }


def analyze(state, pcm, bounds, limits):
    first, last = limits['frame_range']
    selected = state[first:last]
    area = selected['oral_minimum_cm2']
    li = slice(bounds[0] - first, bounds[1] - first)
    if not (first <= bounds[0] < bounds[1] <= last and last < len(pcm)):
        raise ValueError('登録した語間を計測範囲で採取できません')
    length = bounds[1] - bounds[0]
    area_results = {}
    area_agreement = True
    for threshold in limits['area_thresholds_cm2']:
        mask = area <= threshold
        spans = runs(mask, first)
        count = np.count_nonzero(mask[li])
        area_agreement &= overlap(spans, bounds) == count
        cells, counts = np.unique(selected['oral_minimum_cell'][li][mask[li]].astype(int), return_counts=True)
        area_results[str(threshold)] = {
            'spans_in_observation_frames': spans,
            'gap_overlap_frames': int(count), 'gap_overlap_fraction': count / length,
            'gap_overlap_cells': {int(cell): int(n) for cell, n in zip(cells, counts, strict=True)},
        }
    power = pcm.astype(float) ** 2
    a, b = limits['preceding_vowel_reference_frames']
    reference = float(np.mean(power[a:b]))
    width, hop = (limits[k] for k in ('window_frames', 'hop_frames'))
    centers = np.arange(first, last, hop)
    starts = centers - width // 2
    # 閉鎖中の微小な電力を、発話先頭からの累積和の差で求めると桁落ちする。
    measured = np.lib.stride_tricks.sliding_window_view(power, width)[starts].mean(axis=1)
    independently = np.convolve(power, np.ones(width) / width, mode='valid')[starts]
    floor = np.finfo(float).tiny
    db = 10 * np.log10(np.maximum(measured, floor) / reference)
    independent_db = 10 * np.log10(np.maximum(independently, floor) / reference)
    power_error = float(np.max(np.abs(db - independent_db)))
    low = db <= limits['low_energy_db']
    # 中心が hop 間隔の窓の判定を、中心の左右半hopへ割り当てる。
    start = first - hop // 2
    low_spans = [[start + a * hop, start + b * hop] for a, b in runs(low, 0)]
    low_count = overlap(low_spans, bounds)
    independent_low = int(np.count_nonzero(np.repeat(independent_db <= limits['low_energy_db'], hop)
                                           [bounds[0] - start:bounds[1] - start]))
    gap_area = area[li]
    index = int(np.argmin(gap_area)) + bounds[0]
    result = {
        'mfa_gap_frames': bounds,
        'area': area_results,
        'minimum_gap_area_cm2': float(state['oral_minimum_cm2'][index]),
        'minimum_gap_area_frame': index,
        'minimum_gap_lip_area_cm2': float(selected['lip_minimum_cm2'][li].min()),
        'max_abs_radiation_derivative_in_gap_cm3_s2':
            float(np.max(np.abs(selected['radiation_derivative_cm3_s2'][li]))),
        'low_pcm_spans_frames': low_spans,
        'low_pcm_gap_overlap_frames': low_count,
        'low_pcm_gap_overlap_fraction': low_count / length,
        'pcm_reference_power': reference,
        'max_power_crosscheck_db': power_error,
        'overlap_crosscheck': bool(area_agreement and low_count == independent_low),
    }
    return result, (centers, db)


def plot(path, case, states, levels, results, plan):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import fontManager

    font = Path('/Library/Fonts/Arial Unicode.ttf')
    if font.is_file():
        fontManager.addfont(font)
        plt.rcParams['font.family'] = ['Arial Unicode MS', 'DejaVu Sans']
    limits = case['measurement']
    rate = limits['output_rate_hz']
    first, last = limits['frame_range']
    fig, axes = plt.subplots(3, 2, figsize=(11, 6.4), sharex=True, sharey='row', layout='constrained')
    threshold = limits['primary_area_threshold_cm2']
    for col, (tag, title) in enumerate(zip(VOICES, ('固定上流', '再実装'), strict=True)):
        area_ax, pcm_ax, rad_ax = axes[:, col]
        lo, hi = results[tag]['mfa_gap_frames']
        for ax in axes[:, col]:
            ax.axvspan(1000 * lo / rate, 1000 * hi / rate, color='#dadde8', label='MFAの語間')
            for left, right in plan['planned_stop_seconds']:
                ax.axvline(1000 * left, color='#7c496a', linestyle=':', lw=1)
                ax.axvline(1000 * right, color='#7c496a', linestyle=':', lw=1)
            ax.grid(axis='y', alpha=.18)
        area_ax.set_title(title, loc='left')
        trace = states[tag][first:last]
        x = 1000 * trace['frame'] / rate
        area_ax.plot(x, trace['oral_minimum_cm2'], color='#086f83', lw=1)
        area_ax.axhline(threshold, color='#086f83', linestyle='--', lw=.8)
        area_ax.set_yscale('symlog', linthresh=.0002)
        pcm_ax.plot(1000 * levels[tag][0] / rate, levels[tag][1], color='#ad5020', lw=1)
        pcm_ax.axhline(limits['low_energy_db'], color='#ad5020', linestyle='--', lw=.8)
        rad_ax.plot(x, trace['radiation_derivative_cm3_s2'], color='#4e5389', lw=.7)
        rad_ax.set_xlabel('発話ファイル先頭からの時刻 (ms)')
        area_ax.legend(loc='upper right', frameon=False, fontsize=9)
    for ax, label in zip(axes[:, 0], ('口腔の最小断面 (cm²)', '清浄PCMの相対電力 (dB)', '放射流量の時間差分 (cm³/s²)'), strict=True):
        ax.set_ylabel(label)
    axes[2, 0].set_xlim(1000 * first / rate, 1000 * last / rate)
    fig.suptitle('FK61_02   coat to  /t t/')
    fig.savefig(path, dpi=155)
    plt.close(fig)


def render_and_trace(source, out, execute, *, body, host_block, probe_flags=(), extra_tests=()):
    path = source / 'candidate.json'
    vocal = WORKSPACE / 'target/release/vocal-cli'
    chimera = UPSTREAM / 'target/release/chimera'
    execute(['cargo', 'build', '--locked', '--offline', '--release', '-p', 'vocal-cli'])
    execute(['cargo', 'build', '--locked', '--offline', '--release', '-p', 'chimera-cli'], cwd=UPSTREAM)
    setup = out / 'candidate-plan.json'
    execute([str(vocal), 'inspect', str(path)], stdout=setup)
    state = out / 'candidate-state.csv'
    execute([str(vocal), 'render', str(path), str(state)])
    execute([str(vocal), 'render-pcm', str(path), str(out / 'candidate.wav'), str(out / 'candidate-pcm.csv'),
             str(host_block)])
    text = read(path)['speech_voice']['input']['text']
    execute([str(chimera), 'render', 'text', str(out / 'upstream'), text, body, '--float'], cwd=UPSTREAM)
    tests = [flag for name in ('stop_spans', 'engine', *extra_tests) for flag in ('--test', name)]
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', *tests],
            cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    probe = shared.build_upstream_probe(PROBE, out, execute, extra_libraries=('serde_json',))
    dictionary = out.parent / 'tmp' / 'cmudict.tsv'
    dictionary.write_bytes(gzip.decompress(DICT.read_bytes()))
    execute([str(probe), str(path), str(dictionary), str(out / 'upstream-state.csv'),
             str(out / 'upstream.f32'), str(out / 'upstream-plan.json'), *probe_flags])


def measurement(case, source, aligned, out, execute):
    spec, limits = case['speech'], case['measurement']
    render_and_trace(source, out, execute, body=spec['body'], host_block=spec['candidate_host_block'])
    candidate_plan, upper_plan = map(read, (out / 'candidate-plan.json', out / 'upstream-plan.json'))
    plan = plan_comparison(case, candidate_plan, upper_plan)
    rate = limits['output_rate_hz']
    states, levels, results, pcm = {}, {}, {}, {}
    input_match = {}
    for tag in VOICES:
        sample_rate, pcm[tag] = wavfile.read(out / f'{tag}.wav')
        if sample_rate != rate or pcm[tag].dtype != np.float32 or not np.isfinite(pcm[tag]).all():
            raise ValueError(f'清浄PCMの形式または範囲が不正です ({tag})')
        input_match[tag] = sha256(out / f'{tag}.wav') == sha256(source / f'{tag}.wav')
        trace = out / f'{tag}-state.csv'
        wanted = case['retain_csv']['candidate-state.csv']['columns']
        with trace.open() as stream:
            fields = stream.readline().strip().split(',')
        states[tag] = np.loadtxt(trace, delimiter=',', skiprows=1, usecols=[fields.index(k) for k in wanted],
                                 dtype=[(k, 'f8') for k in wanted])
        if not np.array_equal(states[tag]['frame'], np.arange(len(pcm[tag]))) or any(
                not np.isfinite(states[tag][name]).all() for name in wanted):
            raise ValueError(f'状態の時刻または値が不正です ({tag})')
        bounds = gap(aligned[tag], case['words'], rate)
        results[tag], levels[tag] = analyze(states[tag], pcm[tag], bounds, limits)
    plot(out / 'coat-to.png', case, states, levels, results, plan)
    primary = str(limits['primary_area_threshold_cm2'])
    count = len(pcm['candidate'])
    previous = np.fromfile(out / 'upstream.f32', dtype='<f4')
    first_diff = np.flatnonzero(pcm['candidate'].view('u4') != pcm['upstream'].view('u4'))
    return {
        'checks': {
            'clean_pcm_from_both_clis': all(input_match.values()),
            'upstream_probe_pcm': np.array_equal(previous.view('u4'), pcm['upstream'].view('u4')),
            'complete_frame_clock': len(pcm['upstream']) == candidate_plan['output_frames'] == upper_plan['output_frames'] == count
                                    and candidate_plan['decimation_factor'] * rate == limits['internal_rate_hz'],
            'mfa_gap': all(row['mfa_gap_frames'] == limits['expected_mfa_gap_frames'] for row in results.values()),
            'plan_and_independent_stop_equations': all(plan[k] for k in ('same_ipa_and_times', 'closure_gesture_equation',
                                                                        'reference_within_preceding_vowel')),
            'independent_overlap_and_power': all(row['overlap_crosscheck']
                                                  and row['max_power_crosscheck_db'] <= limits['power_tolerance_db'] for row in results.values()),
            'majority_of_mfa_gap_has_narrow_area': all(row['area'][primary]['gap_overlap_fraction'] >= limits['minimum_gap_overlap_fraction']
                                                       for row in results.values()),
            'majority_of_mfa_gap_is_low_energy': all(row['low_pcm_gap_overlap_fraction'] >= limits['minimum_low_energy_overlap_fraction']
                                                     for row in results.values()),
        },
        'frames': count,
        'pcm_first_bit_difference_frame': int(first_diff[0]) if first_diff.size else None,
        'clean_wave_hash_agreement': input_match,
        'plan': plan,
        'results': results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case', type=Path, default=CASE)
    args = parser.parse_args()
    case_path = args.case.resolve()
    case = read(case_path)
    rev = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if rev != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('差分のない固定上流版を用意してください')
    uid = case['recording_id']
    reference_run = WORKSPACE / 'runs' / case['source_run']
    source = reference_run / 'artifacts' / uid
    alignment_run = WORKSPACE / 'runs' / case['alignment_run']
    aligned = {tag: alignment_run / 'artifacts/aligned-1-synth' / f'{uid}-{tag}' / f'{uid}-{tag}.json' for tag in VOICES}
    inputs = [case_path, PROBE, Path(__file__).resolve(), Path(shared.__file__), DICT, *shared.candidate_sources()]
    for run, paths in ((reference_run, [source / 'candidate.json', *(source / f'{tag}.wav' for tag in VOICES)]),
                       (alignment_run, list(aligned.values()))):
        manifest = run / 'manifest.json'
        hashes = {entry['path']: entry['sha256'] for entry in read(manifest)['outputs']}
        if any(sha256(p) != hashes.get(p.relative_to(run).as_posix()) for p in paths):
            parser.error(f'保存済み成果がマニフェストと一致しません ({run.name})')
        inputs.extend([manifest, *paths])
    return shared.record_measurement(args.run_id, case_path, inputs,
        {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': rev},
        lambda out, execute: measurement(case, source, aligned, out, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
