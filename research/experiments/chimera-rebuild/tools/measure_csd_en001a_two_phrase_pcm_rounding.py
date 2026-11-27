"""同設定のCSD先頭2句を、内部放射からPCMの丸めまで照合する。"""

import argparse
from difflib import unified_diff
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np

import measure_csd_continuous_song as song
import measure_tsp_fk61_02_full_pcm_rounding as matched_pcm
from tsp_fk61_lip_observation import edit, insert_before


full, prefix, lip, radiation, tsp, pcm = (matched_pcm.full, matched_pcm.prefix, matched_pcm.lip,
                                         matched_pcm.radiation, matched_pcm.tsp, matched_pcm.pcm)
CASE = radiation.WORKSPACE / 'cases/csd-en001a-two-phrase-pcm-rounding.json'
CONDITIONS = matched_pcm.CONDITIONS
SAVED_FILES = ('output-trace.npz', 'pcm-digests.json', 'upstream-observation.patch', 'research-observation.patch',
               'upstream-plan.json', 'research-plan.json')
REFERENCE_FILES = ('candidate-short-128.json', 'candidate-short-128.wav', 'candidate-inspect.json',
                   'matched.f32', 'matched.json')
RESEARCH = 'crates/vocal-cli/src/timing_case/speech_voice.rs'
SOURCE_FIELDS = ('pressure_drop_dyn_cm2', 'phase', 'glottal_area_cm2', 'glottal_flow_cm3_s',
                 'lip_cm3_s', 'nose_cm3_s', 'wall_cm3_s', 'total_cm3_s', radiation.RADIATION)
UPSTREAM_CONTROL_OUTPUT_FRAMES = 64
UPSTREAM_TINY = 1e-30


def diff(original, path, name):
    return ''.join(unified_diff(original.splitlines(keepends=True), path.read_text().splitlines(keepends=True),
                               fromfile=f'a/{name}', tofile=f'b/{name}'))


def patch_upstream(path):
    original = path.read_text()
    edit(path, '    let [case, mode, samples, trace, score] = args.as_slice() else {',
         '    let [case, mode, samples, trace, score, source_path, output_path] = args.as_slice() else {')
    insert_before(path, '    let mut one = [0.0f32];', '''    let mut source_trace = BufWriter::new(File::create_new(source_path)?);
    let mut output_trace = BufWriter::new(File::create_new(output_path)?);
''')
    fields = ', '.join(str(radiation.FIELDS.index(key)) for key in SOURCE_FIELDS)
    insert_before(path, '        pcm.write_all(&one[0].to_le_bytes())?;', f'''        for row in &voice.probe_source_pair {{
            for index in [{fields}] {{
                source_trace.write_all(&row[index].to_le_bytes())?;
            }}
        }}
        for value in voice.probe_radiation_pair.into_iter().chain(voice.probe_output) {{
            output_trace.write_all(&value.to_le_bytes())?;
        }}
''')
    insert_before(path, '    pcm.flush()?;', '    source_trace.flush()?;\n    output_trace.flush()?;\n')
    return diff(original, path, 'tools/' + song.PROBE.name)


def patch_research(path):
    original = path.read_text()
    anchor = '''            pcm::write(
                || {
                    step_audio(&mut voice, &mut pattern)
                        .map(|s| s.radiation.radiation_flow_derivative_cm3_s2)
                },
                stage,
                output_rate,
                samples,
                block_frames,
                wave,
                trace,
            )'''
    edit(path, anchor, '''            let mut observation = std::env::var_os("CHIMERA_CSD_SOURCE_TRACE")
                .map(File::create_new)
                .transpose()?
                .map(BufWriter::new);
            pcm::write(
                || {
                    let sample = step_audio(&mut voice, &mut pattern)?;
                    let radiation = sample.radiation;
                    if let Some(output) = &mut observation {
                        for value in [
                            sample.glottal_input_pressure_dyn_cm2,
                            sample.glottis.phase,
                            sample.glottis.area_cm2,
                            sample.glottal_flow_cm3_s,
                            sample.lip_flow_cm3_s,
                            sample.nose_flow_cm3_s,
                            radiation.wall_radiation_flow_cm3_s,
                            radiation.radiation_flow_cm3_s,
                            radiation.radiation_flow_derivative_cm3_s2,
                        ] {
                            output.write_all(&value.to_le_bytes())
                                .map_err(|_| "内部の放射系列を書き出せません")?;
                        }
                    }
                    Ok(radiation.radiation_flow_derivative_cm3_s2)
                },
                stage,
                output_rate,
                samples,
                block_frames,
                wave,
                trace,
            )?;
            if let Some(mut output) = observation {
                output.flush()?;
            }
            Ok(())''')
    return diff(original, path, RESEARCH)


def source_trace(path, count):
    rows = np.fromfile(path, dtype='<f8').reshape(-1, len(SOURCE_FIELDS))
    if len(rows) != 2 * count or not np.isfinite(rows).all():
        raise ValueError(f'内部観測の長さまたは値が不正です ({path.name})')
    return rows


def capture(study, spec, out, execute, *, capture_standard=False):
    m = study['measurement']
    count, rate = m['frames'], m['sample_rate_hz']
    gain = tsp.read(spec)['song_voice']['voice']['output_gain']
    observations, proof = {}, {}
    with TemporaryDirectory(prefix='csd-two-phrase-rounding-', dir=out.parent / 'tmp') as directory:
        scratch = Path(directory)
        upper, research = (scratch / name for name in CONDITIONS)
        upper.mkdir()
        research.mkdir()
        archive = scratch / 'upper.tar'
        execute(['git', 'archive', study['upstream_revision']], cwd=radiation.UPSTREAM, stdout=archive)
        execute(['tar', '-xf', str(archive), '-C', str(upper)])
        upper_flags = ('--offline', '--target-dir', str(scratch / 'upper-target'))
        execute(['cargo', 'test', '--locked', '--release', *upper_flags, '-p', 'chimera',
                 '--test', 'sing_fast', '--test', 'sung_release', '--test', 'denormals'],
                cwd=upper, stdout=out / 'upper-tests.log')
        stock = lip.build_upstream_probe(song.PROBE, scratch, execute, upstream=upper, cargo_args=upper_flags,
                                        extra_libraries=('serde_json',))
        normal, plain_plan = scratch / 'upstream-normal.f32', scratch / 'upstream-normal.json'
        execute([str(stock), str(spec), 'matched', str(normal), str(scratch / 'upper-normal.csv'), str(plain_plan)])
        normal_upper = np.fromfile(normal, dtype='<f4')
        if capture_standard:
            standard_audio, standard_state, standard_plan = (scratch / f'upper-standard.{kind}'
                                                              for kind in ('f32', 'csv', 'json'))
            execute([str(stock), str(spec), 'standard', str(standard_audio), str(standard_state), str(standard_plan)])
            standard = np.fromfile(standard_audio, dtype='<f4')
            observations['upstream_standard_pcm'] = standard
            proof['upstream_standard'] = {'pcm': lip.pcm_digest(standard),
                                          'plan_matches': tsp.read(plain_plan) == tsp.read(standard_plan)}
            standard_state.unlink()
        for patch in (lip.OUTPUT_PATCH, lip.SOURCE_PATCH):
            execute(['git', 'apply', str(patch)], cwd=upper)
        up_source = scratch / 'upstream_csd_rounding_probe.rs'
        up_source.write_bytes(song.PROBE.read_bytes())
        (out / 'upstream-observation.patch').write_text(patch_upstream(up_source))
        probe = lip.build_upstream_probe(up_source, scratch, execute, upstream=upper, cargo_args=upper_flags,
                                        extra_libraries=('serde_json',))
        measured, source, output = (scratch / f'upstream-probe.{ext}' for ext in ('f32', 'source', 'output'))
        up_plan = out / 'upstream-plan.json'
        execute([str(probe), str(spec), 'matched', str(measured), str(scratch / 'upper-probe.csv'),
                 str(up_plan), str(source), str(output)])
        up_pcm = np.fromfile(measured, dtype='<f4')
        observations.update(upstream_normal_pcm=up_pcm, upstream_normal_source=source_trace(source, count),
                            upstream_normal_output=pcm.trace_input(output, count))
        proof['upstream_normal'] = {'ordinary': lip.pcm_digest(normal_upper), 'observed': lip.pcm_digest(up_pcm),
                                    'plan_matches': tsp.read(plain_plan) == tsp.read(up_plan)}

        lip.copy_inputs((*radiation.candidate_sources(), lip.EMBEDDED_DICTIONARY,
                         radiation.WORKSPACE / 'data/cmudict.txt.gz',
                         radiation.WORKSPACE / 'crates/vocal-core/tests/uniform_tube.rs'), research)
        flags = ('--offline', '--target-dir', str(scratch / 'research-target'))
        execute(['cargo', 'test', '--locked', '--release', *flags, '-p', 'vocal-core', '--test', 'uniform_tube'],
                cwd=research, stdout=out / 'research-tests.log')
        cli = lip.build_pcm_cli(False, research, flags, execute)
        unobserved_wave, unobserved_plan = (scratch / name for name in ('research-normal.wav', 'research-normal.json'))
        frames = str(m['block_frames'])
        execute([str(cli), 'render-pcm', str(spec), str(unobserved_wave), '--no-trace', frames])
        execute([str(cli), 'inspect', str(spec)], stdout=unobserved_plan)
        (out / 'research-observation.patch').write_text(patch_research(research / RESEARCH))
        cli = lip.build_pcm_cli(False, research, flags, execute)
        source, trace, wave = (scratch / f'research-probe.{ext}' for ext in ('source', 'csv', 'wav'))
        execute(['env', f'CHIMERA_CSD_SOURCE_TRACE={source}', str(cli), 'render-pcm', str(spec),
                 str(wave), str(trace), frames])
        research_plan = out / 'research-plan.json'
        execute([str(cli), 'inspect', str(spec)], stdout=research_plan)
        stock_pcm = song.samples(unobserved_wave, rate, count)
        research_pcm = song.samples(wave, rate, count)
        source = source_trace(source, count)
        fields = ('frame', 'internal_sample', 'decimated', 'dc_removed', 'limiter_envelope', 'hold_frames', 'pcm_f32')
        rows = song.state(trace, fields, count)
        if not np.array_equal(rows['internal_sample'], np.arange(1, count * 2, 2)):
            raise ValueError('研究版の出力と内部標本の対応が不正です')
        dec = rows['decimated']
        derivatives = source[:, SOURCE_FIELDS.index(radiation.RADIATION)].reshape(count, 2)
        levels = np.column_stack((derivatives, dec, dec * gain, rows['dc_removed'],
                                  rows['limiter_envelope'], rows['hold_frames']))
        observations.update(research_normal_pcm=research_pcm, research_normal_source=source, research_normal_output=levels)
        proof['research_normal'] = {'ordinary': lip.pcm_digest(stock_pcm), 'observed': lip.pcm_digest(research_pcm),
                                     'plan_matches': tsp.read(unobserved_plan) == tsp.read(research_plan),
                                     'csv_pcm_matches': bool(lip.bit_equal(rows['pcm_f32'].astype('<f4'), research_pcm))}
    np.savez_compressed(out / SAVED_FILES[0], **observations)
    (out / SAVED_FILES[1]).write_text(json.dumps(proof, indent=2) + '\n')


def replay_output(current, states, measure, config, gain, coefficients, *, output_limiter=False):
    count = measure['frames']
    internal_rate = measure['internal_sample_rate_hz']
    control = UPSTREAM_CONTROL_OUTPUT_FRAMES * (internal_rate // measure['sample_rate_hz'])
    result = {}
    for name, mode in zip(CONDITIONS, ('upstream', 'candidate'), strict=True):
        source = states[name]
        output, samples = (current[f'{name}_{key}'] for key in ('output', 'pcm'))
        upper = mode == 'upstream'
        total, derivative = radiation.radiation_from_components(source, internal_rate, upper)
        if upper:
            previous = total[control - 1:-1:control]
            derivative[control::control] = (total[control::control]
                                          - np.where(np.abs(previous) < UPSTREAM_TINY, 0.0, previous)) * internal_rate
        state_trim = (control, UPSTREAM_TINY) if upper else None
        replayed, independent_pcm = pcm.replay(derivative, coefficients[mode], gain, config, state_trim=state_trim,
                                               output_limiter=output_limiter)
        same = prefix.load.same_bits
        result[name] = {
            'length_and_finiteness': len(derivative) == count * 2 and len(output) == count and len(samples) == count
            and all(np.isfinite(values).all() for values in (output, samples, *source.values())),
            'radiation_sum': same(total, source['total_cm3_s']),
            'radiation_derivative': same(derivative, source[radiation.RADIATION])
            and same(derivative, output[:, :2].ravel()),
            **{field: same(replayed[:, i], output[:, i + 2]) for i, field in enumerate(pcm.COLUMNS[2:])},
            'float32_pcm': lip.bit_equal(independent_pcm, samples),
        }
    return result


def analyze(study, out, reference, config, coefficients):
    m = study['measurement']
    gain = tsp.read(reference['candidate-short-128.json'])['song_voice']['voice']['output_gain']
    with np.load(out / SAVED_FILES[0], allow_pickle=False) as saved:
        current = dict(saved)
    states = {name: dict(zip(SOURCE_FIELDS, current[f'{name}_source'].T, strict=True)) for name in CONDITIONS}
    replay = replay_output(current, states, m, config, gain, coefficients)
    proof = tsp.read(out / SAVED_FILES[1])
    upper, research = (current[f'{name}_pcm'] for name in CONDITIONS)
    old_upper = np.fromfile(reference['matched.f32'], dtype='<f4')
    old_research = song.samples(reference['candidate-short-128.wav'], m['sample_rate_hz'], m['frames'])
    old_plan, new_plan = (tsp.read(path) for path in (reference['candidate-inspect.json'], out / 'research-plan.json'))
    old_gestures_match = old_plan['gestures'] == new_plan['gestures']
    archived = {'upstream_pcm_matches': bool(lip.bit_equal(old_upper, upper)),
                'upstream_plan_matches': tsp.read(reference['matched.json']) == tsp.read(out / 'upstream-plan.json'),
                'research_pcm_matches': bool(lip.bit_equal(old_research, research)),
                'research_gestures_match': old_gestures_match,
                'research_pcm_change': full.metrics(research.astype(np.float64) - old_research)}
    poles = (coefficients['upstream']['dc_pole'], coefficients['candidate']['dc_pole'])
    comparison = full.compare(*CONDITIONS, current, m, poles)
    amplitudes = matched_pcm.amplitude_groups(upper, research, m['quiet_pcm_threshold'])
    left, right = (states[name] for name in CONDITIONS)
    internal = {key: full.metrics(right[key] - left[key]) for key in SOURCE_FIELDS}
    left_output, right_output = (current[f'{name}_output'] for name in CONDITIONS)
    output = {field: full.metrics(right_output[:, i] - left_output[:, i])
              for i, field in enumerate(pcm.COLUMNS[2:], start=2)}
    first = internal[radiation.RADIATION]['first_nonzero_frame']
    cast_peak = comparison['full']['precast']['peak_frame']
    raw_peak = comparison['full']['pcm']['peak_frame']
    quiet_share = amplitudes['multiple_ulp_quiet_fraction']
    checks = {
        'matched_upstream_and_plan_equal_to_archive': archived['upstream_pcm_matches'] and archived['upstream_plan_matches'],
        'ordinary_and_observed_entries_match': all(
            proof[name]['ordinary'] == proof[name]['observed'] == lip.pcm_digest(current[f'{name}_pcm'])
            and proof[name]['plan_matches'] and len(current[f'{name}_pcm']) == m['frames'] for name in CONDITIONS)
            and proof['research_normal']['csv_pcm_matches'],
        'internal_radiation_and_output_stages_replay': all(all(row.values()) for row in replay.values()),
        'same_settings_tolerance_and_rounding': comparison['full']['pcm']['peak'] <= m['same_settings_pcm_tolerance']
            and comparison['pcm_all_one_ulp_straddle']
            and all(lip.bit_equal(current[f'{name}_output'][:, full.DC].astype('<f4'), current[f'{name}_pcm'])
                    for name in CONDITIONS),
    }
    hypotheses = {
        'radiation_differs_in_first_output_pair': first is not None and first < 2,
        'precast_and_pcm_peaks_are_at_different_frames': cast_peak != raw_peak,
        'pcm_peak_is_before_first_beat': raw_peak < m['beats_frames'][0],
        'multi_ulp_differences_are_mainly_quiet': quiet_share is not None and quiet_share >= m['multi_ulp_minimum_quiet_share'],
    }
    return {'checks': checks, 'hypotheses': hypotheses, 'archive': archived, 'output_replay': replay,
            'comparison': comparison, 'amplitude_by_ulp': amplitudes,
            'internal_differences': internal, 'output_differences': output,
            'initial_source_rows': {name: current[f'{name}_source'][:m['initial_internal_samples']].tolist()
                                    for name in CONDITIONS},
            'source_field_order': list(SOURCE_FIELDS),
            'max_envelope': {name: float(np.max(current[f'{name}_output'][:, pcm.COLUMNS.index('envelope')]))
                             for name in CONDITIONS}}


def reference_paths(archive):
    return {name: archive / 'artifacts' / name for name in REFERENCE_FILES}


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
    reference, stage, coeff = (tsp.open_run(study[key], revision) for key in ('reference', 'config', 'coefficients'))
    files = {name: tsp.verified_path(reference, f'artifacts/{name}') for name in REFERENCE_FILES}
    config, cfg = radiation.saved_case(stage, lip.CONFIG)
    coefficients = tsp.verified_path(coeff, 'artifacts/coefficients.json')
    inputs = [CASE, Path(__file__).resolve(), Path(song.__file__), Path(full.__file__), Path(matched_pcm.__file__),
              cfg, coefficients, song.PROBE, *files.values(), *prefix.capture_dependencies(),
              *(run[0] / 'manifest.json' for run in (reference, stage, coeff)),
              *(upper / 'crates/chimera/tests' / name for name in ('sing_fast.rs', 'sung_release.rs', 'denormals.rs'))]

    def measure(out, execute):
        capture(study, files['candidate-short-128.json'], out, execute)
        return analyze(study, out, files, config, tsp.read(coefficients))

    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return radiation.record_measurement(args.run_id, CASE, inputs, details, measure, command=None, input_root=ws.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
