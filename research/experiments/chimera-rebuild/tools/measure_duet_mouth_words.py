"""口元の音節の投影、退場、シークへの追従を実ブラウザで検証する。"""

import argparse
from fractions import Fraction
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

import measure_uniform_tube as shared
from measure_duet_words import expected_word, oracle, prior
from measure_fan_crossing_allocations import verified_path
from measure_wasm_fixed import read_json
from measure_worklet_fixed import ROOT, WEB, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/duet-mouth-words.json'
DEMO = WEB / 'public/shows/duet-clock'
CAPTURE = WEB / 'tools/capture-duet-mouth-words.mjs'


def reference_trail(spec, reset):
    entries = []
    for step in spec['controlled_trail']:
        now, word = step['time_ms'] / 1000, step['word']
        if reset and step.get('seek'):
            entries = []
        top = entries[-1] if entries else None
        returned = top and word and word['key'] == top['word']['key']
        if returned:
            top['left'] = None
        else:
            if top and top['left'] is None:
                top['left'] = now
            if word:
                entries.append({'word': word, 'left': None})
        entries = [item for item in entries if item['left'] is None or now - item['left'] <= spec['fade_seconds']][-8:]
        yield [item.copy() for item in entries]


def word_keys(head, departure):
    return [label['key'] for label in head['labels'] if label['departing'] == departure]


def coordinates(head, fade_seconds):
    width, height = head['css']
    facing = head['facing']
    world = np.array(head['model']).reshape(4, 4, order='F') if 'model' in head else np.diag([facing, 1, 1, 1])
    projection, view = (np.array(head[key]).reshape(4, 4, order='F') for key in ('projection', 'view'))
    matrix = projection @ view
    lip_cm = np.mean(head['lipCenters'], axis=0) + [0.15, 0, 0]
    point = matrix @ world @ np.r_[lip_cm, 1]
    lx, ly = point[:2] / point[3] * [width / 2, -height / 2] + [width / 2, height / 2]
    scale = np.linalg.norm(matrix[0, :3]) * width / 2
    x0 = lx + facing * scale * 1.2
    ahead = (width - x0 if facing == 1 else x0) - 14
    below = bool(ahead < 60)
    room = width - 16 if below else ahead
    base = np.clip(scale * 1.7, 26, 64)
    errors = []
    for element, item in zip(head['labels'], head['overlay']['labels'], strict=True):
        age = item['age']
        u = min(1, age / fade_seconds)
        w = 1.08 * element['baseWidth']
        size = base * (1 - .55 * u) * min(room / max(1.0, w), 1.0)
        alpha = .75 * (1 - u) ** 1.5 if element['departing'] else 1.0
        if below:
            half = min(w, room) * (1 - .55 * u) / 2
            x = np.clip(lx, 8 + half, width - 8 - half)
            y = min(height - 14, ly + scale * 18) + age * 120
        else:
            x, y = x0 + facing * age * 240, ly + size * .36 - age * 200
        errors.extend(abs(element[k] - value) for k, value in zip(('x', 'y', 'size', 'alpha'), (x, y, size, alpha)))
    actual = head['overlay']
    errors.extend(abs(actual['view'][field] - expected) for field, expected in dict(x=lx, y=ly, pxPerCm=scale).items())
    return float(max(errors)), actual['below'] == below, below


def inside(head, tolerance):
    width, height = head['css']
    labels = [label for label in head['labels'] if not label['departing']]
    for label in labels:
        x1, y1, x2, y2 = label['bounds']
        if min(x1, y1) < -tolerance or x2 > width + tolerance or y2 > height + tolerance:
            return False
        if not head['overlay']['below']:
            lips = head['overlay']['view']['x']
            if head['facing'] == 1 and x1 <= lips or head['facing'] == -1 and x2 >= lips:
                return False
    return True


def changed_pixels(view, artifacts, samples):
    images = [np.asarray(Image.open(artifacts / view['screenshots'][str(sample)]).convert('RGB'), dtype=np.int16)
              for sample in samples]
    return int(np.any(np.abs(images[1] - images[0]) >= 20, axis=2).sum())


def measure(spec, artifacts, execute, bun, source):
    execute([*bun, 'test', 'tests/words.test.ts', 'tests/transport.test.ts'], cwd=UPSTREAM)
    execute([*bun, 'run', 'build'], cwd=WEB)
    execute([*bun, str(CAPTURE), str(CASE), str(UPSTREAM), str(artifacts), str(source)], cwd=WEB)
    browser = read_json(artifacts / 'browser-mouth.json')
    upper = read_json(artifacts / 'upper-mouth.json')
    inputs = read_json(source / 'word-inputs.json')
    fade = spec['fade_seconds']
    control_before = list(reference_trail(spec, reset=False))
    control_after = list(reference_trail(spec, reset=True))
    checks = {'usual_trail_matches_upper_and_independent_result': all(row['upper'] == row['candidate'] == ref
                  for row, ref in zip(upper['control'], control_before, strict=True)),
              'seek_reset_matches_independent_result': [row['isolated'] for row in upper['control']] == control_after,
              'upper_retains_previous_key_after_seek': any(row.get('seek') and len(control_before[i]) >
                  len(control_after[i]) == 1 for i, row in enumerate(spec['controlled_trail'])),
              'no_browser_errors': not browser['errors']}
    toler = spec['projection_tolerance_css_px']
    known_decimals = {(54720, 2), (78720, 2)}
    observed_decimals = set()
    viewports = []
    for viewport in browser['viewports']:
        width = viewport['width']
        expected_below = width == spec['viewports'][1][0]
        errors = []
        upper_errors = []
        word_count = 0
        tests = {'paused_words': True, 'paused_no_inherited_labels': True, 'head_clock_matches_words': True,
                 'foreground_inside': True, 'projection_places_foreground': True, 'fixed_upper_same_placement': True}
        for scene in ('demo', 'diagnostic'):
            phrase = inputs[scene]
            schedules = [oracle(voice, phrase['spell']) for voice in phrase['voices']]
            rows = viewport[scene]['paused']
            tests['paused_words'] &= [row['sample'] for row in rows] == spec[f'{scene}_paused_samples']
            for row in rows:
                at = Fraction(row['sample'], spec['sample_rate_hz'])
                expected = [expected_word(schedule, at) for schedule in schedules]
                tests['paused_words'] &= row['table'] == expected
                fixed = next(item['heads'] for item in upper['placements'] if item['scene'] == scene
                             and item['width'] == width and item['epoch'] == row['epoch'])
                for i, (head, word, comparison) in enumerate(zip(row['heads'], expected, fixed, strict=True)):
                    tests['head_clock_matches_words'] &= head['clock']['time'] == row['time'] and (
                        head['clock']['epoch'] == row['epoch'] and not head['clock']['playing'])
                    labels = head['labels']
                    tests['paused_no_inherited_labels'] &= (
                        [(item['key'], item['text'], item['departing']) for item in labels] ==
                        ([(word['key'], word['text'].upper(), False)] if word else []))
                    error, mode, below = coordinates(head, fade)
                    errors.append(error)
                    tests['projection_places_foreground'] &= mode and (not word or below == expected_below)
                    tests['foreground_inside'] &= inside(head, spec['layout_tolerance_css_px'])
                    if word != comparison['word']:
                        observed_decimals.add((row['sample'], i + 1) if scene == 'demo' else ('diagnostic', i + 1))
                    elif word and labels and len(comparison['calls']) == 1:
                        call, label = comparison['calls'][0], labels[0]
                        tests['fixed_upper_same_placement'] &= call['text'] == label['text'] and call['align'] == (
                            'center' if below else 'left' if i == 0 else 'right')
                        upper_errors.extend(abs(call[k] - label[k]) for k in ('x', 'y', 'size'))
                    elif word:
                        tests['fixed_upper_same_placement'] = False
                    word_count += len(labels)
        tests['projection_places_foreground'] &= max(errors) <= toler
        tests['fixed_upper_same_placement'] &= bool(upper_errors) and max(upper_errors) <= toler
        demo = viewport['demo']
        before, after = [next(row for row in demo['paused'] if row['sample'] == s) for s in spec['screenshot_samples']]
        difference = changed_pixels(demo, artifacts, spec['screenshot_samples'])
        tests['word_is_rendered'] = before['heads'][0]['index'] == after['heads'][0]['index'] and (
            difference >= spec['minimum_changed_pixels'])
        if 'afterResize' in demo:
            old, new = demo['beforeResize'], demo['afterResize']
            tests['resize_repositions_paused_word'] = (
                old['sample'] == new['sample'] and old['epoch'] == new['epoch'] and
                not old['heads'][0]['overlay']['below'] and new['heads'][0]['overlay']['below'] and
                inside(new['heads'][0], spec['layout_tolerance_css_px']))
        live = viewport['diagnostic']['live']
        states = [live[name]['heads'][0] for name in ('melisma', 'rest', 'restFaded', 'repeat', 'following')]
        tests['live_melisma_rest_repeat_and_departure'] = (
            [word_keys(head, False) for head in states] == [[0], [], [], [2], [3]] and
            [word_keys(head, True) for head in states] == [[], [0], [], [], [2]] and
            all(head['clock']['playing'] and coordinates(head, fade)[0] <= toler for head in states))
        tests['live_forward_backward_seek_clears_prior_words'] = (
            [step['sample'] for step in live['seeks']] == spec['diagnostic_live']['seek_samples'] and
            [word_keys(step['heads'][0], False) for step in live['seeks']] == [[], [2], [0]] and
            all(head['clock']['playing'] and not word_keys(head, True) for step in live['seeks'] for head in step['heads']))
        checks.update({f'{width}_{name}': verdict for name, verdict in tests.items()})
        viewports.append({'width_css_px': width, 'foreground_labels_checked': word_count,
            'max_projection_error_css_px': max(errors), 'max_placement_difference_to_upper_css_px': max(upper_errors, default=None),
            'paired_screenshot_changed_pixels': difference,
            'live_first_voice_samples': {key: row['sample'] for key, row in live.items() if key != 'seeks'}})
    checks['only_known_upper_note_boundary_rounding'] = observed_decimals == known_decimals
    return {'checks': checks, 'browser': browser['browser'], 'observed_upper_boundary_differences': sorted(observed_decimals),
            'viewports': viewports}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('英数字で始まる実行IDが必要です')
    spec = read_json(CASE)
    ref = spec['reference']
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != spec['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        parser.error('変更のない固定上流版が必要です')
    heads = prior(ref['heads_run'], 'duet-heads', revision, ref['heads_manifest_sha256'])
    words = prior(ref['words_run'], 'duet-words', revision, ref['words_manifest_sha256'])
    sources = [verified_path(words, f'artifacts/{name}') for name in ('word-inputs.json', 'diagnostic/show.json',
        'diagnostic/mix.wav', 'diagnostic/melody-1.json', 'diagnostic/melody-2.json')]
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    names = ('src/ui/mouthWords.ts', 'src/ui/components/DuetPage.tsx', 'src/ui/components/AnatomyView3D.tsx',
             'src/ui/render/anatomy.ts', 'src/ui/render/anatomy3d.ts', 'src/ui/render/vector.ts', 'src/show/words.ts',
             'tests/words.test.ts', 'tests/transport.test.ts')
    details = {'case_id': spec['id'], 'upstream_revision': revision,
        'upstream_source_sha256': {name: sha256(UPSTREAM / name) for name in names},
        'bun': subprocess.check_output([*bun, '--version'], text=True).strip()}
    inputs = [CASE, CAPTURE, Path(__file__), Path(shared.__file__),
        *(run[0] / 'manifest.json' for run in (heads, words)), *sources, *sorted(DEMO.iterdir()),
        *web_sources(), *shared.candidate_sources()]
    return shared.record_measurement(args.run_id, CASE, inputs, details,
        lambda artifacts, execute: measure(spec, artifacts, execute, bun, sources[0].parent),
        command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
