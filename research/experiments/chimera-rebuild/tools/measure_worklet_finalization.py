"""固定発声の最後の量子で描画、転送、解放を別々に計る。"""

import argparse
from functools import partial
from pathlib import Path

import measure_worklet_release_alignment as release
import measure_worklet_shared_context as shared


CASE = release.WORKSPACE / 'cases/worklet-finalization-phases.json'
PHASES = (
    ('before_render', 'render-start'),
    ('render', 'render-end'),
    ('capture', 'recorded'),
    ('prepare_message', 'post-start'),
    ('post_message', 'post-end'),
    ('after_post', 'free-start'),
    ('free_handle', 'free-end'),
    ('close_port', 'port-closed'),
    ('before_return', 'return'),
)


def intervals(callback, marks, clock, duration):
    if clock not in callback or duration not in callback or any(clock not in event for event in marks):
        return None
    times = [callback[clock], *(event[clock] for event in marks), callback[clock] + callback[duration]]
    return {name: end - start for (name, _), start, end in zip(PHASES, times, times[1:])}


def inspect_tail(spec, events, report, trial, ctor, voice_callbacks):
    mode = spec['expected_finalization_mode']
    free_prepared = spec['expected_dsp_warmup_frames'] == 0
    last_index = report['startupCallbacks'] + len(report['observations']) - 1
    marks = shared.trace_marks(events, extra=[f'final-{phase}' for _, phase in PHASES[:-1]]
                              + ['final-detached', 'final-retained', 'final-partial'])
    marks = {name[6:]: group for name, group in marks.items() if name.startswith('final-')}
    checks = {'same_wasm_as_registered': trial['servedWasmSha256'] == spec['registered_wasm_sha256'],
              'finalization_options_applied': report.get('finalizationProbe') == mode
              and report['wrapperWarmup'].get('discardedRenderFrames') == spec['expected_dsp_warmup_frames'],
              'all_finalization_marks_present': len(voice_callbacks) > last_index
              and all(len(marks[phase]) == 1 for _, phase in PHASES[:-1])}
    details = {'mode': mode, 'free_prepared': free_prepared,
               'mark_counts': {phase: len(rows) for phase, rows in marks.items()}}
    if not checks['all_finalization_marks_present']:
        return checks, details
    last = voice_callbacks[last_index]
    thread = (last['pid'], last['tid'])
    ordered = [marks[phase][0][1] for _, phase in PHASES[:-1]]
    context_frame = report['observations'][-1][0]
    checks['marks_on_last_recorded_quantum'] = all(
        marks[phase][0][0] == context_frame and (event['pid'], event['tid']) == thread
        for (_, phase), event in zip(PHASES[:-1], ordered))
    wall = intervals(last, ordered, 'ts', 'dur')
    cpu = intervals(last, ordered, 'tts', 'tdur')
    checks['ordered_nonnegative_scope_partition'] = (
        all(value >= 0 for value in wall.values()) and sum(wall.values()) == last['dur'])
    statuses = ['detached', 'retained', 'partial']
    sender_state = [(phase, frame, event) for phase in statuses for frame, event in marks[phase]]
    details['sender_buffer_state'] = [phase for phase, _, _ in sender_state]
    state_should_be = 'retained' if mode == 'copy' else 'detached'
    post_ended = marks['post-end'][0][1]['ts']
    free_began = marks['free-start'][0][1]['ts']
    checks['sender_buffers_transferred_or_copied_as_requested'] = (
        len(sender_state) == 1 and all(phase == state_should_be and frame == context_frame
                                       and (event['pid'], event['tid']) == thread
                                       and post_ended <= event['ts'] <= free_began
                                       for phase, frame, event in sender_state))
    lazy = [event for event in events if event['ph'] == 'X' and event['name'] == spec['finalization_lazy_event']
            and (event['pid'], event['tid']) == thread]
    prepared = shared.function_compilations_in_interval(lazy, ctor[0]['ts'], ctor[1]['ts'])
    funcs = {}
    boundaries = [last, *ordered]
    ends = [*(row['ts'] for row in ordered), last['ts'] + last['dur']]
    for (name, _), start, end in zip(PHASES, boundaries, ends):
        funcs[name] = shared.function_compilations_in_interval(lazy, start['ts'], end)
    released_ids = {row['index'] for row in funcs['free_handle']}
    constructor_ids = {row['index'] for row in prepared}
    free_functions = set(spec['free_functions'])
    checks['result_function_compilation_is_in_message_preparation'] = (
        spec['result_function'] in {row['index'] for row in funcs['prepare_message']})
    checks['free_functions_compile_in_expected_phase'] = (
        free_functions <= constructor_ids and free_functions.isdisjoint(released_ids) if free_prepared
        else free_functions <= released_ids and free_functions.isdisjoint(constructor_ids))
    pcm_bytes = report['outputFrames'] * 4
    observation_bytes = len(report['columns']) * len(report['observations']) * 8
    budget_us = 1e6 * report['observations'][-1][1] / report['sampleRate']
    details.update({
        'context_frame': context_frame,
        'pcm_bytes': pcm_bytes, 'observation_bytes': observation_bytes,
        'phase_wall_us': wall, 'phase_thread_us': cpu, 'full_callback_wall_us': last['dur'],
        'full_callback_thread_us': last.get('tdur'),
        'reported_process_ms': report['observations'][-1][2], 'budget_us': budget_us,
        'budget_exceeded': last['dur'] > budget_us,
        'longest_phase': max(wall, key=wall.get),
        'lazy_compile_in_each_phase': funcs,
        'free_functions_in_constructor': [row for row in prepared if row['index'] in free_functions],
    })
    return checks, details


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    study = release.stored.read(CASE)
    dsp_path = release.WORKSPACE / 'cases' / study['dsp_case']
    dsp = release.stored.read(dsp_path)
    shared_path = release.WORKSPACE / 'cases' / dsp['shared_case']
    baseline = release.stored.read(shared_path)
    prior, manifest = release.saved.load_saved_run(
        study['dsp_run'], dsp['id'], study['upstream_revision'], ['summary.json', 'artifacts/vocal_wasm.wasm'])
    inputs = release.stored.read(manifest)['inputs']
    for path in (dsp_path, shared_path):
        digest, = (row['sha256'] for row in inputs if row['path'].endswith('/' + path.name))
        if digest != release.sha256(path):
            parser.error('前回のケース定義のハッシュが一致しません')
    if (not all(release.stored.read(prior['summary.json'])['checks'].values())
            or release.sha256(prior['artifacts/vocal_wasm.wasm']) != dsp['wasm_sha256']):
        parser.error('前回の比較記録またはWASMを照合できません')
    measurement = {**baseline['measurement'], **study['measurement'],
                   'registered_wasm_sha256': dsp['wasm_sha256']}
    registered = {**baseline, **study, 'measurement': measurement}
    return shared.run_shared_study(args.run_id, CASE, registered,
        inspect_capture=partial(shared.inspect_shared_trace, inspect_tail=inspect_tail),
        extra_inputs=(Path(__file__).resolve(), dsp_path, shared_path, manifest, *prior.values()))


if __name__ == '__main__':
    raise SystemExit(main())
