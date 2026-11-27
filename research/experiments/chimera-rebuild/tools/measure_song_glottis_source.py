"""短音の歌唱で、声門の乱流源のゲインを個別に比較する。"""

import argparse
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
from scipy.io import wavfile

import measure_song_voice as song
from measure_fan_crossing_allocations import run_manifest, verified_path
from upstream_baseline import sha256


WORKSPACE = song.WORKSPACE
CASE = WORKSPACE / 'cases/song-voice-fast-glottis-source.json'
REFERENCES = ('artifacts/pcm-128.wav', 'artifacts/voicing.csv',
              'artifacts/upstream-pcm.f32', 'artifacts/upstream-voicing.csv')
LEVELS = ('glottis_noise_level', 'constriction_noise_level', 'teeth_noise_level')
OBSERVATIONS = ('glottis_noise_forward_pressure', 'glottis_noise_reverse_pressure',
                'constriction_noise_forward_pressure', 'constriction_noise_reverse_pressure',
                'teeth_noise_forward_pressure', 'teeth_noise_reverse_pressure',
                'pressure_supra_dyn_cm2', 'glottal_flow_cm3_s', 'glottal_area_cm2',
                'radiation_derivative_cm3_s2', 'gate', 'abduction_cm2', 'glottal_f0_hz')


def first(mask):
    indices = np.flatnonzero(mask)
    return int(indices[0]) if len(indices) else None


def differences(before, after, pcm_before, pcm_after, floor):
    pcm_delta = np.abs(pcm_after.astype(float) - pcm_before)
    return {'trace': {field: first(before[field] != after[field]) for field in OBSERVATIONS},
            'pcm_first_bit_difference_frame': first(pcm_before.view('<u4') != pcm_after.view('<u4')),
            'pcm_first_above_floor_frame': first(pcm_delta > floor),
            'pcm_maximum_absolute_difference': float(pcm_delta.max())}


def describe_effect(study, reference, control, muted, reference_pcm, control_pcm, muted_pcm):
    floor = study['pcm_difference_floor']
    for s in (reference_pcm, control_pcm, muted_pcm):
        if s.shape != (len(control),) or s.dtype != np.float32 or not np.isfinite(s).all():
            raise ValueError('比較するPCMの形式が一致しません')
    before = differences(reference, control, reference_pcm, control_pcm, floor)
    after = differences(reference, muted, reference_pcm, muted_pcm, floor)
    slots = ('glottis_noise_source', 'glottis_noise_forward', 'glottis_noise_reverse')
    return {'full_against_zero': before, 'muted_against_zero': after,
            'muted_against_full': differences(control, muted, control_pcm, muted_pcm, floor),
            'muted_first_active_sources': {field: first(muted[field] > 0) for field in LEVELS},
            'muted_peak_source_levels_dyn_cm2': {field: float(np.max(muted[field])) for field in LEVELS},
            'glottis_source_retained_with_zero_gain': (all(np.array_equal(control[k], muted[k]) for k in slots)
                                                       and bool(np.all(muted['glottis_noise_forward'] >= 0))
                                                       and bool(np.all(muted['glottis_noise_gain'] == 0)))}


def measure(study, source, references, artifacts, execute):
    base = song.timing.read(source)
    frames = base['measurement']['expected_frames']
    blocks = base['measurement']['host_block_frames']
    tests = [arg for suite in song.SUITES for arg in ('--test', suite)]
    execute(['cargo', 'test', '--locked', '-p', 'chimera', *tests], cwd=song.UPSTREAM,
            stdout=artifacts / 'upstream-tests.log')
    probe = song.shared.build_upstream_probe(song.voice.PROBE, artifacts, execute, extra_libraries=('serde_json',))
    renders, checks, comparison = {}, {}, {}
    for label, turbulence in (('full', {'scale': 1}), ('glottis_gain_zero', study['turbulence'])):
        folder = artifacts / label
        folder.mkdir()
        case = {**base, 'song_voice': {**base['song_voice'], 'turbulence': turbulence}}
        config = folder / 'case.json'
        config.write_text(json.dumps(case, ensure_ascii=False, indent=2) + '\n')
        renders[label] = song.voice.capture(config, blocks, folder, execute, (), probe=probe)
        comparison[label] = song.compare_outputs(case, *renders[label])
        checks.update({f'{label}/{key}': value for key, value in comparison[label]['checks'].items()})

    full, muted = (renders[key] for key in ('full', 'glottis_gain_zero'))
    checks['same_planned_score'] = all(full[0][key] == muted[0][key] for key in ('song', 'gestures'))
    reference, archived_full = references
    checks['full_cli_matches_archived_wav'] = sha256(full[2][0][0]) == sha256(archived_full['artifacts/pcm-128.wav'])
    checks['full_upstream_matches_archived_pcm'] = sha256(full[4]) == sha256(archived_full['artifacts/upstream-pcm.f32'])
    evidence = {
        'cli': describe_effect(study, *(song.voice.load_trace(path, frames) for path in (
            reference['artifacts/voicing.csv'], full[1], muted[1])),
            *(wavfile.read(path)[1] for path in (reference['artifacts/pcm-128.wav'], full[2][0][0], muted[2][0][0]))),
        'upstream': describe_effect(study, *(song.voice.load_trace(path, frames) for path in (
            reference['artifacts/upstream-voicing.csv'], full[3], muted[3])),
            *(np.fromfile(path, dtype='<f4') for path in (reference['artifacts/upstream-pcm.f32'], full[4], muted[4]))),
    }
    checks['source_slot_preserved_and_muted'] = all(
        row['glottis_source_retained_with_zero_gain'] and row['muted_peak_source_levels_dyn_cm2'][LEVELS[0]] == 0
        for row in evidence.values())
    predictions = {'other_sources_remain_active': all(any(row['muted_first_active_sources'][key] is not None
                                                           for key in LEVELS[1:]) for row in evidence.values()),
                   'first_pcm_difference_moved_later': all(
                       row['muted_against_zero']['pcm_first_bit_difference_frame'] is not None and
                       row['full_against_zero']['pcm_first_bit_difference_frame'] is not None and
                       row['muted_against_zero']['pcm_first_bit_difference_frame'] >
                       row['full_against_zero']['pcm_first_bit_difference_frame'] for row in evidence.values())}
    return {'checks': checks, 'comparison_to_upstream': comparison, 'predictions': predictions, 'evidence': evidence}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    study = song.timing.read(CASE)
    source = CASE.parent / study['source_case']
    base = song.timing.read(source)
    revision = study['upstream_revision']
    if (base['upstream_revision'] != revision or study['turbulence'] != {'scale': 1, 'glottis_gain_multiplier': 0} or
            subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=song.UPSTREAM, text=True).strip() != revision or
            subprocess.check_output(['git', 'status', '--porcelain'], cwd=song.UPSTREAM, text=True)):
        parser.error('変更のない固定上流と短音の比較ケースが必要です')
    references, files = [], []
    for scale, name in enumerate((study['zero_reference_run'], study['full_reference_run'])):
        run = run_manifest(name, 'worklet-song-voice-fast', revision)
        if run[1]['status'] != 'pass' or run[1]['turbulence_scale'] != scale:
            parser.error(f'{name} の係数または判定が一致しません')
        outputs = {name: verified_path(run, name) for name in REFERENCES}
        if scale == 0:
            aligned = any(row['path'].endswith('/' + source.name) and row['sha256'] == sha256(source)
                          for row in run[1]['inputs'])
        else:
            original = verified_path(run, 'artifacts/turbulence-input.json')
            files.append(original)
            aligned = song.timing.read(original) == {**base, 'song_voice': {**base['song_voice'], 'turbulence': {'scale': 1}}}
        if not aligned:
            parser.error(f'{name} の短音入力が一致しません')
        references.append(outputs)
        files.extend([run[0] / 'manifest.json', *outputs.values()])
    inputs = [CASE, source, Path(__file__).resolve(), song.voice.PROBE, *files, *song.shared.candidate_sources(),
              *(Path(module.__file__) for module in (song, song.voice, song.timing, song.shared, song.alveolar, song.vowel))]
    metadata = {'case_id': study['id'], 'upstream_revision': revision,
                'analysis_directory': str(Path.cwd()), 'analysis_command': [sys.executable, *sys.argv]}
    return song.shared.record_measurement(args.run_id, CASE, inputs, metadata,
        lambda artifacts, execute: measure(study, source, references, artifacts, execute), command=None,
        input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
