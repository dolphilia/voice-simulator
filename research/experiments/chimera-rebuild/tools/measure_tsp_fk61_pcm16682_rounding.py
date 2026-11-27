"""FK61_01のフレーム16682を、放射履歴からPCMの丸めまで照合する。"""

import argparse
import gzip
from itertools import combinations
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np

import measure_tsp_fk61_control4992_5120_expanded_volume_paired as previous


paired, lip, load, radiation, tsp = previous.paired, previous.lip, previous.load, previous.radiation, previous.tsp
pcm = previous.volume.pcm
CASE = radiation.WORKSPACE / 'cases/tsp-fk61-pcm16682-rounding.json'
CONDITIONS = tuple(f'{side}_{mode}' for side in previous.SIDES for mode in previous.MODES)
COMPONENTS = radiation.COMPONENTS
DC = pcm.COLUMNS.index('dc_removed')
SAVED_FILES = ('prefix.npz', 'pcm-digests.json')
ARCHIVED = {
    'indexed_upstream': ('render.npz', 'upstream-indexed-area.patch'),
    'indexed_research': ('render.npz', 'indexed-area.patch'),
    'expanded': ('upstream/render.npz', 'upstream/indexed-expanded-volume.patch',
                 'research/render.npz', 'research/indexed-expanded-volume.patch'),
}


def prepare_capture(study, patches, scratch, logs, execute, *, conditions=CONDITIONS):
    archive = scratch / 'upstream.tar'
    execute(['git', 'archive', study['upstream_revision']], cwd=radiation.UPSTREAM, stdout=archive)
    dictionary = scratch / 'dictionary.tsv'
    dictionary.write_bytes(gzip.decompress(lip.DICT.read_bytes()))
    builds = {}
    for name in conditions:
        fixed = name.startswith('upstream_')
        root = scratch / name
        root.mkdir()
        source = lip.PROBE if fixed else lip.LOCAL
        lip.copy_inputs((source, lip.TRACE_TOOL), root)
        if fixed:
            execute(['tar', '-xf', str(archive), '-C', str(root)])
        else:
            lip.copy_inputs((*radiation.candidate_sources(), lip.EMBEDDED_DICTIONARY,
                             radiation.WORKSPACE / 'data/cmudict.txt.gz',
                             radiation.WORKSPACE / 'crates/vocal-core/tests/uniform_tube.rs'), root)
        if patches is not None:
            if not fixed:
                load.patch_trial(root)
            execute(['git', 'apply', str(patches[name])], cwd=root)
        flags = ('--offline', '--target-dir', str(scratch / f'{name}-target'))
        package = 'chimera' if fixed else 'vocal-core'
        ordinary_cli = lip.build_pcm_cli(fixed, root, flags, execute)
        execute(['cargo', 'test', '--locked', '--release', '-p', package, *flags,
                 '--test', 'engine' if fixed else 'uniform_tube'], cwd=root, stdout=logs / f'{name}-tests.log')
        if fixed:
            for patch in (lip.OUTPUT_PATCH, lip.SOURCE_PATCH):
                execute(['git', 'apply', str(patch)], cwd=root)
        probe = lip.build_upstream_probe(root / source.relative_to(radiation.WORKSPACE), scratch, execute,
            upstream=root, lto='fat' if fixed else 'off', package=package, extra_libraries=('serde_json',),
            rustc_args=('--cfg', 'tsp_voice_probe') if fixed else (), cargo_args=flags)
        builds[name] = (root, ordinary_cli, probe)
    return dictionary, builds


def capture_utterance(measure, config, spec, prepared, scratch, out, execute, *,
                      filename='prefix.npz', source_fields=radiation.FIELDS):
    dictionary, builds = prepared
    count = measure['prefix_frames']
    voice = tsp.read(spec)['speech_voice']
    text, body = voice['input']['text'], voice['body']
    states, proof = {}, {}
    for name, (root, ordinary_cli, probe) in builds.items():
        fixed = name.startswith('upstream_')
        normal = lip.render_pcm_cli(fixed, ordinary_cli, root, spec, text,
                                    scratch / f'{name}.wav', measure, execute, body=body)
        trace, raw, stages = (scratch / f'{name}.{suffix}' for suffix in ('source', 'raw', 'stages'))
        if fixed:
            args = (trace, raw, scratch / f'{name}-plan.json', count, 'default', stages)
        else:
            args = (count, measure['initial_f0_hz'], config['body'][body]['base_f0_hz'], trace, raw, stages)
        execute([str(probe), str(spec), str(dictionary), *map(str, args)])
        observed = np.fromfile(raw, dtype='<f4')
        proof[name] = {'ordinary': lip.pcm_digest(normal), 'probe': lip.pcm_digest(observed),
                       'bit_equal': bool(lip.bit_equal(normal, observed))}
        source_values = pcm.read_series(trace, count * 2)
        states[f'{name}_source'] = np.column_stack([source_values[key] for key in source_fields])
        states[f'{name}_output'] = pcm.trace_input(stages, count)
        states[f'{name}_pcm'] = observed
    np.savez_compressed(out / filename, **states)
    (out / 'pcm-digests.json').write_text(json.dumps(proof, indent=2) + '\n')


def capture(study, config, spec, patches, out, execute, *, filename='prefix.npz', conditions=CONDITIONS):
    with TemporaryDirectory(prefix='fk61-pcm16682-', dir=out.parent / 'tmp') as directory:
        scratch = Path(directory)
        prepared = prepare_capture(study, patches, scratch, out, execute, conditions=conditions)
        capture_utterance(study['measurement'], config, spec, prepared, scratch, out, execute, filename=filename)


def archived_paths(files):
    return {
        'upstream_indexed': files['indexed_upstream'][0],
        'research_indexed': files['indexed_research'][0],
        'upstream_expanded': files['expanded'][0],
        'research_expanded': files['expanded'][2],
    }


def patch_paths(files):
    return {'upstream_indexed': files['indexed_upstream'][1], 'research_indexed': files['indexed_research'][1],
            'upstream_expanded': files['expanded'][1], 'research_expanded': files['expanded'][3]}


def capture_dependencies():
    ws, upper = radiation.WORKSPACE, radiation.UPSTREAM
    return [Path(__file__).resolve(), *radiation.candidate_sources(),
            *(Path(module.__file__) for module in (previous, paired, lip, load, load.bernstein,
                                                   load.bernstein.ray, radiation, pcm)),
            lip.DICT, lip.LOCAL, lip.PROBE, lip.TRACE_TOOL, lip.OUTPUT_PATCH, lip.SOURCE_PATCH, lip.EMBEDDED_DICTIONARY,
            ws / 'data/cmudict.txt.gz', ws / 'crates/vocal-core/tests/uniform_tube.rs',
            *(upper / name for name in ('Cargo.lock', paired.NETWORK, 'crates/chimera/src/airway/decimator.rs',
                'crates/chimera/src/voice/human_voice.rs', 'crates/chimera-cli/src/render.rs',
                'crates/chimera/tests/engine.rs'))]


def archived_matches(current, proof, archives, measure):
    result = {}
    for name, path in archives.items():
        mode = name.split('_', maxsplit=1)[1]
        with np.load(path, allow_pickle=False) as saved:
            native = proof[name]
            samples = current[f'{name}_pcm']
            source = current[f'{name}_source']
            output = current[f'{name}_output']
            result[name] = {
                'pcm': native['bit_equal'] and native['ordinary'] == native['probe'] == lip.pcm_digest(samples)
                    and len(samples) == measure['frames'] and lip.bit_equal(samples, saved[f'{mode}_pcm']),
                'previous_source': load.same_bits(source[:len(saved[f'{mode}_source'])], saved[f'{mode}_source']),
                'previous_output': load.same_bits(output[:len(saved[f'{mode}_output'])], saved[f'{mode}_output']),
                'mouth_through_window': load.same_bits(
                    source[:, radiation.FIELDS.index('lip_cm3_s')], saved[f'{mode}_mouth'][:len(source)]),
            }
    return result


def swaps(frame, states, current, coefficients, gain, config, midpoint):
    results = {}
    for side in previous.SIDES:
        fixed = side == 'upstream'
        coeff = coefficients['upstream' if fixed else 'candidate']
        rate = config['internal_sample_rate_hz']
        for src, dst in (previous.MODES, previous.MODES[::-1]):
            source, target = (f'{side}_{mode}' for mode in (src, dst))
            attempts = []
            for fields in (keys for n in range(1, len(COMPONENTS) + 1) for keys in combinations(COMPONENTS, n)):
                flow = {key: states[source if key in fields else target][key] for key in COMPONENTS}
                _, derivative = radiation.radiation_from_components(flow, rate, fixed)
                replay, samples = pcm.replay(derivative, coeff, gain, config)
                value = float(replay[frame, DC - 2])
                attempts.append({
                    'components': list(fields), 'precast': value, 'from_midpoint': value - midpoint,
                    'pcm_at_frame': float(samples[frame]),
                    'pcm_at_frame_matches_target': bool(samples[frame] == current[f'{target}_pcm'][frame]),
                    'pcm_at_frame_matches_source': bool(samples[frame] == current[f'{source}_pcm'][frame]),
                    'pcm_through_window_matches_source': bool(lip.bit_equal(current[f'{source}_pcm'][:len(samples)], samples)),
                    'output_chain_matches_source': load.same_bits(current[f'{source}_output'][:, 2:], replay),
                })
            results[f'{target}<-{source}'] = attempts
    return results


def stages_at_difference(states, current, coefficients, gain, config, frame, side):
    fixed = side == 'upstream'
    rate = config['internal_sample_rate_hz']
    names = [f'{side}_{mode}' for mode in previous.MODES]
    before, after = (states[name] for name in names)
    old, new = (current[f'{name}_output'] for name in names)
    measured = float(new[frame, DC] - old[frame, DC])
    coeff = coefficients['upstream' if fixed else 'candidate']
    response = {}
    for key in (*COMPONENTS, radiation.RADIATION):
        delta = after[key] - before[key]
        if key in COMPONENTS:
            delta = np.diff(delta, prepend=0.0) * rate
        stages, _ = pcm.replay(delta, coeff, gain, config)
        response[key] = float(stages[frame, DC - 2])
    return {
        'first_source_changes': {key: paired.metrics(before[key], after[key])['first']
                                 for key in (*COMPONENTS, 'total_cm3_s', radiation.RADIATION)},
        'first_output_changes': {key: paired.metrics(old[:, i], new[:, i])['first']
                                 for i, key in enumerate(pcm.COLUMNS[2:], start=2)},
        'linear_response_to_difference': response,
        'measured_precast_shift': measured,
        'measured_minus_linear_radiation_response': measured - response[radiation.RADIATION],
        'linear_radiation_minus_sum_of_component_responses': response[radiation.RADIATION]
            - sum(response[key] for key in COMPONENTS),
    }


def exact_output_replays(current, states, measure, config, gain, coefficients, *, conditions=CONDITIONS):
    count = measure['prefix_frames']
    output_check = {}
    for name in conditions:
        fixed = name.startswith('upstream_')
        source = states[name]
        output, samples = (current[f'{name}_{key}'] for key in ('output', 'pcm'))
        total, derivative = radiation.radiation_from_components(source, measure['internal_sample_rate_hz'], fixed)
        c = coefficients['upstream' if fixed else 'candidate']
        replay, independent_pcm = pcm.replay(derivative, c, gain, config)
        output_check[name] = (
            len(derivative) == count * 2 and len(output) == count
            and all(np.isfinite(values).all() for values in (output, samples, *source.values()))
            and load.same_bits(total, source['total_cm3_s'])
            and load.same_bits(derivative, source[radiation.RADIATION])
            and load.same_bits(derivative, output[:, :2].ravel()) and load.same_bits(replay, output[:, 2:])
            and lip.bit_equal(independent_pcm, samples[:count]))
    return output_check


def analyze(study, out, archives, config, gain, coefficients):
    measure = study['measurement']
    frame = measure['focus_frame']
    with np.load(out / 'prefix.npz', allow_pickle=False) as captured:
        current = dict(captured)
    states = {name: dict(zip(radiation.FIELDS, current[f'{name}_source'].T, strict=True)) for name in CONDITIONS}
    proof = tsp.read(out / 'pcm-digests.json')
    archived = archived_matches(current, proof, archives, measure)
    output_check = exact_output_replays(current, states, measure, config, gain, coefficients)
    levels = {name: float(current[f'{name}_pcm'][frame]) for name in CONDITIONS}
    low, high = min(levels.values()), max(levels.values())
    midpoint = (low + high) / 2
    precast = {name: float(current[f'{name}_output'][frame, DC]) for name in CONDITIONS}
    offsets = {name: value - midpoint for name, value in precast.items()}
    interventions = swaps(frame, states, current, coefficients, gain, config, midpoint)
    up = [rows for key, rows in interventions.items() if key.startswith('upstream_')]
    selected = lambda rows, *fields: next(row for row in rows if set(row['components']) == set(fields))
    hypotheses = {
        'only_upstream_indexed_below_16682_midpoint': offsets['upstream_indexed'] < 0
            and all(value > 0 for name, value in offsets.items() if name != 'upstream_indexed'),
        'upstream_mouth_alone_switches_pcm_in_both_directions': all(
            selected(rows, 'lip_cm3_s')['pcm_at_frame_matches_source']
            and not selected(rows, 'lip_cm3_s')['pcm_at_frame_matches_target'] for rows in up),
        'upstream_wall_and_nose_without_mouth_do_not_switch_pcm': all(
            selected(rows, 'wall_cm3_s', 'nose_cm3_s')['pcm_at_frame_matches_target'] for rows in up),
    }
    checks = {
        'normal_probes_archived_full_pcm_and_prefix_match': all(
            passed for row in archived.values() for passed in row.values()),
        'radiation_fir_dc_envelope_and_pcm_exact': all(output_check.values()),
        'adjacent_pcm_values_reproduced_by_precast': low != high
            and bool(np.nextafter(np.float32(low), np.float32(high)) == np.float32(high))
            and all(float(np.float32(value)) == levels[key] for key, value in precast.items()),
        'all_component_swaps_reconstruct_donor': all(rows[-1]['pcm_through_window_matches_source']
            and rows[-1]['output_chain_matches_source'] for rows in interventions.values()),
    }
    return {
        'checks': checks, 'hypotheses': hypotheses, 'archive_matches': archived, 'output_replay': output_check,
        'rounding': {'frame': frame, 'midpoint': midpoint, 'pcm_spacing': high - low, 'pcm': levels,
                     'precast': precast, 'from_midpoint': offsets},
        'max_envelope': {name: float(np.max(current[f'{name}_output'][:, pcm.COLUMNS.index('envelope')]))
                         for name in CONDITIONS},
        'stage_differences': {side: stages_at_difference(states, current, coefficients, gain, config, frame, side)
                              for side in previous.SIDES},
        'component_swaps': interventions,
        'local_frames': [{
            'frame': n,
            'stages': {name: dict(zip(pcm.COLUMNS, current[f'{name}_output'][n].tolist(), strict=True))
                       for name in CONDITIONS},
            'pcm': {name: float(current[f'{name}_pcm'][n]) for name in CONDITIONS},
        } for n in range(*measure['local_frames'])],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    ws, upper = radiation.WORKSPACE, radiation.UPSTREAM
    study = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=upper, text=True).strip()
    if revision != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=upper):
        parser.error('変更のない固定上流版が必要です')
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('試験ビルドにCHIMERA_RUN_STORAGE=rtl9210bを指定してください')
    runs = {key: tsp.open_run(study[key], revision) for key in ('matched', 'coefficients', *ARCHIVED)}
    uid = study['measurement']['recording_id']
    spec = tsp.verified_path(runs['matched'], f'artifacts/{uid}/matched-case.json')
    config, config_path = radiation.saved_case(runs['matched'], lip.CONFIG)
    coeff = tsp.verified_path(runs['coefficients'], 'artifacts/coefficients.json')
    files = {key: [tsp.verified_path(runs[key], f'artifacts/{name}') for name in names]
             for key, names in ARCHIVED.items()}
    patches = patch_paths(files)
    inputs = [CASE, spec, config_path, coeff, *capture_dependencies(),
              *(run[0] / 'manifest.json' for run in runs.values()), *(path for paths in files.values() for path in paths)]

    def measure(out, execute):
        capture(study, config, spec, patches, out, execute)
        gain = tsp.read(spec)['speech_voice']['voice']['output_gain']
        return analyze(study, out, archived_paths(files), config, gain, tsp.read(coeff))

    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return radiation.record_measurement(args.run_id, CASE, inputs, details, measure, command=None, input_root=ws.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
