"""鳴禽の短区間で揃えた気道を、全コールの通常PCM描画で比較する。"""

import argparse
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

import numpy as np

from measure_songbird_chirps_beak_inlet_half_inertance_44100 import CASE as PATCH_CASE, LABEL as LAST_PATCH
from measure_songbird_chirps_beak_load import ROOT
from measure_songbird_chirps_beak_tip_inflow_44100 import registered_artifacts
from measure_songbird_chirps_right_syrinx_half_inertance_44100 import restore_patches
from measure_songbird_chirps_volume_rate_propagation_44100 import stage_candidate
from measure_songbird_flute import CALL_FIELDS, bit_difference, trace
from measure_songbird_sustain_pcm import FIELDS, PARAMS, fir_tolerance, independent_output, internal, waveform
from measure_speech_timing import read
from measure_uniform_tube import candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/songbird-chirps-full-pcm-44100.json'
CALL_CASE = WORKSPACE / 'cases/songbird-calls.json'
SUSTAIN_CASE = WORKSPACE / 'cases/songbird-sustain-pcm.json'
PROBE = WORKSPACE / 'tools/upstream_songbird_voice_probe.rs'
STAGES = ('radiation_internal', 'decimated', 'dc_removed', 'pcm_f32')


def render_variants(case_path, blocks, patches, snapshot, sources, out, execute):
    products, builds, block_traces = {}, {}, {}
    with TemporaryDirectory(prefix='chirps-full-pcm-', dir=out.parent) as temporary:
        root = Path(temporary)
        workspace = root / 'candidate'
        target = root / 'target'
        stage_candidate(snapshot, sources, workspace)
        for label, patch_list in (('standard', ()), ('experiment', patches)):
            for patch in patch_list:
                execute(['git', 'apply', '--check', str(patch)], cwd=workspace)
                execute(['git', 'apply', str(patch)], cwd=workspace)
            execute(['cargo', 'build', '--release', '--locked', '--offline', '-p', 'vocal-cli',
                     '--manifest-path', str(workspace / 'Cargo.toml'), '--target-dir', str(target)])
            cli = target / 'release/vocal-cli'
            builds[label] = sha256(cli)
            products[label] = {key: out / f'{label}-{suffix}' for key, suffix in (
                ('settings', 'settings.json'), ('trace', 'trace.csv'), ('wave', f'{blocks[0]}.wav'),
                ('second_wave', f'{blocks[1]}.wav'))}
            paths = products[label]
            execute([str(cli), 'inspect', str(case_path)], stdout=paths['settings'])
            execute([str(cli), 'render-pcm', str(case_path), str(paths['wave']), str(paths['trace']), str(blocks[0])])
            second_trace = root / f'{label}-{blocks[1]}.csv'
            execute([str(cli), 'render-pcm', str(case_path), str(paths['second_wave']), str(second_trace), str(blocks[1])])
            block_traces[label] = {'sha256': sha256(second_trace), 'bytes': second_trace.stat().st_size}
            if block_traces[label]['sha256'] != sha256(paths['trace']):
                second_trace.replace(out / second_trace.name)
    return products, builds, block_traces


def statistics(left, right, tolerance, start=0):
    bits = np.dtype(f'u{left.dtype.itemsize}')
    indices = np.flatnonzero(left.view(bits) != right.view(bits))
    errors = left.astype(np.float64) - right
    over = np.flatnonzero(np.abs(errors) > tolerance)
    first = int(indices[0]) if indices.size else None
    return {
        'first_bit_difference': start + first if first is not None else None,
        'first_values': [float(left[first]), float(right[first])] if first is not None else None,
        'bit_difference_count': int(indices.size),
        'first_over_tolerance': start + int(over[0]) if over.size else None,
        'max_abs_error': float(np.max(np.abs(errors))),
        'rms_error': float(np.sqrt(np.mean(errors * errors))),
        'compared_samples': len(left),
    }


def compare_stages(left, right, case, factor):
    config = case['limits']
    tolerances = {
        'radiation_internal': (np.max(np.abs(right['radiation_internal'])) * config['acoustic_peak_relative_tolerance']
                               + config['acoustic_absolute_floor']),
        'decimated': fir_tolerance(right['decimated'], config),
        'dc_removed': config['dc_absolute_tolerance'],
        'pcm_f32': config['pcm_absolute_tolerance'],
    }
    result = {}
    for stage in STAGES:
        scale = factor if stage == 'radiation_internal' else 1
        tolerance = float(tolerances[stage])
        windows = {}
        for name, (first, last) in case['windows_frames'].items():
            start, stop = first * scale, last * scale
            windows[name] = statistics(left[stage][start:stop], right[stage][start:stop], tolerance, start)
        result[stage] = {'tolerance': tolerance, 'total': statistics(left[stage], right[stage], tolerance),
                         'windows': windows}
    return result


def stages(data, factor):
    return {'radiation_internal': internal(data, factor), 'decimated': data['decimated'],
            'dc_removed': data['dc_removed'], 'pcm_f32': data['pcm_f32'].astype(np.float32)}


def measure(case, settings, archived, config, expected_binary, patches, snapshot, sources, out, execute):
    blocks, frames = case['host_block_frames'], case['frames']
    paths, binaries, block_traces = render_variants(archived['case.json'], blocks, patches, snapshot, sources, out, execute)
    factor = case['sample_rate_hz'] // case['output_rate_hz']
    limits = case['limits']
    fields = (*FIELDS, *CALL_FIELDS)
    traces = {label: trace(files['trace'], frames, (*fields, 'gate_target', 'call_id'))
              for label, files in paths.items()}
    traces['upstream'] = trace(archived['upstream.csv'], frames, (*fields, 'call_id'))
    signals = {label: stages(data, factor) for label, data in traces.items()}
    checks = {
        'standard_trace_reproduced': sha256(paths['standard']['trace']) == sha256(archived[f'pcm-{blocks[0]}.csv']),
        'standard_wave_reproduced': sha256(paths['standard']['wave']) == sha256(archived[f'pcm-{blocks[0]}.wav']),
        'experiment_binary_reproduced': binaries['experiment'] == expected_binary,
        'experiment_binary_differs': binaries['standard'] != binaries['experiment'],
    }
    for label, files in paths.items():
        metadata = read(files['settings'])
        checks[f'{label}/layout'] = (
            metadata['songbird_voice'] == settings
            and (metadata['internal_rate_hz'], metadata['decimation_factor'], metadata['control_frames'],
                 metadata['filter_taps']) == (case['sample_rate_hz'], factor, case['control_frames'], 24 * factor + 1))
        checks[f'{label}/pcm_wave_and_trace'] = bit_difference(
            waveform(files['wave'], settings), signals[label]['pcm_f32']) == 0
        checks[f'{label}/block_split_wave'] = sha256(files['wave']) == sha256(files['second_wave'])
        checks[f'{label}/block_split_trace'] = (
            block_traces[label]['bytes'] == files['trace'].stat().st_size
            and block_traces[label]['sha256'] == sha256(files['trace']))

    control_columns = ('frame', 'internal_sample', 'call_id', *CALL_FIELDS, *PARAMS,
                       'gate', 'sac_pressure_dyn_cm2', 'left_opening', 'right_opening')
    checks['controls_unchanged'] = all(
        np.array_equal(traces['standard'][field].view(np.uint64), traces['experiment'][field].view(np.uint64))
        for field in (*control_columns, 'gate_target'))
    checkpoints, independent = {}, {}
    no_change = case['windows_frames']['before_control_change'][1]
    for label, data in traces.items():
        pcm = signals[label]['pcm_f32']
        transitions = np.flatnonzero(np.diff(data['call_id'], prepend=0))
        events = [[int(index), int(data['call_id'][index])] for index in transitions]
        breath = np.flatnonzero(data['gate'] > 0)
        start_breath = int(breath[0]) if breath.size else None
        checkpoints[label] = {'call_transitions': events, 'first_breath_frame': start_breath,
                              'peak_pcm': float(np.max(np.abs(pcm)))}
        checks[f'{label}/timing'] = (
            np.array_equal(data['frame'], np.arange(frames))
            and np.array_equal(data['internal_sample'], np.arange(1, frames + 1) * factor - 1)
            and events == case['expected_call_transitions'] and start_breath == case['expected_breath_start_frame'])
        checks[f'{label}/silent_before_control_update'] = bool(
            not np.any(pcm[:no_change]) and not np.any(signals[label]['radiation_internal'][:no_change * factor]))
        checks[f'{label}/finite_bounded_signal'] = bool(limits['minimum_pcm_peak'] <= checkpoints[label]['peak_pcm'] <= 1)
        reference = independent_output(signals[label]['radiation_internal'], settings, factor, config)
        tolerances = (fir_tolerance(reference['decimated'], config), limits['dc_absolute_tolerance'],
                      limits['pcm_absolute_tolerance'])
        independent[label] = {}
        for stage, tolerance in zip(STAGES[1:], tolerances, strict=True):
            report = statistics(signals[label][stage], reference[stage], tolerance)
            independent[label][stage] = report
            checks[f'{label}/independent/{stage}'] = report['first_over_tolerance'] is None
    upper = traces['upstream']
    for field in control_columns:
        tolerance = (limits['clock_absolute_tolerance_seconds'] if field == 'control_clock_seconds'
                     else limits['control_and_target_absolute_tolerance'])
        checks[f'upstream_control/{field}'] = bool(np.all(np.abs(traces['experiment'][field] - upper[field]) <= tolerance))
    results = {f'{left}_vs_{right}': compare_stages(signals[left], signals[right], case, factor)
               for left, right in (('standard', 'upstream'), ('experiment', 'upstream'), ('experiment', 'standard'))}
    for name, comparison in results.items():
        checks[f'{name}/within_registered_tolerances'] = all(
            stage['total']['first_over_tolerance'] is None for stage in comparison.values())
    first_standard = results['standard_vs_upstream']['radiation_internal']['total']['first_bit_difference']
    first_experiment = results['experiment_vs_upstream']['radiation_internal']['total']['first_bit_difference']
    pcm_differences = results['experiment_vs_upstream']['pcm_f32']['total']['bit_difference_count']
    effect = results['experiment_vs_standard']
    raw_first = effect['radiation_internal']['total']['first_bit_difference']
    checks['archived_first_radiation_difference_reproduced'] = first_standard == case['archived_first_upstream_radiation_difference']
    checks['experiment_effect_starts_at_radiation'] = all(
        stage['total']['first_bit_difference'] is None
        or (raw_first is not None and stage['total']['first_bit_difference'] >= raw_first // factor)
        for name, stage in effect.items() if name != 'radiation_internal')
    hypotheses = {
        'first_radiation_difference_delayed':
            first_standard is not None and (first_experiment is None or first_experiment > first_standard),
        'pcm_bit_exact': pcm_differences == 0,
    }
    return {'checks': checks, 'hypotheses': hypotheses, 'binaries': binaries, 'frames': frames,
            'alternate_block_trace': block_traces,
            'internal_samples': frames * factor, 'checkpoints': checkpoints, 'comparisons': results,
            'independent_recalculation': independent}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case, patch_case, call_case, sustain = (read(path) for path in (CASE, PATCH_CASE, CALL_CASE, SUSTAIN_CASE))
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if (revision != case['upstream_revision'] or revision != patch_case['upstream_revision']
            or revision != call_case['upstream_revision']
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM)):
        parser.error('変更のない固定上流版が必要です')
    limits = case['limits']
    config = sustain['measurement']
    if any(value != call_case['measurement'].get(key, config.get(key)) for key, value in limits.items()):
        parser.error('全コールの既存許容差と一致しません')
    patch_manifest, patch_files = registered_artifacts(
        case['patch_reference'], patch_case['id'], revision, ('summary.json', f'artifacts/{LAST_PATCH}.patch'))
    patches = restore_patches(read(patch_manifest), patch_files, LAST_PATCH)
    if len(patches) != case['patch_reference']['patch_count']:
        parser.error('登録された数の差分が必要です')
    call_ref = case['call_reference']
    prefix = f'artifacts/{call_ref["variant"]}/'
    block = case['host_block_frames'][0]
    names = ('case.json', 'upstream.csv', f'pcm-{block}.csv', f'pcm-{block}.wav')
    call_manifest, references = registered_artifacts(case['call_reference'], call_ref['case_id'], revision,
                                                     tuple(prefix + name for name in names))
    archived = {name: references[prefix + name] for name in names}
    settings = read(archived['case.json'])['songbird_voice']
    variant, = (entry['overrides'] for entry in call_case['measurement']['variants'] if entry['id'] == call_ref['variant'])
    if ((settings['sample_rate_hz'], settings['frames']) != (case['output_rate_hz'], case['frames'])
            or settings != (call_case['songbird_voice'] | variant)):
        parser.error('保存した全コールの制御ケースが事前登録と一致しません')
    sources = [*candidate_sources(), WORKSPACE / 'data/cmudict.txt.gz', WORKSPACE / 'data/mandarin.txt.gz']
    tool_names = ('measure_songbird_chirps_beak_tip_inflow_44100', 'measure_songbird_chirps_right_syrinx_half_inertance_44100',
                  'measure_songbird_chirps_volume_rate_propagation_44100', 'measure_songbird_flute',
                  'measure_songbird_sustain_pcm', 'measure_songbird_syrinx',
                  'measure_speech_timing', 'measure_uniform_tube', 'upstream_baseline')
    tools = [WORKSPACE / f'tools/{name}.py' for name in tool_names]
    upstream_sources = [UPSTREAM / file for file in ('crates/chimera/src/creatures/voice.rs',
                        'crates/chimera/src/creatures/songbird.rs', 'crates/chimera/src/airway/network.rs',
                        'crates/chimera/src/airway/decimator.rs')]
    inputs = [CASE, PATCH_CASE, CALL_CASE, SUSTAIN_CASE, PROBE, Path(__file__).resolve(), patch_manifest, call_manifest,
              *patch_files.values(), *patches, *archived.values(), *tools, *upstream_sources, *sources]
    expected_binary = read(patch_files['summary.json'])['build']['experimental_binary_sha256']
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    snapshot = WORKSPACE / 'runs' / args.run_id / 'artifacts/source'
    return record_measurement(args.run_id, CASE, inputs, details,
        lambda out, execute: measure(case, settings, archived, config, expected_binary, patches, snapshot, sources, out, execute),
        command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
