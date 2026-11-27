"""二声のテレメトリを上流のCLIと読出し、波形、研究画面に照合する。"""

import argparse
from hashlib import sha256 as digest
import json
from pathlib import Path
import re
import shutil
from struct import unpack
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
from scipy.io import wavfile

from measure_duet_transport import CASE as TRANSPORT_CASE
from measure_fan_crossing_allocations import run_manifest, verified_path
import measure_uniform_tube as shared
from measure_wasm_fixed import read_json
from measure_worklet_fixed import ROOT, WEB, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/duet-telemetry.json'
CAPTURE = WEB / 'tools/capture-duet-telemetry.mjs'


class Track:
    def __init__(self, file):
        data = file.read_bytes()
        self.magic, self.version, self.rate, self.hop, self.rows, width, self.artic, ph, oral, self.scope, *self.body = (
            unpack('<4s9I2f', data[:48]))
        self.cells = ph + oral
        self.payload_sha = digest(data[48:]).hexdigest()
        self.values = np.frombuffer(data, dtype='<f4', offset=48).reshape(self.rows, width)
        if width != 11 + self.artic + 3 * self.cells + 2 * self.scope or not np.isfinite(self.values).all():
            raise ValueError(f'{file.name} の列数または有限性が不正です')
        self.clock = self.values[:, 10]
        self.postures = self.values[:, 11:11 + self.artic]
        self.areas, self.pressure, self.flow = np.split(self.values[:, 11 + self.artic:11 + self.artic + 3 * self.cells], 3, axis=1)
        self.glottis = self.values[:, -2 * self.scope:]
        self.header = [self.rate, self.hop, self.rows, ph, oral, dict(zip(('female', 'child'), self.body, strict=True))]

    def follows_clock(self, constraints, samples):
        return (self.magic.decode('ascii') == constraints['magic'] and self.version == constraints['version']
                and self.rate == constraints['sample_rate_hz'] and self.hop == constraints['hop_samples']
                and self.artic == constraints['articulators'] and self.scope == constraints['scope_points']
                and self.rows == samples // self.hop + 1
                and float(np.max(np.abs(self.clock - np.arange(self.rows) * self.hop / self.rate)))
                <= constraints['clock_absolute_tolerance_seconds'])


def candidate_render(source, index, out, execute, block=128):
    stem = f'voice-{index}'
    wave, trace, tele = (out / f'{stem}.{suffix}' for suffix in ('wav', 'csv', 'tele'))
    execute(['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--', 'render-pcm-tele',
             str(source), str(wave), str(trace), str(tele), str(block)])
    return wave, tele


def candidate_noise_branches(source):
    result = subprocess.check_output([str(WORKSPACE / 'target/release/vocal-cli'), 'inspect', str(source)], cwd=WORKSPACE)
    return json.loads(result)['noise_branches']


def upper_render(voice, song, index, artifacts, execute):
    path = artifacts / f'upper-{index}-notes.json'
    wave = artifacts / f'upper-{index}.wav'
    wave_without_tele = artifacts / f'upper-{index}-unobserved.wav'
    tele = artifacts / f'upper-{index}.tele'
    path.write_text(json.dumps({'bpm': song['score']['bpm'], 't0': voice['start_seconds'],
                               'lyrics': song['score']['lyrics'], 'notes': [[m, note['beats']] for m, note in zip(
                                   voice['midi'], song['score']['notes'], strict=True)],
                               'vibrato': song['vibrato_cents']}, ensure_ascii=False) + '\n')
    command = ['cargo', 'run', '--locked', '--release', '-p', 'chimera-cli', '--', '--float', 'render', 'notes', str(path)]
    execute([*command, str(wave), voice['body'], '--tele', str(tele)], cwd=UPSTREAM)
    execute([*command, str(wave_without_tele), voice['body']], cwd=UPSTREAM)
    return wave, tele, sha256(wave) == sha256(wave_without_tele)


def reference_tract(source, index, track, constraints, artifacts, execute):
    hop = track.hop
    sample_index = np.arange(1, track.rows) * hop - 1
    control = constraints['control_period_output_samples']
    stride = constraints['pressure_stride_output_samples']
    pressure_windows = [list(range((i - 1) * hop + stride - 1, i * hop, stride))
                        for i in constraints['pressure_test_hop_indices']]
    control_offsets = list(range(control, int(sample_index[-1]) + 1, control))
    points = sorted({*sample_index.tolist(), *(position - 1 for position in control_offsets),
                     *(position for window in pressure_windows for position in window)})
    case = read_json(source)
    case['song_voice'].update(tract_profile_frames=points, tract_profile_acoustics=True)
    settings = artifacts / f'tract-{index}.json'
    settings.write_text(json.dumps(case, ensure_ascii=False) + '\n')
    output = artifacts / f'tract-{index}.csv'
    execute(['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--', 'render', str(settings), str(output)])
    trace = np.loadtxt(output, skiprows=1, delimiter=',', usecols=(0, 3, 4, 6, 7)).reshape(len(points), track.cells, 5)
    if not np.array_equal(trace[:, 0, 0], points):
        raise ValueError('独立採取のサンプル番号が一致しません')
    raw = dict(zip(points, trace, strict=True))
    reference_areas = np.array([raw[i][:, 2] for i in sample_index], dtype=np.float32)
    reference_pressure = np.array([np.sqrt(np.mean(np.stack([raw[p][:, 3] for p in window]) ** 2, axis=0))
                                   for window in pressure_windows])
    observed = track.pressure[constraints['pressure_test_hop_indices']]
    alpha = 1 - np.exp(-control / track.rate / 0.03)
    filtered = np.zeros(track.cells)
    filtered_rows = []
    for tick in control_offsets:
        if tick % hop == 0:
            filtered_rows.append(filtered.copy())
        filtered += alpha * (raw[tick - 1][:, 4] - filtered)
    filtered_rows.append(filtered.copy())
    return {
        'cell_area_trace': np.array_equal(reference_areas, track.areas[1:]),
        'independent_pressure_rms': bool(np.allclose(observed, reference_pressure, rtol=constraints['pressure_rms_relative_tolerance'], atol=0)),
        'independent_flow_smoothing': bool(np.allclose(track.flow[1:], filtered_rows,
             rtol=constraints['flow_relative_tolerance'], atol=constraints['flow_absolute_tolerance_cm3_s'])),
    }, {'pressure_rms_error_max': float(np.max(abs(observed - reference_pressure))),
        'flow_error_max': float(np.max(abs(track.flow[1:] - filtered_rows))), 'compared_tract_samples': len(points)}


def reference_scalars(source, index, track, constraints, pcm, artifacts, execute):
    trace = artifacts / f'raw-voice-{index}.csv'
    execute(['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--', 'render', str(source), str(trace)])
    with trace.open() as stream:
        header = stream.readline().strip().split(',')
        fields = ['lip_aperture_cm', 'glottal_f0_hz', 'gate', 'glottal_area_cm2', 'glottal_flow_cm3_s']
        full = np.loadtxt(stream, delimiter=',', usecols=[header.index(column) for column in fields], dtype=np.float32)
    hop = track.hop
    indices = np.arange(1, track.rows) * hop - 1
    rms = np.sqrt(np.mean(pcm[:len(indices) * hop].astype(float).reshape(len(indices), hop) ** 2, axis=1))
    expected_scope = np.pad(full[:hop, 3:5], ((1024 - hop, 0), (0, 0)))[::1024 // track.scope].T.ravel()
    return {
        'initial_rms_and_scope_zero': bool(np.all(track.pressure[0] == 0) and np.all(track.glottis[0] == 0)
                                           and track.values[0, 6] == 0 and track.clock[0] == 0),
        'f0_lip_gate_trace': np.array_equal(full[indices, :3], np.stack((track.postures[1:, 7], track.values[1:, 3], track.values[1:, 9]), axis=1)),
        'scope_fallback_trace': np.array_equal(track.glottis[1], expected_scope),
        'independent_pcm_rms': float(np.max(abs(rms - track.values[1:, 6]))) <= constraints['pcm_rms_absolute_tolerance'],
    }, {'pcm_rms_error_max': float(np.max(abs(rms - track.values[1:, 6])))}


def ui_checks(report, browser, tracks, voices):
    def follows(readout):
        expected = [min(t.rows - 1, (int(np.floor(readout['time'] * t.rate + 1e-7))) // t.hop) for t in tracks]
        return len(readout['voices']) == len(tracks) and all(
            row['name'] == voice['name'] and row['index'] == i and row['sample'] == i * track.hop
            and abs(row['f0'] - track.values[i, 3]) <= 0.00051 and abs(row['lip'] - track.postures[i, 7]) <= 0.000051
            for row, track, i, voice in zip(readout['voices'], tracks, expected, voices, strict=True))

    paused, live, held = (report[key] for key in ('paused', 'live', 'held'))
    return {
        'browser_has_no_errors': not report['errors'],
        'browser_paused_seeks_choose_each_track': [entry['frame'] for entry in paused] == browser['paused_seek_samples']
            and all(not entry['playing'] and entry['epoch'] == i and follows(entry) for i, entry in enumerate(paused)),
        'browser_forward_and_backward_seeks_choose_each_track': len(live) == 3 and live[1]['frame'] > live[2]['frame']
            and all(entry['playing'] and entry['epoch'] == len(paused) + i and follows(entry) for i, entry in enumerate(live)),
        'browser_pause_holds_both_voices': len(held) == 2 and held[0] == held[1] and not held[0]['playing'] and follows(held[0]),
        'browser_rejects_truncated_track': 'バイト数' in report['badFile'] and not report['invalidCanPlay'],
    }


def measure(case, refs, transport, bun, demo, artifacts, execute):
    fmt = case['format']
    voices = transport['source']['voices']
    execute([*bun, 'test', 'tests/tele.test.ts', 'tests/transport.test.ts'], cwd=UPSTREAM, stdout=artifacts / 'upper-tests.log')
    checks = {'mixed_demo_keeps_prior_wav': sha256(demo / 'mix.wav') == sha256(verified_path(refs, 'artifacts/mix.wav'))}
    tracks = []
    summaries = []
    inputs = {}
    for index, voice in enumerate(voices, 1):
        source = verified_path(refs, f'artifacts/voice-{index}.json')
        wave, tele = candidate_render(source, index, artifacts, execute, block=(128 if index == 1 else 77))
        upper_wave, upper_tele, upper_pcm_consistent = upper_render(voice, read_json(source)['song_voice'], index, artifacts, execute)
        track, upper = Track(tele), Track(upper_tele)
        tracks.append(track)
        inputs.update({tele.name: track, upper_tele.name: upper})
        _, pcm = wavfile.read(wave)
        _, upper_pcm = wavfile.read(upper_wave)
        part = {
            'candidate_header_and_sample_clock': track.follows_clock(fmt, len(pcm)) and track.rows == fmt['expected_records'][index - 1]
                and len(pcm) == fmt['stem_frames'][index - 1] and track.body == fmt['body_mix'][index - 1],
            'upper_header_and_sample_clock': upper.follows_clock(fmt, len(upper_pcm)) and upper.body == track.body,
            'upper_telemetry_keeps_pcm': upper_pcm_consistent,
            'candidate_pcm_keeps_prior_stem': sha256(wave) == sha256(verified_path(refs, f'artifacts/voice-{index}.wav')),
            'public_tele_matches_cli': sha256(tele) == sha256(demo / tele.name),
        }
        tract, tract_notes = reference_tract(source, index, track, fmt, artifacts, execute)
        scalars, scalar_notes = reference_scalars(source, index, track, fmt, pcm, artifacts, execute)
        checks.update({f'voice_{index}_{key}': value for key, value in (part | tract | scalars).items()})
        common = min(track.rows, upper.rows)
        difference = abs(track.clock[:common] - upper.clock[:common])
        checks[f'voice_{index}_clock_matches_upper'] = float(np.max(difference)) <= fmt['clock_absolute_tolerance_seconds']
        differing_axes = np.flatnonzero(track.postures[0] != upper.postures[0]).tolist()
        summaries.append({'name': voice['name'], 'candidate': track.header, 'upstream': upper.header,
                          'upper_pcm_frames': len(upper_pcm), 'common_clock_max_error_seconds': float(np.max(difference)),
                          'initial_candidate_f0_lip': [float(track.values[0, 3]), float(track.postures[0, 7])],
                          'initial_upper_f0_lip': [float(upper.values[0, 3]), float(upper.postures[0, 7])],
                          'initial_candidate_tract_lengths_cm': track.values[0, :2].tolist(),
                          'initial_upper_tract_lengths_cm': upper.values[0, :2].tolist(),
                          'initial_articulator_differences': [{'axis_index': a, 'candidate': float(track.postures[0, a]),
                                                               'upstream': float(upper.postures[0, a])} for a in differing_axes],
                          **tract_notes, **scalar_notes})
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=artifacts / 'build.log')
    execute(['node', str(CAPTURE), str(CASE), str(UPSTREAM), str(artifacts), transport['source']['show_id']])
    interop = read_json(artifacts / 'decoders.json')
    report = read_json(artifacts / 'browser-telemetry.json')
    checks['all_payloads_read_identically_by_both_decoders'] = len(interop['compare']) == 4 and all(
        row['header'] == row['upperHeader'] == inputs[row['name']].header
        and row['decodedCandidate'] == row['decodedUpstream'] == row['sourcePayload'] == inputs[row['name']].payload_sha
        and all(c == u for _, c, u in row['positions']) for row in interop['compare'])
    checks['both_decoders_reject_truncated_track'] = all(interop['truncated'].values())
    checks.update(ui_checks(report, case['browser'], tracks, voices))
    return {'checks': checks, 'browser': report['version'], 'voices': summaries}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id', nargs='?')
    parser.add_argument('--prepare-demo', action='store_true', help='既存の二声音源に対応する公開用テレメトリを作る')
    args = parser.parse_args()
    case = read_json(CASE)
    rev = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if rev != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        parser.error('変更のない固定上流版が必要です')
    transport = read_json(TRANSPORT_CASE)
    refs = run_manifest(case['reference']['run'], transport['id'], rev)
    ref_manifest = refs[0] / 'manifest.json'
    if refs[1]['status'] != 'pass' or sha256(ref_manifest) != case['reference']['manifest_sha256']:
        parser.error('登録した再生基準を照合できません')
    demo = WEB / 'public/shows' / transport['source']['show_id']
    stems = [[verified_path(refs, f'artifacts/voice-{i}.{ext}') for ext in ('json', 'wav')]
             for i in range(1, 1 + len(transport['source']['voices']))]
    if args.prepare_demo:
        manifest_path = demo / 'show.json'
        show = read_json(manifest_path)
        with TemporaryDirectory() as directory:
            def execute(command):
                subprocess.run(command, cwd=WORKSPACE, check=True)

            paths = []
            for index, (voice, (source, prior)) in enumerate(zip(show['voices'], stems, strict=True), 1):
                wave, tele = candidate_render(source, index, Path(directory), execute)
                if sha256(wave) != sha256(prior):
                    parser.error('テレメトリの採取中に音源が変化しました')
                if voice.get('tele') != tele.name:
                    parser.error('公演と生成したテレメトリのファイル名が一致しません')
                voice['noise_branches'] = candidate_noise_branches(source)
                paths.append(tele)
            for tele in paths:
                shutil.copyfile(tele, demo / tele.name)
            manifest_path.write_text(json.dumps(show, ensure_ascii=False, indent=2) + '\n')
        return 0
    if not args.run_id or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('英数字で始まる実行IDが必要です')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    upstream_paths = ['crates/chimera-cli/src/render.rs', 'crates/chimera/src/voice/human_voice.rs',
                      'src/ui/components/DuetPage.tsx', 'src/show/tele.ts', 'tests/tele.test.ts', 'tests/transport.test.ts']
    details = {'case_id': case['id'], 'upstream_revision': rev, 'upstream_source_sha256': {name: sha256(UPSTREAM / name) for name in upstream_paths},
               'node': subprocess.check_output(['node', '--version'], text=True).strip(),
               'bun': subprocess.check_output([*bun, '--version'], text=True).strip()}
    demo_show = read_json(demo / 'show.json')
    inputs = [CASE, TRANSPORT_CASE, ref_manifest, *(path for stem in stems for path in stem),
              verified_path(refs, 'artifacts/mix.wav'), CAPTURE, Path(__file__), Path(shared.__file__),
              Path(__file__).with_name('measure_duet_transport.py'),
              *(demo / name for name in ('show.json', 'mix.wav', 'voice-1.tele', 'voice-2.tele')),
              *(demo / voice['melody'] for voice in demo_show['voices'] if 'melody' in voice),
              *web_sources(), *shared.candidate_sources()]
    return shared.record_measurement(args.run_id, CASE, inputs, details,
        lambda artifacts, execute: measure(case, refs, transport, bun, demo, artifacts, execute), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
