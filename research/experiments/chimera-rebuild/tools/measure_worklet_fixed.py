"""ブラウザのWAVと状態をネイティブCLI、固定上流、独立した時刻・F0計算に照合する。"""

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_pcm_output as pcm
import measure_uniform_tube as shared
import measure_vowel_voice as vowel
import measure_wasm_fixed as wasm
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

ROOT = WORKSPACE.parents[2]
WEB = ROOT / 'web/prototypes/chimera-research'
CASE = WORKSPACE / 'cases/worklet-fixed-voice.json'
CAPTURE = WEB / 'tools/capture-worklet.mjs'


def web_sources():
    return [
        CAPTURE, WEB / 'tools/fake-midi.mjs', WEB / 'tools/observe-live-tract.mjs',
        WEB / 'tools/shared-context-marker.mjs', WEB / 'tools/shared-context-marker-worklet.js',
        WEB / 'tools/song-output-probe.mjs', WEB / 'tools/song-output-probe-worklet.js',
        ROOT / 'web/shared/audio/fft.ts',
        *(WEB / name for name in ('package.json', 'bun.lock', 'index.html', 'tsconfig.json', 'vite.config.ts')),
        *sorted(path for path in (WEB / 'src').iterdir() if path.is_file()),
        *sorted((WORKSPACE / 'crates/vocal-wasm/host').glob('*.ts')),
        *(WORKSPACE / 'cases' / name for name in ('vowel-voice-i.json', 'worklet-fixed-voice.json',
          'worklet-realtime-voice.json', 'worklet-realtime-voice-44100.json', 'worklet-realtime-voice-32000.json',
          'worklet-realtime-voice-16000.json', 'worklet-realtime-voice-96000.json', 'worklet-midi-voice.json',
          'worklet-tract-3d.json', 'worklet-tract-3d-dynamic.json',
          'bilabial-p.json', 'worklet-ipa-voice.json',
          'song-voice-long.json', 'worklet-song-voice.json', 'worklet-song-prepared-source.json',
          'beatbox-pattern-hum.json', 'worklet-beatbox-pattern.json', 'worklet-live-beatbox.json',
          'english-mom-pop.json', 'worklet-english-voice.json', 'worklet-tract-profile.json',
          'worklet-glottal-scope.json', 'worklet-pcm-spectrum.json', 'worklet-live-ipa.json', 'worklet-live-song.json',
          'worklet-live-song-render-warmup.json', 'worklet-live-tsp-firefox-render-preparation.json',
          'worklet-songbird-sustain.json', 'songbird-sustain-pcm.json', 'worklet-midi-songbird.json', 'worklet-midi-songbird-call.json',
          'worklet-songbird-flute.json', 'songbird-flute.json',
          'worklet-songbird-trill.json', 'worklet-songbird-trill-observation.json',
          'worklet-songbird-chirps.json', 'worklet-songbird-buzz.json',
          'worklet-songbird-switch.json',
          'songbird-calls.json', 'worklet-seal-sustain.json', 'seal-sustain-pcm.json', 'worklet-midi-seal.json', 'worklet-midi-seal-call.json',
          'worklet-seal-trill.json', 'seal-trill.json', 'worklet-seal-zap.json', 'seal-zap.json',
          'worklet-seal-whistle.json', 'seal-whistle.json', 'worklet-seal-chug.json', 'seal-chug-v2.json',
          'worklet-alligator-fixed-voice.json', 'alligator-fixed-voice-v2.json', 'worklet-midi-alligator.json',
          'worklet-midi-alligator-call.json',
          'worklet-alligator-bellow.json', 'alligator-bellow.json',
          'worklet-alligator-growl.json', 'alligator-growl.json',
          'worklet-alligator-hiss.json', 'alligator-hiss.json',
          'worklet-alligator-dance.json', 'alligator-dance.json',
          'worklet-elephant-fixed-voice.json', 'elephant-fixed-voice.json', 'worklet-midi-elephant.json',
          'worklet-midi-elephant-call.json',
          'worklet-elephant-rumble.json', 'elephant-rumble.json',
          'worklet-elephant-trumpet.json', 'elephant-trumpet.json',
          'worklet-elephant-squeak.json', 'elephant-squeak.json')),
        WORKSPACE / 'data/cmudict.txt.gz',
        WORKSPACE / 'data/CMUDICT-LICENSE.txt',
    ]


def compare(source, case, artifacts, execute, bun):
    limits = case['measurement']
    data = wasm.read_json(source)
    voice = data['voice']
    frames, rate, internal = (limits[key] for key in ('output_frames', 'output_rate_hz', 'internal_rate_hz'))
    quantum, stride = (limits[key] for key in ('expected_render_quantum_frames', 'observation_stride_frames'))
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=artifacts / 'browser-build.log')
    module = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(WORKSPACE / wasm.WASM, module)
    execute(['node', str(CAPTURE), str(artifacts), str(CASE)])

    prefix = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']
    trace = artifacts / 'native-trace.csv'
    execute([*prefix, 'render', str(source), str(trace)])
    rendered = pcm.render_blocks(source, {'block_frames': [quantum]}, artifacts, execute)
    native_rate, native_audio = wavfile.read(rendered[quantum][0])
    native_trace = pcm.read_columns(trace, frames)[1]
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'engine'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-engine.log')
    probe = shared.build_upstream_probe(vowel.PROBE, artifacts, execute)
    args = [data['measurement']['voice']['ipa'], internal, rate, frames, *(voice[k] for k in
            ('pressure_cm_h2o', 'gate', 'breathiness', 'tension', 'output_gain')), artifacts]
    execute([str(probe), 'render', *map(str, args)], cwd=UPSTREAM)
    upper_trace = pcm.read_columns(artifacts / 'upstream-trace.csv', frames)[1]
    upper_audio = np.fromfile(artifacts / 'upstream-voice.f32', dtype='<f4')

    browser_run = wasm.read_json(artifacts / 'browser-run.json')
    report = wasm.read_json(artifacts / 'browser.json')
    browser_rate, browser_audio = wavfile.read(artifacts / 'browser.wav')
    if any(audio.shape != (frames,) or audio.dtype != np.float32
           for audio in (native_audio, browser_audio, upper_audio)):
        raise ValueError('ブラウザ、CLIまたは上流のPCMの型・長さが条件外です')
    candidate = wasm.compare_pcm(browser_audio, native_audio, 0)
    upstream = wasm.compare_pcm(browser_audio, upper_audio, limits['upstream_pcm_absolute_tolerance'])
    fields = limits['observed_fields']
    if report['columns'] != ['context_frame', 'frames_rendered', *fields]:
        raise ValueError('Workletの観測列が条件と一致しません')
    points = np.minimum(np.arange(stride, frames + stride, stride), frames) - 1
    obs = np.asarray(report['observations'], dtype=float)
    if obs.shape != (len(points), len(fields) + 2) or not np.isfinite(obs).all():
        raise ValueError('Workletの観測点数・有限性が条件外です')
    states = obs[:, 2:]
    native_states, upstream_states = (
        np.column_stack([table[key][points] for key in fields]) for table in (native_trace, upper_trace))
    series_cli = wasm.compare_states(states, native_states, fields, points,
                                    limits['candidate_state_peak_relative_tolerance'])
    series_upstream = wasm.compare_states(states, upstream_states, fields, points,
                                         limits['upstream_state_peak_relative_tolerance'])
    sample_clock = internal // rate * (points + 1) - 1
    onset = wasm.first_index(abs(browser_audio) > limits['onset_threshold'])
    left, right = limits['steady_window_frames']
    selected = (points >= left) & (points < right)
    from_phase = wasm.phase_pitch(states[selected, fields.index('glottal_phase')], points[selected], rate)
    from_pcm, _ = vowel.independent_yin(browser_audio[left:right].astype(float), rate, data['measurement']['voice'])
    low, high = limits['expected_f0_hz']
    tests = [browser_run['normal']]
    if limits['check_retry_after_worklet_load_failure']:
        tests.append(browser_run['retry'])
    checks = {
        'same_source_and_format': (report['caseId'] == data['id'] and report['sampleRate'] == browser_rate
              == native_rate == report['workletSampleRate'] == rate == voice['output_sample_rate_hz']
              and report['outputFrames'] == report['framesRendered'] == frames
              and report['outputChannels'] == limits['output_channels']
              and data['fixed_airway']['sample_rate_hz'] == internal),
        'served_exact_wasm': all(run['servedWasmSha256'] == sha256(module) for run in tests),
        'cli_pcm_matches': candidate['first_bit_difference_frame'] is None if limits['require_cli_pcm_bit_equality']
                           else candidate['first_frame_over_tolerance'] is None,
        'fixed_upstream_pcm_matches': upstream['first_frame_over_tolerance'] is None,
        'quanta_are_contiguous': (report['firstContextFrame'] == report['discontinuities'] == 0
                and report['longestQuantum'] == report['shortestQuantum'] == quantum
                and report['callbacks'] == (frames + quantum - 1) // quantum),
        'browser_and_wasm_clocks_align': bool(
            np.array_equal(obs[:, 0], points) and np.array_equal(obs[:, 1], points + 1)
            and all(np.array_equal(table['internal_sample'][points], sample_clock)
                    for table in (native_trace, upper_trace))),
        'stable_wasm_buffers': not limits['require_stable_wasm_buffers'] or report['stableWasmBuffers'] is True,
        'cli_states_match': all(result['status'] for result in series_cli.values()),
        'fixed_upstream_states_match': all(result['status'] for result in series_upstream.values()),
        'onset_and_pitch': onset == limits['expected_onset_frame'] and all(
            value is not None and low <= value <= high for value in (from_phase, from_pcm)),
        'browser_controls_and_downloads': all(run['status'] == 'レンダー完了'
                 and not run['errors'] and round(rate * run['audioDuration']) == frames for run in tests),
    }
    if limits['check_retry_after_worklet_load_failure']:
        checks['retry_after_load_failure'] = (
            '計測用のWorklet読み込み失敗' in (browser_run['retry']['failure'] or '')
            and all(sha256(artifacts / f'browser.{ext}') == sha256(artifacts / f'retry.{ext}')
                    for ext in ('wav', 'json')))
    return {'checks': checks, 'browser': browser_run['version'], 'frames': frames,
            'callbacks': report['callbacks'], 'observations': len(points),
            'observation_first_and_last_frame': [int(points[0]), int(points[-1])],
            'pcm_onset_frame': onset, 'phase_f0_hz': from_phase, 'pcm_f0_hz': from_pcm,
            'cli_pcm': candidate, 'fixed_upstream_pcm': upstream,
            'cli_states': series_cli, 'fixed_upstream_states': series_upstream}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case = wasm.read_json(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    source = WORKSPACE / 'cases' / case['fixed_voice_case']
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    sources = [CASE, source, Path(__file__).resolve(), *web_sources(), *shared.candidate_sources(), vowel.PROBE,
               *(Path(tool.__file__) for tool in (pcm, shared, vowel, wasm)),
               WORKSPACE / 'tools/upstream_baseline.py', WORKSPACE / 'tools/measure_junction.py']
    upstream_paths = ['src/audio/AudioEngine.ts', 'src/worklet/processor.ts', 'tools/e2e.ts',
                      'crates/chimera/src/voice/human_voice.rs', 'crates/chimera/tests/engine.rs']
    metadata = {'case_id': case['id'], 'upstream_revision': revision, 'input_root': '$REPOSITORY',
                'node': subprocess.check_output(['node', '--version'], text=True).strip(),
                'bun': subprocess.check_output([*bun, '--version'], text=True).strip(),
                'web_diff_status': subprocess.check_output(
                    ['git', 'status', '--porcelain', '--', str(WEB)], cwd=ROOT, text=True).strip(),
                'upstream_source_sha256': {path: sha256(UPSTREAM / path) for path in upstream_paths}}
    return shared.record_measurement(args.run_id, CASE, sources, metadata,
                                     lambda out, run: compare(source, case, out, run, bun),
                                     command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
