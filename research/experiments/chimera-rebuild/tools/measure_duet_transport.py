"""二声のCLI音源を作り、デュエットの再生時計を固定上流と照合する。"""

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
from scipy.io import wavfile
from scipy.signal import correlate

import measure_uniform_tube as shared
from measure_wasm_fixed import read_json
from measure_worklet_fixed import ROOT, WEB, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/duet-transport.json'
CAPTURE = WEB / 'tools/capture-duet-transport.mjs'
MODEL = WEB / 'tools/check-duet-clock.mjs'


def synthesize(spec, source, artifacts, execute):
    rate, frames = spec['sample_rate_hz'], spec['expected_frames']
    if frames != round(rate * spec['duration_seconds']):
        raise ValueError('事前登録の音源長が一致しません')
    mix = np.zeros(frames)
    stems = []
    for index, voice in enumerate(spec['voices'], 1):
        case = read_json(source)
        song = case['song_voice']
        song['body'] = voice['body']
        score = song['score']
        score['start_seconds'] = voice['start_seconds']
        for note, midi in zip(score['notes'], voice['midi'], strict=True):
            note['midi'] = midi
        settings = artifacts / f'voice-{index}.json'
        settings.write_text(json.dumps(case, ensure_ascii=False, indent=2) + '\n')
        wave = artifacts / f'voice-{index}.wav'
        execute(['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--',
                 'render-pcm', str(settings), str(wave), str(artifacts / f'voice-{index}.csv'), '128'])
        actual_rate, pcm = wavfile.read(wave)
        if actual_rate != rate or pcm.ndim != 1 or not (0 < len(pcm) <= frames and np.isfinite(pcm).all()):
            raise ValueError(f'声部{index}のPCM形式・長さが一致しません')
        mix[:len(pcm)] += voice['gain'] * pcm.astype(float)
        stems.append({'body': voice['body'], 'frames': len(pcm), 'peak': float(np.max(np.abs(pcm))),
                      'sha256': sha256(wave)})
    peak = float(np.max(np.abs(mix)))
    if not 0 < peak < 32767 / 32768:
        raise ValueError('混合音源の振幅が範囲外です')
    wave = artifacts / 'mix.wav'
    wavfile.write(wave, rate, np.rint(mix * 32768).astype('<i2'))
    return wave, {'frames': frames, 'rate_hz': rate, 'voice_stems': stems, 'peak_before_quantization': peak}


def align_signal(readout, pcm, rate, spec):
    signal = np.asarray(readout['signal'], dtype=float)
    source = readout['source']
    clock_bounds = [round(rate * (time - source['when'] + source['offset'])) for time in readout['signal_clock']]
    expected_end = clock_bounds[-1]
    radius = round(rate * spec['audio_alignment_search_seconds'])
    start = max(0, expected_end - radius - len(signal))
    stop = min(len(pcm), expected_end + radius)
    search = pcm[start:stop]
    energy = np.r_[0, np.cumsum(search * search)]
    window_energy = np.maximum(energy[len(signal):] - energy[:-len(signal)], 0)
    normalization = np.sqrt(window_energy * np.dot(signal, signal))
    dots = correlate(search, signal, mode='valid')
    coefficients = np.divide(dots, normalization, out=np.zeros_like(dots), where=normalization > 0)
    best = int(np.argmax(coefficients))
    return {'expected_end_frame': expected_end, 'matching_end_frame': start + best + len(signal),
            'clock_bounds_frames': clock_bounds,
            'correlation': float(coefficients[best]), 'rms': float(np.sqrt(np.mean(signal ** 2)))}


def compare_browser(view, entry, source, pcm, upstream):
    rate = source['sample_rate_hz']
    frames = source['expected_frames']
    positions = view['positions']
    sources = view['sources']
    witnesses = [positions[label] for label in ('first_audio', 'second_audio')]
    comparisons = []
    for observed in witnesses:
        stamp = observed['timestamp']
        audible = min(observed['context_time'], stamp['contextTime']
                      + max(0, observed['performance_ms'] - stamp['performanceTime']) / 1000)
        current = observed['source']
        position = current['offset'] + max(0, audible - current['when'])
        comparisons.append({'display_minus_audible_seconds': observed['time'] - position,
                            'has_output_timestamp': stamp['contextTime'] > 0,
                            'sample_match': align_signal(observed, pcm, rate, entry)})
    expected_offsets = [0, entry['paused_seek_seconds'], entry['playing_seek_seconds'], entry['end_seek_seconds'], 0]
    sample_error = entry['maximum_ui_offset_error_samples']
    before = positions['before_rejection']
    after = positions['after_rejection']
    rejected_frame = round(entry['rejected_resume_seek_seconds'] * rate)
    return {
        'browser_errors': not view['errors'],
        'same_audio_buffer': (view['decoded']['length'] == frames and view['decoded']['rate'] == rate
                              and view['decoded']['channels'] == 1 and view['wave_sha256'] == view['expected_wave_sha256']),
        'source_offsets': len(sources) == len(expected_offsets) and all(
            abs(record['offset'] - target) * rate <= sample_error
            for record, target in zip(sources, expected_offsets, strict=True))
        and all(sources[i]['stop_called'] and sources[i]['disconnected'] for i in (0, 1, 2))
        and sources[3]['ended'],
        'initial_pause_and_seeks': (
            positions['ready']['frame'] == 0 and positions['ready']['epoch'] == 0
            and positions['paused']['frame'] == positions['held']['frame']
            and 0 <= positions['paused']['time'] - positions['first_audio']['time'] <= 0.20
            and not positions['paused_seek']['playing'] and positions['paused_seek']['epoch'] == 1
            and abs(positions['paused_seek']['frame'] - entry['paused_seek_seconds'] * rate) <= sample_error
            and positions['second_audio']['epoch'] == 2 and positions['second_audio']['playing']
            and positions['end']['epoch'] == 3 and positions['end']['frame'] == frames
            and not positions['end']['playing'] and positions['again']['playing']),
        'audible_clock': all(w['has_output_timestamp']
              and abs(w['display_minus_audible_seconds']) <= entry['maximum_ui_clock_error_seconds']
              for w in comparisons),
        'waveform_matches_cli_at_two_offsets': all(w['sample_match']['rms'] > 0
              and w['sample_match']['correlation'] >= entry['minimum_signal_correlation'] for w in comparisons),
        'seek_during_rejected_resume': (before['playing'] and before['epoch'] == after['epoch'] == 4
            and before['context_state'] == after['context_state'] == 'suspended'
            and before['frame'] == after['frame'] == rejected_frame and after['playing'] == upstream
            and after['source']['stop_called'] == after['source']['disconnected'] == (not upstream)),
    }, comparisons


def measure(case, source, demo, bun, artifacts, execute):
    execute([*bun, 'test', 'tests/transport.test.ts', 'tests/tele.test.ts'], cwd=UPSTREAM,
            stdout=artifacts / 'upper-tests.log')
    wave, mix = synthesize(case['source'], source, artifacts, execute)
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=artifacts / 'browser-build.log')
    execute(['node', str(CAPTURE), str(CASE), str(UPSTREAM), str(artifacts), str(wave)])
    observation = read_json(artifacts / 'browser.json')
    model = read_json(artifacts / 'virtual-clock.json')
    _, pcm = wavfile.read(wave)
    pcm = pcm.astype(float) / 32768
    checks = {f'virtual_{engine}_{row["id"]}': row['passed'] for engine, scenarios in model.items() for row in scenarios}
    checks['demo_matches_independently_rerendered_wav'] = sha256(wave) == sha256(demo)
    evidence = {}
    for label in ('candidate', 'upstream'):
        compared, evidence[label] = compare_browser(observation[label], case['browser'], case['source'], pcm, label == 'upstream')
        checks.update({f'{label}_{key}': value for key, value in compared.items()})
    return {'checks': checks, 'mix': mix, 'browser': observation['version'], 'audio_and_clock': evidence,
            'virtual_steps': {name: sum(len(row['steps']) for row in rows) for name, rows in model.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id', nargs='?')
    parser.add_argument('--prepare-demo', action='store_true', help='公開用の小さなデモWAVをCLIから作る')
    args = parser.parse_args()
    case = read_json(CASE)
    source = WORKSPACE / 'cases' / case['source']['case']
    directory = WEB / 'public/shows' / case['source']['show_id']
    manifest = directory / 'show.json'
    show = read_json(manifest)
    demo = directory / show['audio']
    if args.prepare_demo:
        with TemporaryDirectory() as temporary:
            wave, _ = synthesize(case['source'], source, Path(temporary),
                                 lambda command: subprocess.run(command, cwd=WORKSPACE, check=True))
            shutil.copyfile(wave, demo)
        return 0
    if not args.run_id or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('英数字で始まる実行IDが必要です')
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        parser.error('変更のない固定上流版が必要です')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    upper_paths = ['src/ui/App.tsx', 'src/ui/components/DuetPage.tsx', 'src/show/transport.ts',
                   'src/show/tele.ts', 'src/audio/session.ts', 'tests/transport.test.ts', 'tests/tele.test.ts']
    details = {'case_id': case['id'], 'upstream_revision': revision,
               'upstream_source_sha256': {name: sha256(UPSTREAM / name) for name in upper_paths},
               'node': subprocess.check_output(['node', '--version'], text=True).strip(),
               'bun': subprocess.check_output([*bun, '--version'], text=True).strip()}
    inputs = [CASE, source, manifest, demo,
              *(directory / voice[key] for voice in show['voices'] for key in ('tele', 'melody') if key in voice),
              CAPTURE, MODEL, Path(__file__), Path(shared.__file__),
              *web_sources(), *shared.candidate_sources()]
    return shared.record_measurement(args.run_id, CASE, inputs, details,
        lambda artifacts, execute: measure(case, source, demo, bun, artifacts, execute), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
