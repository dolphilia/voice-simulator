"""確認用07を英語発話画面で読み込み、保存ケースのCLI再演へ照合する。"""

import argparse
from copy import deepcopy
import gzip
import hashlib
from pathlib import Path
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

from measure_csd_envelope_timing import verified_file
from measure_speech_timing import compare, read
from measure_tsp_fine_gain import render_cli
from measure_tsp_fine_tip import read_series
from measure_tsp_fine_variation import signal_difference
from measure_tsp_listening import hydrate_run, snapshot_case
from measure_uniform_tube import candidate_sources, record_measurement
from measure_wasm_fixed import WASM, compare_pcm
from measure_worklet_english import DICT, UPPER_DICT
from measure_worklet_fixed import CAPTURE, ROOT, WEB, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/worklet-tsp-source-defaults.json'
STATE_NAMES = {'gate': 'gate', 'glottal_f0_hz': 'f0_hz', 'glottal_phase': 'phase',
               'glottal_area_cm2': 'glottal_area_cm2', 'glottal_flow_cm3_s': 'glottal_flow_cm3_s',
               'radiation_derivative_cm3_s2': 'radiation_derivative_cm3_s2'}


def observations(limits, report, paths):
    frames = limits['output_frames']
    stride = limits['observation_stride_frames']
    points = np.minimum(np.arange(stride, frames + stride, stride), frames) - 1
    columns = report['columns']
    rows = np.asarray(report['observations'], dtype='f8')
    if (columns[:2] != ['context_frame', 'frames_rendered'] or any(key not in columns for key in STATE_NAMES)
            or rows.shape != (len(points), len(columns)) or not np.isfinite(rows).all()):
        raise ValueError('ブラウザの観測列、件数、有限性を確認できません')
    clock_matches = np.array_equal(rows[:, 0], points) and np.array_equal(rows[:, 1], points + 1)
    selected = points < limits['traced_output_frames']
    factor = limits['internal_rate_hz'] // limits['output_rate_hz']
    internal_points = (points[selected] + 1) * factor - 1
    count = limits['traced_output_frames'] * factor
    references = {'candidate': read_series(paths['source.f64le'], count),
                  'upstream': read_series(paths['upstream-source.f64le'], count)}
    sampled = {name: rows[selected, columns.index(name)] for name in STATE_NAMES}
    differences = {label: {key: signal_difference(data[native][internal_points], sampled[key])
                           for key, native in STATE_NAMES.items()} for label, data in references.items()}
    for result in differences.values():
        for difference in result.values():
            first = difference['first_unequal_sample']
            difference['first_unequal_output_frame'] = int(points[selected][first]) if first is not None else None
    phase_before = sampled['glottal_phase']
    wrapped = np.r_[False, np.diff(phase_before) < 0]
    wrap_points = points[selected][wrapped]
    reference_wraps = np.loadtxt(paths['cycle-boundaries.csv'], delimiter=',', skiprows=1, usecols=0, dtype=int)
    counts = np.searchsorted(reference_wraps, internal_points, side='right')
    expected_wrap_points = points[selected][np.r_[False, np.diff(counts) != 0]]
    return {
        'checks': {
            'observation_clock': clock_matches,
            'sampled_source_and_radiation': all(value['peak_error'] <= limits['state_absolute_tolerance'][key]
                for fields in differences.values() for key, value in fields.items()),
            'cycle_boundaries': len(wrap_points) > 0 and np.array_equal(wrap_points, expected_wrap_points),
        },
        'observation_points': len(points), 'comparison_points': int(selected.sum()),
        'matched_wraps': len(wrap_points),
        'first_observed_wrap_output_frame': int(wrap_points[0]) if len(wrap_points) else None,
        'state_differences': differences,
    }


def measure(study, paths, out, execute, bun):
    limits = study['measurement']
    source = paths['source-defaults-case.json']
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=out / 'browser-build.log')
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'english', '--test',
             'golden_phonetics_text', '--test', 'engine'], cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'vocal-wasm', '--lib'],
            stdout=out / 'wasm-tests.log')
    binary = out / 'vocal_wasm.wasm'
    shutil.copyfile(WORKSPACE / WASM, binary)
    execute(['node', str(CAPTURE), str(out), str(CASE), str(source)])
    web = read(out / 'browser-run.json')
    report = read(out / 'browser.json')
    observed_case = out / 'browser-case.json'
    (rate_cli, cli), plan = render_cli('browser-replay', observed_case, out, execute)
    rate, pcm = wavfile.read(out / 'browser.wav')
    rate_ref, reference = wavfile.read(paths['source-defaults.wav'])
    upstream = np.fromfile(paths['upstream.f32le'], dtype='<f4')
    frames = limits['output_frames']
    if any(wave.dtype != np.float32 or wave.shape != (frames,) or not np.isfinite(wave).all()
           for wave in (pcm, cli, reference, upstream)):
        raise ValueError('PCMの形式、長さ、有限性を確認できません')
    phonetics = ('speech', 'gestures')
    baseline_plan = read(paths['source-defaults-plan.json'])
    plan_checks = {label: {key: compare(candidate[key], baseline_plan[key], limits['plan_numeric_tolerance'])
                           for key in phonetics} for label, candidate in (('browser', report), ('cli', plan))}
    archived_settings = read(source)['speech_voice']
    expected = deepcopy(archived_settings)
    expected['input'].setdefault('start_seconds', 0.05)
    waves = {'replay': compare_pcm(pcm, cli, 0), 'recorded_cli': compare_pcm(pcm, reference, 0),
             'upstream': compare_pcm(pcm, upstream, limits['upper_pcm_absolute_tolerance'])}
    trace = observations(limits, report, paths)
    quantum = limits['expected_render_quantum_frames']
    dictionary = sha256(DICT)
    response = dictionary if web['dictionaryResponseIsGzip'] else hashlib.sha256(gzip.decompress(DICT.read_bytes())).hexdigest()
    a, b = limits['attention_frames']
    return {
        **trace,
        'checks': {
            **trace['checks'],
            'actual_browser_assets': not web['errors'] and web['servedWasmSha256'] == sha256(binary)
            and dictionary == sha256(UPPER_DICT) and web['dictionaryResponseSha256'] == response,
            'settings_match': read(observed_case)['speech_voice'] == expected
            and report['caseId'] == study['recording_id'] == archived_settings['input']['id']
            and report['input'] == archived_settings['input']['text'],
            'phonetics_match': all(delta is None for group in plan_checks.values() for delta, _ in group.values()),
            'rate_and_length': (rate == rate_cli == rate_ref == report['sampleRate'] == report['workletSampleRate']
                                == limits['output_rate_hz'] and report['outputChannels'] == 1
                                and report['outputFrames'] == report['framesRendered'] == plan['output_frames'] == frames
                                and plan['decimation_factor'] * rate == limits['internal_rate_hz']),
            'render_clock': (report['shortestQuantum'] == report['longestQuantum'] == quantum
                             and report['firstContextFrame'] == report['discontinuities'] == 0
                             and report['callbacks'] == (frames + quantum - 1) // quantum),
            'native_pcm_match': all(waves[key]['first_bit_difference_frame'] is None for key in ('replay', 'recorded_cli')),
            'upstream_pcm_tolerance': waves['upstream']['first_frame_over_tolerance'] is None,
        },
        'frames': frames, 'browser': web, 'pcm': waves, 'plan': plan_checks,
        'upstream_attention_pcm': compare_pcm(pcm[a:b], upstream[a:b], limits['upper_pcm_absolute_tolerance']),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    study = read(CASE)
    rev = study['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != rev
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM)):
        parser.error('差分のない固定上流版が必要です')
    base = hydrate_run(study['candidate_run'], study['candidate_case'], rev)
    upper = hydrate_run(study['upstream_run'], study['upstream_case'], rev)
    source_cases = [snapshot_case(run, study[key]) for run, key in ((base, 'candidate_case'), (upper, 'upstream_case'))]
    limits = study['measurement']
    for path in source_cases:
        source = read(path)
        if (source['recording_id'] != study['recording_id'] or source['frames'] != limits['output_frames']
                or source['sample_rate_hz'] != limits['output_rate_hz']
                or source['internal_sample_rate_hz'] != limits['internal_rate_hz']
                or source['trace_frames'] != limits['traced_output_frames']):
            parser.error('保存済みの参照が登録条件と一致しません')
    paths = {name: verified_file(*base, f'artifacts/{name}') for name in (
        'source-defaults-case.json', 'source-defaults-plan.json', 'source-defaults.wav',
        'source.f64le', 'cycle-boundaries.csv')}
    paths.update({name: verified_file(*upper, f'artifacts/{name}') for name in ('upstream.f32le', 'upstream-source.f64le')})
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    inputs = [CASE, Path(__file__).resolve(), DICT, UPPER_DICT, *source_cases, *paths.values(),
              base[0] / 'manifest.json', upper[0] / 'manifest.json', *candidate_sources(), *web_sources(),
              *(WORKSPACE / 'tools' / name for name in ('measure_uniform_tube.py', 'measure_wasm_fixed.py',
                'measure_tsp_listening.py', 'measure_speech_timing.py', 'measure_tsp_fine_tip.py',
                'measure_tsp_fine_gain.py', 'measure_tsp_fine_variation.py', 'measure_worklet_fixed.py',
                'measure_worklet_english.py', 'measure_csd_envelope_timing.py', 'upstream_baseline.py'))]
    metadata = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': rev,
                'invoked_from': str(Path.cwd()), 'node': subprocess.check_output(['node', '-v'], text=True).strip(),
                'bun': subprocess.check_output([*bun, '--version'], text=True).strip()}
    return record_measurement(args.run_id, CASE, inputs, metadata, lambda out, execute: measure(study, paths, out, execute, bun),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
