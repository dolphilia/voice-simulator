"""保存済みの歌唱比較から、音源名を伏せた試聴用の音声と記録欄を作る。"""

import argparse
from collections import Counter
import csv
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from fractions import Fraction
from hashlib import sha256 as hash_bytes
from html import escape
import itertools
import json
import math
import os
from pathlib import Path
import random
import sys
import wave

import numpy as np
import scipy
from scipy.signal import resample_poly

from measure_csd_envelope_timing import verified_file, waveforms
from measure_csd_long_notes import load_sources
from measure_csd_song_f0 import LABELS
from measure_speech_timing import read, write
from measure_uniform_tube import record_measurement
from upstream_baseline import WORKSPACE, sha256


CASE = WORKSPACE / 'cases/csd-listening.json'
TEMPLATE = WORKSPACE / 'tools/csd_listening.html'
BROWSER_TEST = WORKSPACE.parents[2] / 'web/prototypes/chimera-research/tools/verify-csd-listening.mjs'
LETTERS = ('A', 'B', 'C')
PCM_SCALE = 32768


def packet_identity(case, key, clips):
    definition = {'case_id': case['id'], 'case_revision': case['revision'],
                  'upstream_revision': case['upstream_revision'],
                  'columns': case['listening']['observations_schema'],
                  'scores': case['listening']['scores'],
                  'key_sha256': sha256(key),
                  'wave_sha256': {path.name: sha256(path) for path in clips}}
    encoded = json.dumps(definition, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return {'packet_id': hash_bytes(encoded).hexdigest(), **definition}


def matched_sources(case, run, manifest, inputs, published):
    baseline = CASE.parent / case['baseline_case']
    inputs.append(baseline)
    selections = load_sources(read(baseline), manifest['selection_run'], manifest['recording_run'], inputs)
    signals = {}
    for split, selected, _, recording, _ in selections:
        song = selected['id']
        fixed = verified_file(run, manifest, f'artifacts/upstream/{song}-synth.wav')
        candidate = verified_file(run, manifest, f'artifacts/{song}/candidate.wav')
        if published[song]['split'] != split:
            raise ValueError('歌唱比較の区分が注釈による選定と一致しません')
        inputs.extend((fixed, candidate))
        signals[song] = (recording, fixed, candidate)
    return signals


def verify_selection(trial, song, alias):
    index = trial['note_index']
    note = song['notes'][index]
    category = trial['category']
    if trial['split'] != song['split'] or note['note_index'] != index or not note['aligned']:
        return False
    if category in ('all_detected', 'recording_without_peak'):
        recording = 'detected' if category == 'all_detected' else 'no_correlation_peak'
        statuses = (recording, 'detected', 'detected')
        selected = next((n['note_index'] for n in song['notes']
                         if n['aligned'] and all(s['eligible'] for s in n['signals'].values())
                         and tuple(n['signals'][name]['status'] for name in LABELS) == statuses), None)
        return selected == index
    if category == 'dental_theta':
        first = next((n['note_index'] for n in song['notes'] if 'θ' in n['ipa']), None)
        return index == first
    if category == 'f0_alias':
        return (trial['song'], index) == (alias['song'], alias['note_index'])
    return False


def frames_for_ms(ms, rate):
    frames, remainder = divmod(ms*rate, 1000)
    if remainder:
        raise ValueError('時間格子が入力・出力のサンプル位置に載りません')
    return frames


def clip_ms(annotation, settings):
    grid = settings['clip_grid_ms']
    start = Decimal(str(annotation['start']))*1000 - settings['before_note_ms']
    stop = Decimal(str(annotation['end']))*1000 + settings['after_note_ms']
    return tuple(int((time/grid).to_integral_value(rounding=direction))*grid
                 for time, direction in ((start, ROUND_FLOOR), (stop, ROUND_CEILING)))


def crop_resample(samples, rate, time_ms, target_rate):
    lo, hi = (frames_for_ms(ms, rate) for ms in time_ms)
    if not 0 <= lo < hi <= len(samples):
        raise ValueError('試聴の切り出し区間が波形の範囲を外れています')
    source = samples[lo:hi].astype(np.float64, copy=False)
    if rate == target_rate:
        return source.copy(), (lo, hi)
    ratio = Fraction(target_rate, rate)
    return resample_poly(source, ratio.numerator, ratio.denominator), (lo, hi)


def stabilize(start_stop, clip_start_ms, rate):
    start, stop = (Decimal(str(value))*rate for value in start_stop)
    origin = frames_for_ms(clip_start_ms, rate)
    return (int(start.to_integral_value(rounding=ROUND_CEILING))-origin,
            int(stop.to_integral_value(rounding=ROUND_FLOOR))-origin)


def fade_ends(samples, frames):
    if frames < 2 or frames*2 >= len(samples):
        raise ValueError('フェードを適用できる区間長がありません')
    weight = .5 - .5*np.cos(np.pi*np.linspace(0, 1, frames))
    samples[:frames] *= weight
    samples[-frames:] *= weight[::-1]


def rms(samples):
    return math.sqrt(float(np.mean(samples**2)))


def to_db(amplitude):
    return 20*math.log10(amplitude)


def common_level(clips, start_stop, settings):
    start, stop = start_stop
    levels = {name: rms(x[start:stop]) for name, x in clips.items()}
    peaks = {name: float(np.max(np.abs(x))) for name, x in clips.items()}
    if any(not math.isfinite(x) or x <= 0 for x in (*levels.values(), *peaks.values())):
        raise ValueError('音量をそろえる区間に有効な信号がありません')
    ceiling = 10**(settings['peak_ceiling_dbfs']/20)
    desired = 10**(settings['target_rms_dbfs']/20)
    target = min(desired, *(ceiling*levels[k]/v for k, v in peaks.items()))
    return target, levels, {k: target/x for k, x in levels.items()}


def write_pcm16(path, signal, rate, stable, settings):
    samples = np.rint(signal * PCM_SCALE)
    if not np.isfinite(samples).all() or samples.min() < -PCM_SCALE or samples.max() >= PCM_SCALE:
        raise ValueError('試聴用PCMで整数範囲を超えました')
    with wave.open(str(path), 'wb') as output:
        output.setparams((1, 2, rate, len(samples), 'NONE', 'not compressed'))
        output.writeframes(samples.astype('<i2').tobytes())
    with wave.open(str(path), 'rb') as output:
        fmt = (output.getnchannels(), output.getsampwidth(), output.getframerate(), output.getnframes())
        pcm = np.frombuffer(output.readframes(fmt[-1]), dtype='<i2').astype(float)/PCM_SCALE
    error = float(np.max(np.abs(pcm-signal))) * PCM_SCALE
    peak = float(np.max(np.abs(pcm)))
    ceiling = 10**(settings['peak_ceiling_dbfs']/20)
    lo, hi = stable
    return {'pcm16_and_length': fmt == (1, 2, rate, len(signal)) and len(pcm) == len(signal),
            'zero_fade_ends': bool(pcm[0] == pcm[-1] == 0),
            'quantization_matches': error <= settings['quantization_error_16bit_lsb'],
            'headroom_matches': peak <= ceiling + .5/PCM_SCALE,
            'peak_dbfs': to_db(peak), 'rms_dbfs': to_db(rms(pcm[lo:hi])), 'quantization_error_lsb': error}


def impulse_check(settings):
    target = settings['output_rate_hz']
    observations = {}
    cut = (100, 400)
    for rate in (44100, 48000):
        signal = np.zeros(frames_for_ms(500, rate))
        signal[frames_for_ms(250, rate)] = 1
        result, boundaries = crop_resample(signal, rate, cut, target)
        observations[str(rate)] = {'peak_frame': int(np.argmax(abs(result))), 'frames': len(result),
                                   'input_frames': boundaries}
    return observations, all(x['peak_frame'] == frames_for_ms(150, target)
                             and x['frames'] == frames_for_ms(300, target) for x in observations.values())


def balanced_orders(seed):
    rng = random.Random(seed)
    names = list(LABELS)
    rng.shuffle(names)
    groups = {}
    for split, base in (('calibration', names), ('held_out', names[::-1])):
        rotations = [tuple(base[i:]+base[:i]) for i in range(len(base))]
        rng.shuffle(rotations)
        groups[split] = iter(rotations)
    return groups


def trial_audio(folder, number, data, window, stable, order, settings):
    rate = settings['output_rate_hz']
    fades = frames_for_ms(settings['fade_ms'], rate)
    length = frames_for_ms(window[1]-window[0], rate)
    left, right = stable
    if not fades <= left < right <= length-fades:
        raise ValueError('音量測定区間が切り出しまたはフェードと重なっています')
    prepared, intervals = {}, {}
    for key, (signal, native_rate) in data.items():
        cropped, input_bounds = crop_resample(signal, native_rate, window, rate)
        if len(cropped) != length or not np.isfinite(cropped).all():
            raise ValueError('変換後の試聴用PCMが登録した長さまたは形式と一致しません')
        fade_ends(cropped, fades)
        prepared[key] = cropped
        intervals[key] = {'rate_hz': native_rate, 'input_frames': input_bounds}
    target, before, gains = common_level(prepared, stable, settings)
    metrics = {}
    for letter, label in zip(LETTERS, order, strict=True):
        filename = folder / f'{number}-{letter}.wav'
        result = write_pcm16(filename, prepared[label]*gains[label], rate, stable, settings)
        metrics[letter] = {**result, 'gain_db': to_db(gains[label]), 'previous_rms_dbfs': to_db(before[label]),
                           **intervals[label]}
    levels = [x['rms_dbfs'] for x in metrics.values()]
    aligned_level = max(levels)-min(levels)
    return {'frame_count': length, 'contexts_ms': window, 'stable_frames': stable, 'target_rms_dbfs': to_db(target),
            'aligned_rms_difference_db': aligned_level, 'labels': metrics}


def html_trial(number, focus, scores):
    choices = '<option value="">未記入</option>' + ''.join(
        f'<option value="{escape(x)}">{escape(x)}</option>' for x in scores)
    abc = '\n'.join(f'''<div class="clip">
        <span class="letter">{label}</span>
        <audio controls preload="none" src="{number}-{label}.wav" aria-label="区間 {number} の {label}"></audio>
        <label>{label}の周期的な揺れ
          <select data-field="{label.lower()}_periodic_pitch">{choices}</select>
        </label>
      </div>''' for label in LETTERS)
    return f'''<section class="trial" data-trial="{number}" aria-labelledby="trial-{number}">
        <h2 id="trial-{number}">区間 {number}</h2>
        <p class="muted">聴き比べる音は {focus[0]:.2f}〜{focus[1]:.2f} 秒付近</p>
        <div class="clips">{abc}</div>
        <div class="details">
          <label>もっとも自然に聞こえた音
            <select data-field="naturalness_preference">
              <option value="">未記入</option><option>A</option><option>B</option><option>C</option>
              <option>差なし</option><option>判定不能</option>
            </select>
          </label>
          <label>音色や入り・終わりで気づいた点
            <textarea data-field="observations"></textarea>
          </label>
        </div>
      </section>'''


def generate(case, summary, report, alias, paths, out, execute):
    audio = case['audio']
    listening = case['listening']
    offset_orders = balanced_orders(listening['order_seed'])
    reference = {r['summary']['id']: r['notes'] for r in report['songs']}
    folder = out / 'listening'
    folder.mkdir()
    trials, key, html_blocks = {}, {}, []
    selected_ok = []
    for song_id, itr in itertools.groupby(case['trials'], key=lambda x: x['song']):
        song = summary['songs'][song_id]
        tracks = waveforms(paths[song_id], song['wave_frames'])
        for trial in itr:
            number = f'{len(trials)+1:02d}'
            note = song['notes'][trial['note_index']]
            annotation = reference[song_id][trial['note_index']]
            window = clip_ms(annotation, audio)
            stable = stabilize(note['stable_seconds'], window[0], audio['output_rate_hz'])
            order = next(offset_orders[trial['split']])
            trials[number] = trial_audio(folder, number, tracks, window, stable, order, audio)
            key[number] = {**trial, 'ipa': note['ipa'], 'annotation_seconds': [annotation['start'], annotation['end']],
                           'labels': dict(zip(LETTERS, order, strict=True))}
            selected_ok.append(verify_selection(trial, song, alias))
            focus = [annotation[k]-window[0]/1000 for k in ('start', 'end')]
            html_blocks.append(html_trial(number, focus, listening['scores']))
    key_path = out / 'listening-key.json'
    write(key_path, key)
    packet = packet_identity(case, key_path, sorted(folder.glob('*.wav')))
    write(out / 'listening-packet.json', packet)
    packet_id = packet['packet_id']
    columns = listening['observations_schema']
    with (folder / 'observations.csv').open('w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(columns)
        writer.writerows((packet_id, number, *([''] * (len(columns)-2))) for number in trials)
    page = (TEMPLATE.read_text().replace('{{TRIALS}}', '\n'.join(html_blocks))
            .replace('{{COLUMNS}}', json.dumps(columns)).replace('{{PACKET_ID}}', packet_id))
    (folder / 'index.html').write_text(page)
    (folder / 'README.md').write_text(
        '# CSD 歌唱の比較試聴\n\nindex.html を開き、各区間のA・B・Cを同じ再生音量で聴きます。'
        '入力した結果は「試聴結果をCSVで保存」から書き出せます。\n\n'
        '0は周期的な音高の揺れを感じない、1は弱い、2ははっきり、3は強いときです。'
        '同梱の observations.csv も記入用に使えます。資料IDは各行に記録されます。'
        '音源の鍵は採点後に開いてください。\n\n'
        '最初の3区間が調整用、後の3区間が確認用です。'
        '録音は Children’s Song Dataset v1.1（Choi, Kim, Park, Yong, Nam, 2020、CC BY-NC-SA 4.0）。'
        '試聴用に切り出し、モノラル化、レートと音量を調整しています。\n\n'
        '[配布版](https://doi.org/10.5281/zenodo.4916302)・'
        '[データセットの説明](https://github.com/equal-singer/CSD)・'
        '[ライセンス](https://creativecommons.org/licenses/by-nc-sa/4.0/)\n')
    impulse, passed = impulse_check(audio)
    per_split = {s: [r['labels'] for r in key.values() if r['split'] == s] for s in ('calibration', 'held_out')}
    outcomes = [z for row in trials.values() for z in row['labels'].values()]
    checks = {
        'registered_trials': len(key) == 6 and all(selected_ok),
        'same_timebase_on_known_impulse': passed,
        'pcm16_fade_and_peak': all(row[x] for row in outcomes for x in (
                                  'pcm16_and_length', 'zero_fade_ends', 'quantization_matches', 'headroom_matches')),
        'matched_levels': all(r['aligned_rms_difference_db'] <= audio['maximum_rms_pair_difference_db']
                              for r in trials.values()),
        'every_source_once_per_position_in_each_split': all(
            Counter(row[p] for row in order) == Counter(LABELS) for order in per_split.values() for p in LETTERS),
        'all_six_play_orders': {tuple(row['labels'].values()) for row in key.values()} == set(itertools.permutations(LABELS)),
        'listener_page_has_no_source_labels': all(s not in page for s in (*reference, 'listening-key.json',
                                                   'candidate.wav', '-synth.wav', 'vibDepth')),
    }
    browser_report = out / 'browser-verification.json'
    execute(['node', str(BROWSER_TEST), str(folder / 'index.html')], stdout=browser_report)
    browser = read(browser_report)
    checks.update(browser['checks'])
    checks['browser_export_matches_packet_id'] = browser['packet_id'] == packet_id
    return {'checks': checks, 'packet_id': packet_id, 'audio': trials, 'impulse_control': impulse,
            'browser_version': browser['browser_version'], 'listener_returned': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('試聴素材は作業用ディスクを指定してください')
    case = read(CASE)
    run = WORKSPACE / 'runs' / case['baseline_run']
    manifest_path = run / 'manifest.json'
    manifest = read(manifest_path)
    alias_root = WORKSPACE / 'runs' / case['alias_control']
    alias_manifest = read(alias_root / 'manifest.json')
    if (manifest['status'] != 'pass' or manifest['upstream_revision'] != case['upstream_revision']
            or alias_manifest['status'] != 'pass' or alias_manifest['baseline_run'] != case['baseline_run']):
        parser.error('固定上流の全曲比較または倍音の対照を検証できません')
    summary = verified_file(run, manifest, 'summary.json')
    report = verified_file(run, manifest, 'artifacts/upstream/report.json')
    alias = verified_file(alias_root, alias_manifest, 'summary.json')
    inputs = [CASE, TEMPLATE, BROWSER_TEST, Path(__file__).resolve(), manifest_path, summary, report, alias,
              alias_root/'manifest.json',
              *(WORKSPACE/'tools'/name for name in ('measure_csd_long_notes.py', 'measure_csd_envelope_timing.py',
                'select_csd_long_notes.py', 'measure_tsp_active_duration.py', 'measure_csd_song_f0.py'))]
    baseline = read(summary)
    paths = matched_sources(case, run, manifest, inputs, baseline['songs'])
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': case['upstream_revision'],
               'baseline_run': case['baseline_run'], 'scipy': scipy.__version__,
               'driver': [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]]}
    return record_measurement(args.run_id, CASE, inputs, details,
        lambda out, execute: generate(case, baseline, read(report), read(alias), paths, out, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
