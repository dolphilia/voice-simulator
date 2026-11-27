"""鳴禽の最後の直列枝を、44.1 kHz出力相当の内部レートで照合する。"""

import argparse
from fractions import Fraction
import math
from pathlib import Path
import subprocess
import sys

from measure_csd_envelope_timing import verified_file
from measure_songbird_airway import FIELDS, PROBE
from measure_songbird_chirps_beak_load import ROOT, SIDES, SPEED, beak_fields
from measure_songbird_chirps_beak_tip_inflow import UPPER_NETWORK, UPPER_SONGBIRD, capture_traces, compare_steps, diagnose_difference
from measure_songbird_syrinx import CLI, load_trace
from measure_speech_timing import read, write
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/songbird-chirps-beak-tip-inflow-44100.json'


def registered_artifacts(entry, case_id, revision, names):
    run = WORKSPACE / 'runs' / entry['run']
    manifest_path = run / 'manifest.json'
    manifest = read(manifest_path)
    if (sha256(manifest_path) != entry['manifest_sha256']
            or (manifest['status'], manifest['case_id'], manifest['upstream_revision']) != ('pass', case_id, revision)):
        raise ValueError(f'比較の登録と実行が異なります ({run.name})')
    return manifest_path, {name: verified_file(run, manifest, name) for name in names}


def compare_at_rate(case, references, out, execute):
    probe = build_upstream_probe(PROBE, out, execute, extra_libraries=('serde_json',))
    reference_rate = case['reference']['sample_rate_hz']
    reference_block = case['reference']['control_block_samples']
    rate = case['output_rate_hz'] * case['oversampling']
    matched = round(Fraction(reference_block * rate, reference_rate))
    native = case['output_control_frames'] * case['oversampling']
    observations = case['observation_internal_samples']
    reference = read(references['summary.json'])
    total_length = case['beak_length_cm']
    cells = math.floor(total_length * rate * 0.93 / SPEED)
    length = total_length / cells
    area_columns = [f'beak_{index}_area_cm2' for index in range(cells)]
    source = references['artifacts/archived.json']
    registered_trace = load_trace(references['artifacts/archived-candidate.csv'],
                                  FIELDS + beak_fields(reference['beak_cells']),
                                  read(source)['songbird_airway']['sample_count'])
    inspections = {}
    original = out / 'reference-geometry.json'
    execute([*CLI, 'inspect', str(source)], stdout=original)
    inspections['reference'] = read(original)['geometry']
    checks = {'registered_reference_run': all(reference['checks'].values())
              and reference['sample_rate_hz'] == reference_rate and reference['event_sample'] == reference_block
              and reference['cell_length_cm'] == length and reference['beak_cells'] == cells == case['expected_beak_cells']}
    hypotheses, conditions, results = {}, {}, {}
    for name, block, settings_key in (('matched_time', matched, 'archived'), ('native_block', native, 'archived'),
                                       ('no_tracking', matched, 'no-tracking')):
        settings = read(references[f'artifacts/{settings_key}.json'])
        bird = settings['songbird_airway']
        start, = bird['events']
        if (bird['sample_rate_hz'], bird['control_block_samples'], start['sample'], bird['observe_beak']) != (
                reference_rate, reference_block, reference_block, True):
            raise ValueError('元の鳴禽ケースと登録条件が一致しません')
        count = block + observations
        start['sample'] = block
        bird.update(sample_rate_hz=rate, sample_count=count, control_block_samples=block)
        definition = out / f'{name}.json'
        write(definition, settings)
        if name == 'matched_time':
            current = out / 'current-geometry.json'
            execute([*CLI, 'inspect', str(definition)], stdout=current)
            inspections['current'] = read(current)['geometry']
        _, traces = capture_traces(definition, out, name, probe, execute, cells, count)
        areas, rows = compare_steps(traces, block, count, cells - 1, length, rate)
        results[name] = rows
        for side in SIDES:
            checks[f'{name}/{side}/beak_areas_match_reference'] = all(
                bool((traces[side][key][block - 1:] == registered_trace[key][reference_block]).all())
                for key in area_columns)
            checks[f'{name}/{side}/inflow_replayed_bitwise'] = all(
                row['replayed'][side]['inflow'].hex() == row['observed'][side].hex() for row in rows)
        diagnosis = diagnose_difference(rows, areas, length, rate)
        first = diagnosis['first_difference']
        offset = first['offset'] if first else None
        if name == 'no_tracking':
            checks['no_tracking_quiet'] = all(flow == 0 for row in rows for flow in row['observed'].values())
        else:
            hypotheses[f'{name}/first_difference_in_6_to_12_samples'] = offset is not None and 6 <= offset <= 12
            hypotheses[f'{name}/normalized_momentum_alone_matches_upstream'] = any(
                row['inputs_from_upstream'] == ('normalized_momentum',) and row['matches_upstream']
                for row in diagnosis['term_substitutions'])
        conditions[name] = {'control_block_internal_samples': block, 'control_interval_us': block / rate * 1e6,
                            'first_difference_us': offset / rate * 1e6 if offset is not None else None, **diagnosis}
    write(out / 'terminal-branch-steps.json', results)
    reference_offset = reference['first_difference']['offset']
    return {'checks': checks, 'hypotheses': hypotheses, 'internal_sample_rate_hz': rate,
            'reference': {'internal_sample_rate_hz': reference_rate, 'first_difference_offset': reference_offset,
                          'first_difference_us': reference_offset / reference_rate * 1e6,
                          'term_substitutions': reference['term_substitutions']},
            'geometry': inspections, 'conditions': conditions}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    source, files = registered_artifacts(case['source'], 'songbird-chirps-beak-load', revision, (
        'artifacts/archived.json', 'artifacts/no-tracking.json', 'artifacts/archived-candidate.csv'))
    reference, summary = registered_artifacts(case['reference'], 'songbird-chirps-beak-tip-inflow', revision,
                                              ('summary.json',))
    inputs = [CASE, Path(__file__), PROBE, source, reference, *files.values(), *summary.values(), *candidate_sources(),
              *(WORKSPACE / 'tools' / name for name in ('measure_songbird_airway.py', 'measure_songbird_syrinx.py',
                                                       'measure_songbird_chirps_beak_load.py', 'measure_uniform_tube.py',
                                                       'measure_songbird_chirps_beak_tip_inflow.py', 'measure_speech_timing.py')),
              UPPER_NETWORK, UPPER_SONGBIRD, UPSTREAM / 'crates/chimera/src/creatures/build.rs',
              UPSTREAM / 'crates/chimera/src/creatures/voice.rs', UPSTREAM / 'crates/chimera/src/physics.rs']
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    return record_measurement(args.run_id, CASE, inputs, details,
                              lambda out, execute: compare_at_rate(case, files | summary, out, execute),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
