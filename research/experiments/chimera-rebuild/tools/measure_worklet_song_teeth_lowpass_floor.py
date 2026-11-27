"""短音の歌唱で歯の低域通過周波数をWorkletと保存済みCLIで照合する。"""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
from scipy.io import wavfile

import measure_worklet_song as worklet
from upstream_baseline import sha256


CASE = worklet.WORKSPACE / 'cases/worklet-song-fast-teeth-lowpass-floor.json'
NATIVE = ('settings.json', 'voicing.csv', 'pcm-128.wav', 'pcm-128.csv', 'pcm-77.wav', 'pcm-77.csv')
UPPER = ('upstream-voicing.csv', 'upstream-pcm.f32', 'upstream-plan.json')


def audio(files, name):
    return wavfile.read(files[name])[1]


def references(local, upper):
    return (worklet.wasm.read_json(local['settings.json']), local['voicing.csv'],
            [(local[f'pcm-{n}.wav'], local[f'pcm-{n}.csv']) for n in (128, 77)],
            *(upper[name] for name in UPPER))


def independent_notes(source, observed, rate, tolerance):
    beat_seconds = 60 / source['bpm']
    starts = source['start_seconds'] + np.cumsum([0.0, *(note['beats'] for note in source['notes'][:-1])]) * beat_seconds
    planned = observed['song']['plan']['notes']
    planned_frames = [round(note['beat_seconds'] * rate) for note in planned]
    frames = np.rint(starts * rate).astype(int).tolist()
    expected_pitch = [440.0 * 2.0**((note['midi'] - 69) / 12) for note in source['notes']]
    planned_pitch = [note['f0_hz'] for note in planned]
    maximum = max(abs(a - b) for a, b in zip(expected_pitch, planned_pitch, strict=True))
    return {'passed': planned_frames == frames and maximum <= tolerance, 'beat_frames': frames,
            'f0_hz': expected_pitch, 'maximum_pitch_error_hz': maximum}


def measure(study, capture, capture_path, source, base, zero, reference, changed, artifacts, execute, bun):
    execute([*bun, 'run', 'build'], cwd=worklet.WEB, stdout=artifacts / 'browser-build.log')
    binary = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(worklet.WORKSPACE / worklet.wasm.WASM, binary)

    checks, reports, predictions = {}, {}, {}
    changes = {'worklet': {}, 'cli': {}}
    signals = {}
    zero_pcm = audio(zero, 'pcm-128.wav')
    limits = capture['measurement']
    floor = study['pcm_difference_floor']
    old_source = worklet.wasm.read_json(source)['song_voice']
    low, high = study['teeth_lowpass_floors_hz']
    for label, hz, native, upstream in (('zero_scale', None, zero, zero), ('floor0', low, reference, reference),
                                        ('floor1200', high, changed, reference)):
        folder = artifacts / label
        folder.mkdir()
        if hz is None:
            case_path = source
            turbulence = old_source['turbulence']
        else:
            turbulence = {**study['turbulence'], 'teeth_lowpass_floor_hz': hz}
            case_path = folder / 'input.json'
            case_path.write_text(json.dumps({**base, 'song_voice': {**old_source, 'turbulence': turbulence}},
                                            ensure_ascii=False, indent=2) + '\n')
        execute(['node', str(worklet.CAPTURE), str(folder), str(capture_path), str(case_path)])
        result = worklet.compare_capture(case_path, capture, folder, execute, False, None, None,
                                         binary=binary, references=references(native, upstream))
        observed = worklet.wasm.read_json(folder / 'browser.json')
        exported = worklet.wasm.read_json(folder / 'browser-case.json')['song_voice']
        notes = independent_notes(old_source['score'], observed, limits['output_rate_hz'], limits['score_numeric_tolerance'])
        result['checks']['independent_beats_and_midi_pitch'] = notes['passed']
        result['checks']['replay_settings'] = all(exported.get(key) == value for key, value in {
            'turbulence': turbulence, 'voice': old_source['voice'],
            'internal_sample_rate_hz': old_source['internal_sample_rate_hz'],
        }.items())
        pcm = wavfile.read(folder / 'browser.wav')[1]
        if label == 'zero_scale':
            baseline = audio(zero, 'browser.wav')
            result['checks']['archived_worklet_waveform'] = np.array_equal(pcm.view('u4'), baseline.view('u4'))
        else:
            signals[label] = pcm
            for engine, signal in (('worklet', pcm), ('cli', audio(native, 'pcm-128.wav'))):
                changes[engine][label] = worklet.wasm.compare_pcm(signal, zero_pcm, floor)
        local_checks = result['checks'].copy()
        if label == 'floor1200':
            # 下限を追加したときの上流との差は効果として記録する。
            del local_checks['upstream_pcm'], local_checks['upstream_observed_state']
        checks.update({f'{label}/{key}': value for key, value in local_checks.items()})
        reports[label] = {'acquisition': result, 'independent_notes': notes, 'exported_turbulence': exported['turbulence']}

    original, modified = (signals[key] for key in ('floor0', 'floor1200'))
    first = worklet.wasm.compare_pcm(modified, original, floor)
    expected = study['expected_first_pcm_change_frames']
    for engine, rows in changes.items():
        predictions[f'{engine}/same_first_pcm_change_as_registered'] = all(
            rows[key]['first_bit_difference_frame'] == frame for key, frame in expected.items())
    before, reopen = study['windows']['before_reopening']
    end = study['windows']['first_opening'][1]
    predictions['same_closed_window_pcm'] = all(np.array_equal(signal[before:reopen].view('u4'),
                                                              zero_pcm[before:reopen].view('u4'))
                                                for signal in (original, modified))
    predictions['floor_changes_pcm_during_first_opening'] = (first['first_bit_difference_frame'] is not None
                                                             and reopen <= first['first_bit_difference_frame'] < end)
    return {'checks': checks, 'predictions': predictions, 'comparisons': reports,
            'each_against_zero_scale': changes, 'worklet_floor1200_against_floor0': first}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    read = worklet.wasm.read_json
    study = read(CASE)
    capture_path, source, cli_study = (CASE.parent / study[key] for key in ('capture_case', 'source_case', 'cli_study'))
    capture, base, cli = (read(path) for path in (capture_path, source, cli_study))
    revision = study['upstream_revision']
    if (any(data['upstream_revision'] != revision for data in (capture, base, cli))
            or capture['song_voice_case'] != source.name or study['teeth_lowpass_floors_hz'] != [0, 1200]
            or subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=worklet.UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=worklet.UPSTREAM, text=True)):
        parser.error('変更のない固定上流と登録済みの短音の歌唱条件が必要です')
    zero = worklet.run_manifest(study['zero_reference_run'], capture['id'], revision)
    reference = worklet.run_manifest(study['reference_run'], 'song-voice-fast-constriction-source', revision)
    changed = worklet.run_manifest(study['floor_run'], cli['id'], revision)
    if (any(run[1]['status'] != 'pass' for run in (zero, reference, changed)) or zero[1]['turbulence_scale'] != 0
            or not any(row['path'].endswith('/' + source.name) and row['sha256'] == sha256(source)
                       for row in zero[1]['inputs'])):
        parser.error('保存済みの比較条件と判定が揃いません')
    baseline_case = worklet.verified_path(reference, 'artifacts/case.json')
    floor_case = worklet.verified_path(changed, 'artifacts/case.json')
    for path, turbulence in ((baseline_case, study['turbulence']), (floor_case, cli['turbulence'])):
        if read(path) != {**base, 'song_voice': {**base['song_voice'], 'turbulence': turbulence}}:
            parser.error(f'{path} は登録した短音の条件に対応していません')
    if cli['turbulence'] != {**study['turbulence'], 'teeth_lowpass_floor_hz': 1200}:
        parser.error('保存済みCLIと下限ありの条件が一致しません')
    file_sets = [{name: worklet.verified_path(run, f'artifacts/{name}') for name in names}
                 for run, names in ((zero, (*NATIVE, *UPPER, 'browser.wav')),
                                    (reference, (*NATIVE, *UPPER)), (changed, NATIVE))]
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    metadata = {'case_id': study['id'], 'upstream_revision': revision, 'turbulence_seed': study['noise_seed'],
                'analysis_directory': str(Path.cwd()), 'analysis_command': [sys.executable, *sys.argv],
                'node': subprocess.check_output(['node', '--version'], text=True).strip(),
                'bun': subprocess.check_output([*bun, '--version'], text=True).strip()}
    inputs = [CASE, capture_path, source, cli_study, baseline_case, floor_case, Path(__file__).resolve(),
              *(run[0] / 'manifest.json' for run in (zero, reference, changed)),
              *(path for files in file_sets for path in files.values()), *worklet.web_sources(),
              *worklet.shared.candidate_sources(), *(Path(module.__file__) for module in (
                  worklet, worklet.shared, worklet.wasm, worklet.song, worklet.voice, worklet.vowel, worklet.timing))]
    return worklet.shared.record_measurement(args.run_id, CASE, inputs, metadata,
        lambda artifacts, execute: measure(study, capture, capture_path, source, base, *file_sets, artifacts, execute, bun),
        command=None, input_root=worklet.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
