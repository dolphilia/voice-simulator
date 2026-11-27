"""基準10母音の線形応答、固定発声、隣接遷移を一つの実行で測る。"""

import argparse
import csv
import json
from pathlib import Path
import re
import subprocess
import sys

import numpy as np
import scipy
from scipy.io import wavfile

import measure_uniform_tube as shared
from vowel_boundary import probe_boundaries
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/vowel-benchmark.json'
TOOLS = WORKSPACE / 'tools'
TABLE = UPSTREAM / 'crates/chimera/src/phonetics/vowelTargets.generated.json'


def case_files(case):
    ids = [entry['slug'] for entry in case['vowels']]
    paths = [WORKSPACE / 'cases' / f'vowel-{mode}-{slug}.json'
             for slug in ids for mode in ('transfer', 'voice')]
    return [CASE, *paths, WORKSPACE / 'cases' / f"{case['continuity_case']}.json"]


def read_case(path):
    return json.loads(path.read_text())


def verify_cases(case):
    settings = case['measurement']['fixed_pose']
    poses = {}
    for entry in case['vowels']:
        ipa, slug = entry['ipa'], entry['slug']
        transfer = read_case(WORKSPACE / 'cases' / f'vowel-transfer-{slug}.json')
        voice = read_case(WORKSPACE / 'cases' / f'vowel-voice-{slug}.json')
        analysis = voice['measurement']['voice']
        if (ipa in poses or transfer['posture'] != voice['posture']
                or any(item['body'] != case['body'] or item['upstream_revision'] != case['upstream_revision']
                       or item['fixed_airway']['sample_rate_hz'] != settings['sample_rate_hz']
                       for item in (transfer, voice))
                or transfer['measurement']['transfer']['ipa'] != ipa or analysis['ipa'] != ipa
                or any(transfer['transfer'][key] != settings[key] for key in ('start_hz', 'end_hz', 'points'))
                or any(analysis[key] != settings[key] for key in ('start_frame', 'frame_count',
                                                                 'lpc_sample_rate_hz', 'lpc_order'))
                or voice['voice'] != settings['voice']):
            raise ValueError(f'基準母音 {ipa} の姿勢または計測条件が一致しません')
        poses[ipa] = transfer['posture']

    motion = read_case(WORKSPACE / 'cases' / f"{case['continuity_case']}.json")
    order = list(poses)
    events = motion['articulators']['events']
    spans = motion['measurement']['area_control']['transitions']
    if motion['posture'] != poses[order[0]] or not len(events) == len(spans) == len(order) - 1:
        raise ValueError('隣接母音の初期姿勢またはイベント数が一致しません')
    for i, (event, span) in enumerate(zip(events, spans, strict=True)):
        pose = dict(poses[order[i+1]])
        for part in ('tongue_body', 'tongue_tip'):
            pose[f'{part}_x_cm'], pose[f'{part}_y_cm'] = pose.pop(f'{part}_cm')
        if (pose != event['targets'] or span['start_frame'] != event['frame']
                or (span['from_ipa'], span['to_ipa']) != (order[i], order[i+1])):
            raise ValueError(f'{order[i]} → {order[i+1]} の姿勢または計測フレームが一致しません')


def run_case(execute, script, run_id, case_id, *extra):
    run = WORKSPACE / 'runs' / run_id
    result = {'run_id': run_id, 'status': 'fail', 'error': None, 'manifest_sha256': None}
    if run.exists():
        result['error'] = '指定IDに対応するサブケースが既にあります'
        return result, {}
    try:
        execute([sys.executable, str(TOOLS / f'measure_{script}.py'), run_id, case_id, *extra])
    except subprocess.CalledProcessError:
        pass
    manifest_path = run / 'manifest.json'
    summary_path = run / 'summary.json'
    if not manifest_path.is_file():
        result['error'] = 'サブケースの実行記録が作成されませんでした'
        return result, {}
    manifest = read_case(manifest_path)
    if (manifest['run_id'], manifest['case_id']) != (run_id, case_id):
        raise ValueError(f'{run_id} の実行IDまたはケースが不一致です')
    result.update(status=manifest['status'], error=manifest.get('error'), manifest_sha256=sha256(manifest_path))
    if not summary_path.is_file():
        return result, {}
    summary = read_case(summary_path)
    if not any(item['path'] == 'summary.json' and item['sha256'] == sha256(summary_path)
               for item in manifest['outputs']):
        raise ValueError(f'{run_id} の要約が実行記録と不一致です')
    return result, summary


def native_reference(case, artifacts, execute):
    execute(['cargo', 'build', '--locked', '--release', '-p', 'chimera-cli'], cwd=UPSTREAM)
    stem = artifacts / 'upstream-vowel-sequence'
    log = artifacts / 'upstream-vowel-sequence.log'
    execute([str(UPSTREAM/'target/release/chimera'), 'render', 'vowels', case['body'],
             str(stem), '--float'], cwd=UPSTREAM, stdout=log)
    rate, pcm = wavfile.read(stem.with_suffix('.wav'))
    cfg = case['measurement']['native_vowel_sequence']
    valid_wave = (rate == cfg['sample_rate_hz'] and pcm.shape == (cfg['frames'],)
                  and pcm.dtype == np.float32 and np.isfinite(pcm).all())
    pattern = re.compile(r'^\s*(\S+)\s+f0=([\d.]+)\s+LPC\s+(.*?)\s+model\s+(.*?)\s*$')
    rows = []
    for line in log.read_text().splitlines():
        match = pattern.match(line)
        if match:
            ipa, f0, lpc, model = match.groups()
            rows.append({'ipa': ipa, 'pcm_f0_hz': float(f0), 'lpc_hz': [int(x) for x in lpc.split()],
                         'table_formants_hz': [int(x) for x in model.split()]})
    return {'pcm_valid': bool(valid_wave), 'rows': rows,
            'matches_order': [row['ipa'] for row in rows] == [entry['ipa'] for entry in case['vowels']]}


def write_table(path, rows):
    header = ('ipa', 'linear_status', 'voice_status', 'pcm_f0_hz', 'linear_f1_hz', 'linear_f2_hz',
              'linear_f3_hz', 'lpc_f1_hz', 'lpc_f2_hz', 'lpc_f3_hz', 'pcm_rms', 'pcm_max_error',
              'linear_missing_bandwidth_indices')
    with path.open('w', newline='') as file:
        writer = csv.writer(file, lineterminator='\n')
        writer.writerow(header)
        for row in rows:
            linear = (row.get('linear_hz', []) + [None]*3)[:3]
            lpc = ([item[0] for item in row.get('lpc_hz_and_bandwidth', [])] + [None]*3)[:3]
            writer.writerow((row['ipa'], row['linear_run']['status'], row['voice_run']['status'],
                             row.get('pcm_f0_hz'), *linear, *lpc, row.get('pcm_rms'),
                             row.get('pcm_max_absolute_error'), ' '.join(map(str, row.get('missing_bandwidth', [])))))


def measure(case, run_id, artifacts, execute):
    rows = []
    checks = {}
    for entry in case['vowels']:
        ipa, slug = entry['ipa'], entry['slug']
        linear_id = f'{run_id}-linear-{slug}'
        transfer_run, transfer = run_case(execute, 'vowel_transfer', linear_id, f'vowel-transfer-{slug}')
        voice_run, voice = run_case(execute, 'vowel_voice', f'{run_id}-voice-{slug}', f'vowel-voice-{slug}',
                                   '--linear-run', linear_id)
        checks[f'linear_{slug}'] = transfer_run['status'] == 'pass'
        checks[f'voice_{slug}'] = voice_run['status'] == 'pass'
        row = {'ipa': ipa, 'slug': slug, 'linear_run': transfer_run, 'voice_run': voice_run}
        if transfer:
            peaks = transfer['peaks']
            row.update(linear_hz=peaks['peaks_hz'], linear_bandwidth_hz=peaks['bandwidths_hz'],
                       missing_bandwidth=peaks['missing_bandwidth_indices'],
                       table_formants_hz=peaks['table_formants_hz'], target_formants_hz=peaks['target_formants_hz'],
                       minimum_area_cm2=transfer['minimum_cm2'],
                       linear_peak_relative_flow_error=transfer['upstream_peak_relative_flow_error'])
        if voice:
            acoustic = voice['acoustic']
            row.update(pcm_f0_hz=acoustic['pcm_f0_hz'], pcm_rms=voice['steady_rms'],
                       glottal_cycle_f0_hz=acoustic['glottal_cycle_rate_hz'],
                       lpc_hz_and_bandwidth=acoustic['lpc_formants_frequency_bandwidth_hz'],
                       excluded_nyquist=acoustic['upstream_excluded_nyquist_frequency_bandwidth_hz'],
                       pcm_max_absolute_error=voice['maximum_pcm_absolute_error'],
                       pcm_bits_equal=voice['pcm_sample_bytes_equal'])
        if transfer and voice:
            row['first_three_lpc_minus_linear_hz'] = voice['acoustic']['first_three_lpc_minus_linear_hz']
        rows.append(row)

    continuity_run, motion = run_case(execute, 'tract_control', f'{run_id}-continuity', case['continuity_case'])
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'geometry_continuity',
             'no_area_jumps_on_the_way_between_calibrated_vowels', '--', '--nocapture'],
            cwd=UPSTREAM, stdout=artifacts/'upstream-continuity.log')
    checks['nine_observed_transitions'] = (continuity_run['status'] == 'pass'
                                            and len(motion.get('transitions', [])) == len(rows) - 1)
    write_table(artifacts/'vowels.csv', rows)
    try:
        native = native_reference(case, artifacts, execute)
        checks['native_reference_sequence'] = native['pcm_valid'] and native['matches_order']
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        native = {'error': str(error)}
        checks['native_reference_sequence'] = False
    try:
        boundary = probe_boundaries(case, motion, artifacts, execute) if motion else {}
        checks['minimum_boundary_probe'] = bool(boundary) and all(boundary['checks'].values())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        boundary = {'error': str(error)}
        checks['minimum_boundary_probe'] = False
    return {'checks': checks, 'vowels': rows, 'continuity_run': continuity_run,
            'transitions': motion.get('transitions', []), 'native_reference': native,
            'minimum_boundary': boundary}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*', args.run_id):
        parser.error('英数字で始まる実行IDを指定してください')
    case = read_case(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if (revision != case['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        raise ValueError('変更のない固定上流版が必要です')
    verify_cases(case)
    inputs = [*case_files(case), Path(__file__).resolve(),
              *(TOOLS/f'{name}.py' for name in ('measure_vowel_transfer', 'measure_vowel_voice',
                                               'measure_tract_control', 'measure_uniform_tube',
                                               'vowel_boundary', 'measure_sagittal')),
              TOOLS / 'upstream_sagittal_probe.rs', *shared.candidate_sources()]
    details = {'upstream_revision': revision, 'case_id': case['id'],
               'upstream_vowel_table_sha256': sha256(TABLE), 'scipy_version': scipy.__version__}
    return shared.record_measurement(args.run_id, CASE, inputs, details,
                                     lambda artifacts, execute: measure(case, args.run_id, artifacts, execute),
                                     command=None)


if __name__ == '__main__':
    raise SystemExit(main())
