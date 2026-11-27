"""短音の歌唱で声門と狭窄の乱流を抑えたときの歯の乱流を計測する。"""

import argparse
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
from scipy.io import wavfile

import measure_fan_crossing_allocations as archive
import measure_song_glottis_source as glottis
import measure_song_voice as song
from upstream_baseline import sha256


WORKSPACE = song.WORKSPACE
CASE = WORKSPACE / 'cases/song-voice-fast-constriction-source.json'
SOURCES = ('glottis', 'constriction')
CONTROLS = ('gate', 'abduction_cm2', 'glottal_f0_hz', 'smoothed_f0_hz')
TEETH_COORDINATES = ('teeth_noise_source', 'teeth_noise_forward', 'teeth_noise_reverse')
JET = ('noise_minimum_cm2', 'noise_teeth_distance_cm', 'noise_jet_area_cm2', 'noise_jet_flow_cm3_s')


def without_sources(trace, reference, prefix):
    columns = [f'{prefix}_noise_{field}' for field in ('source', 'forward', 'reverse')]
    return (all(np.array_equal(trace[key], reference[key]) for key in columns)
            and bool(np.any(trace[columns[1]] >= 0))
            and all(not np.any(trace[f'{prefix}_noise_{field}']) for field in ('gain', 'level')))


def compare(study, zero, control, current):
    frames = current[0]['output_frames']
    outputs = (
        ('cli', 'voicing.csv', 'pcm-128.wav', current[1], current[2][0][0], lambda p: wavfile.read(p)[1]),
        ('upstream', 'upstream-voicing.csv', 'upstream-pcm.f32', current[3], current[4],
         lambda p: np.fromfile(p, dtype='<f4')),
    )
    evidence, checks, predictions = {}, {}, {}
    for label, trace_name, audio_name, trace_path, pcm_path, read in outputs:
        silent, muted_glottis, isolated = (song.voice.load_trace(p, frames)
                                          for p in (zero[trace_name], control[trace_name], trace_path))
        pcms = [read(p) for p in (zero[audio_name], control[audio_name], pcm_path)]
        if any(p.shape != (frames,) or p.dtype != np.float32 or not np.isfinite(p).all() for p in pcms):
            raise ValueError(f'{label} のPCMのフレーム数・形式・有限性が一致しません')
        floor = study['pcm_difference_floor']
        prior = glottis.differences(silent, muted_glottis, pcms[0], pcms[1], floor)
        effect = glottis.differences(silent, isolated, pcms[0], pcms[2], floor)
        suppression = glottis.differences(muted_glottis, isolated, pcms[1], pcms[2], floor)
        effect['first_jet_change_at_control_update'] = glottis.first(
            silent['noise_jet_flow_cm3_s'] != isolated['noise_jet_flow_cm3_s'])
        first_activity = glottis.first(isolated['teeth_noise_level'] > 0)
        first_registration = glottis.first(isolated['teeth_noise_source'] >= 0)
        prior_activity = glottis.first(muted_glottis['teeth_noise_level'] > 0)
        field = 'pcm_first_bit_difference_frame'
        prior_radiation = prior['trace']['radiation_derivative_cm3_s2']
        radiation = effect['trace']['radiation_derivative_cm3_s2']
        pressures = [effect['trace'][f'teeth_noise_{direction}_pressure'] for direction in ('forward', 'reverse')]
        first_pressure = min((i for i in pressures if i is not None), default=None)
        band = song.speech.independent_band(isolated, study['teeth_band_absolute_tolerance_hz'])
        checks.update({f'{label}/{name}_slot_and_zero_gain': without_sources(isolated, muted_glottis, name)
                       for name in SOURCES})
        checks[f'{label}/same_control_targets'] = all(np.array_equal(isolated[key], muted_glottis[key])
                                                       for key in CONTROLS)
        checks[f'{label}/independent_teeth_band_and_gain'] = (band['passed'] and
            band['gain_max_error'] <= study['teeth_gain_absolute_tolerance'])
        predictions[f'{label}/teeth_remain_active'] = first_activity is not None
        predictions[f'{label}/radiation_and_pcm_moved_later'] = (
            radiation is not None and prior_radiation is not None and radiation > prior_radiation
            and effect[field] is not None and prior[field] is not None and effect[field] > prior[field])
        predictions[f'{label}/injection_at_or_after_teeth_activity'] = (
            first_activity is not None and first_pressure is not None and first_pressure >= first_activity)
        evidence[label] = {
            'glottis_only_muted_against_zero': prior,
            'both_muted_against_zero': effect,
            'both_muted_against_glottis_only_muted': suppression,
            'first_teeth_registration_frame': first_registration,
            'first_teeth_activity_frame': first_activity,
            'prior_first_teeth_activity_frame': prior_activity,
            'first_teeth_injection_frame': first_pressure,
            'first_teeth_activity_state': None if first_activity is None else {
                key: float(isolated[key][first_activity]) for key in (
                    *TEETH_COORDINATES, *JET, 'teeth_noise_gain', 'teeth_noise_level',
                    'teeth_noise_lowpass_hz', 'teeth_noise_forward_pressure', 'teeth_noise_reverse_pressure')},
            'teeth_band': band,
        }
    return checks, predictions, evidence


def measure(study, base, zero, control, artifacts, execute):
    tests = [arg for suite in (*song.SUITES, 'voiced_fricatives', 'affricates') for arg in ('--test', suite)]
    execute(['cargo', 'test', '--locked', '-p', 'chimera', *tests], cwd=song.UPSTREAM,
            stdout=artifacts / 'upstream-tests.log')
    probe = song.shared.build_upstream_probe(song.voice.PROBE, artifacts, execute, extra_libraries=('serde_json',))
    config = {**base, 'song_voice': {**base['song_voice'], 'turbulence': study['turbulence']}}
    path = artifacts / 'case.json'
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n')
    render = song.voice.capture(path, base['measurement']['host_block_frames'], artifacts, execute, (), probe=probe)
    comparison = song.compare_outputs(config, *render)
    checks, predictions, evidence = compare(study, zero, control, render)
    prior_settings = song.timing.read(control['settings.json'])
    checks['same_planned_score'] = all(render[0][key] == prior_settings[key] for key in ('song', 'gestures'))
    return {'checks': {**comparison['checks'], **checks}, 'comparison_to_upstream': comparison,
            'predictions': predictions, 'evidence': evidence}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    study = song.timing.read(CASE)
    source = CASE.parent / study['source_case']
    base = song.timing.read(source)
    revision = study['upstream_revision']
    if (base['upstream_revision'] != revision or
            subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=song.UPSTREAM, text=True).strip() != revision or
            subprocess.check_output(['git', 'status', '--porcelain'], cwd=song.UPSTREAM, text=True)):
        parser.error('変更のない固定上流と短音の比較ケースが必要です')

    zero = archive.run_manifest(study['zero_reference_run'], 'worklet-song-voice-fast', revision)
    control = archive.run_manifest(study['glottis_only_muted_reference_run'], glottis.CASE.stem, revision)
    if (zero[1]['status'] != 'pass' or zero[1]['turbulence_scale'] != 0 or control[1]['status'] != 'pass'
            or not any(row['path'].endswith('/' + source.name) and row['sha256'] == sha256(source)
                       for row in zero[1]['inputs'])):
        parser.error('保存済みの全体係数0または声門だけを抑えた対照が揃いません')
    prefix = 'artifacts/glottis_gain_zero/'
    saved_case = archive.verified_path(control, prefix + 'case.json')
    if song.timing.read(saved_case) != {**base, 'song_voice': {**base['song_voice'],
            'turbulence': {'scale': 1, 'glottis_gain_multiplier': 0}}}:
        parser.error('声門だけを抑えた保存ケースと短音入力が一致しません')
    names = [Path(path).name for path in glottis.REFERENCES]
    zero_outputs = {name: archive.verified_path(zero, 'artifacts/' + name) for name in names}
    control_outputs = {name: archive.verified_path(control, prefix + name) for name in (*names, 'settings.json')}
    metadata = {'case_id': study['id'], 'upstream_revision': revision,
                'analysis_directory': str(Path.cwd()), 'analysis_command': [sys.executable, *sys.argv]}
    modules = (archive, glottis, song, song.voice, song.speech, song.shared, song.timing, song.alveolar, song.vowel)
    inputs = [CASE, source, saved_case, Path(__file__).resolve(), song.voice.PROBE,
              zero[0] / 'manifest.json', control[0] / 'manifest.json', *zero_outputs.values(), *control_outputs.values(),
              *(Path(module.__file__) for module in modules), *song.shared.candidate_sources()]
    return song.shared.record_measurement(args.run_id, CASE, inputs, metadata,
        lambda artifacts, execute: measure(study, base, zero_outputs, control_outputs, artifacts, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
