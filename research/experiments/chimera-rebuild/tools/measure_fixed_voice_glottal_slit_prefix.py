"""保存したPCMの最初の差まで内部時系列を延ばし、固定上流と照合する。"""

import argparse
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
from scipy.io import wavfile

from measure_fixed_voice_glottal_slit import (
    BALANCE_CASE, CASE as SLIT_CASE, LUNG_CASE, PATCH_ORDER, REFERENCES, ROOT, SERIES_CASE, SINGLE_CASE,
    SLIT_EDITS, capture, read_rows, record_measurement, same, source_inputs, verified_artifact,
)
from measure_wasm_fixed import compare_pcm
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-voice-glottal-slit-prefix-48000.json'
ACOUSTIC = ('lung_boundary_dyn_cm2', 'pressure_sub_dyn_cm2', 'pressure_supra_dyn_cm2',
            'glottal_flow_cm3_s', 'lip_flow_cm3_s', 'nose_flow_cm3_s', 'radiation_derivative_cm3_s2')


def measure(case, common, refs, saved, copies, snapshot, out, execute):
    nframes = case['prefix_frames']
    compiled_input = json.loads(refs['prefix-case.json'].read_text())
    factor = common['internal_rate_hz'] // common['sample_rate_hz']
    compiled_input['fixed_airway']['sample_count'] = nframes * factor
    prefix = out / 'extended-prefix-case.json'
    prefix.write_text(json.dumps(compiled_input, indent=2, ensure_ascii=False) + '\n')
    refs = {**refs, 'prefix-case.json': prefix, 'replay-case.json': prefix}
    hashes = capture({**common, 'blocks': [128]}, refs, copies, snapshot, out, execute,
                     patch_order=(*PATCH_ORDER, 'single-branch-history.patch', 'series-branch-history.patch',
                                  'lung-branch-history.patch'), variant_edits=SLIT_EDITS)
    reference = read_rows(saved['upstream-trace.csv'], nframes)
    indices = [(i + 1) * factor - 1 for i in range(nframes)]
    pcm_upper = np.fromfile(saved['upstream-voice.f32'], dtype='<f4', count=nframes)
    checks = {'upstream_sampling_clock': [row['internal_sample'] for row in reference] == indices,
              'slit_patch_reproduced': sha256(out / 'candidate-tracheal-history.patch') == sha256(saved['slit.patch'])}
    results = {}
    for name in ('control', 'reordered'):
        directory = out / name
        source_trace = directory / 'candidate-internal.csv'
        raw = source_trace.read_bytes()
        checks[f'{name}_trace_prefix'] = raw.startswith(saved[f'{name}-internal.csv'].read_bytes())
        actual = read_rows(source_trace)
        checks[f'{name}_sampling_clock'] = [row['internal_sample'] for row in actual] == list(range(nframes * factor))
        rate, pcm = wavfile.read(directory / 'block-128.wav')
        archived_rate, archived_pcm = wavfile.read(saved[f'{name}-pcm.wav'])
        checks[f'{name}_archived_pcm_prefix'] = (rate == archived_rate == common['sample_rate_hz']
                                                and pcm.tobytes() == archived_pcm[:nframes].tobytes())
        audio = compare_pcm(pcm, pcm_upper, common['pcm_absolute_tolerance'])
        timing = {}
        for key in ACOUSTIC:
            timing[key] = next(({'frame': i, 'internal_sample': index, 'candidate': actual[index][key],
                                 'upstream': reference[i][key]} for i, index in enumerate(indices)
                                if not same(actual[index][key], reference[i][key])), None)
        frame = audio['first_bit_difference_frame']
        neighborhood = [] if frame is None else [
            {'frame': i, 'internal_sample': indices[i], **{key: {'candidate': actual[indices[i]][key],
                 'upstream': reference[i][key]} for key in ACOUSTIC}}
            for i in range(max(0, frame - 1), min(nframes, frame + 2))]
        results[name] = {'pcm': audio, 'first_acoustic_differences': timing, 'pcm_difference_neighborhood': neighborhood}
    return {'checks': checks, 'build_sha256': hashes, 'results': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case, slit, common, base, series, lung = (json.loads(path.read_text()) for path in (
        CASE, SLIT_CASE, SINGLE_CASE, BALANCE_CASE, SERIES_CASE, LUNG_CASE))
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    groups = {**base['references'], 'onset': common['onset_run']}
    patch_files = {group: [name for name in names if name in PATCH_ORDER or name == 'prefix-case.json']
                   for group, names in REFERENCES.items() if group != 'pcm'}
    refs, manifests, saved = {}, {}, {}
    for group, names in patch_files.items():
        for name in names:
            manifests[group], refs[name] = verified_artifact(*groups[group], f'artifacts/{name}')
    for group, run in (('single', series['single_branch_run']), ('series', lung['series_run']), ('lung', slit['lung_run'])):
        manifests[group], refs[f'{group}-branch-history.patch'] = verified_artifact(*run, 'artifacts/candidate-tracheal-history.patch')
    for name in ('upstream-trace.csv', 'upstream-voice.f32'):
        manifests['upper'], saved[name] = verified_artifact(*common['pcm_input_run'], f'artifacts/{name}')
    manifests['slit'], saved['slit.patch'] = verified_artifact(*case['slit_run'], 'artifacts/candidate-tracheal-history.patch')
    for name in ('control', 'reordered'):
        for filename, key in (('candidate-internal.csv', 'internal.csv'), ('block-128.wav', 'pcm.wav')):
            _, saved[f'{name}-{key}'] = verified_artifact(*case['slit_run'], f'artifacts/{name}/{filename}')
    copies, archived, snapshot = source_inputs(manifests['scaled'])
    loaded = (Path(file).resolve() for module in tuple(sys.modules.values())
              if (file := getattr(module, '__file__', None)))
    tools = sorted({path for path in loaded if path.parent == WORKSPACE / 'tools' and path.suffix == '.py'})
    inputs = [CASE, SLIT_CASE, SINGLE_CASE, BALANCE_CASE, SERIES_CASE, LUNG_CASE, WORKSPACE / 'LICENSE-CHIMERA',
              *archived, *tools, *manifests.values(), *refs.values(), *saved.values()]
    return record_measurement(args.run_id, CASE, inputs, {'case_id': case['id'], 'upstream_revision': revision},
                              lambda out, run: measure(case, common, refs, saved, copies, snapshot, out, run),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
