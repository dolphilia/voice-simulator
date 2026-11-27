"""TSP録音のF2注釈資料を生成し、回答を元の観測窓へ対応付ける。"""

import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import random
import re
from statistics import median
import subprocess
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.io import wavfile

from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_tsp_stressed_vowel_formants import open_run, read
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


ROOT = WORKSPACE.parents[2]
CASE = WORKSPACE / 'cases/tsp-f2-annotation.json'
PAGE = WORKSPACE / 'tools/tsp-f2-annotation.html'
BROWSER = ROOT / 'web/prototypes/chimera-research/tools/verify-tsp-f2-annotation.mjs'
COLUMNS = ('packet_id', 'trial', 'status', 'f2_hz', 'note')
STATUSES = ('measured', 'ambiguous', 'unusable', 'unanswered')


def save_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')


def control_pcm(wave):
    return np.rint(wave * (0.85 * 32767 / np.max(np.abs(wave)))).astype(np.int16)


def make_trials(case, references):
    windows = read(references['windows'])['windows']
    alignments = read(references['alignment'])['intervals']
    analysis_rate = case['analysis_rate_hz']
    frames = case['analysis_window_samples']
    if len(windows) != case['recording_windows']:
        raise ValueError('録音の観測窓数が登録と一致しません')
    waves = {uid: wavfile.read(references[uid]) for uid in {w['utterance'] for w in windows}}
    for row in windows:
        uid = row['utterance']
        begin, end = row['interval_seconds']
        rate, pcm = waves[uid]
        window = row['start_sample'], row['start_sample'] + frames
        expected_start = int((begin + row['center'] * (end - begin)) * analysis_rate) - frames // 2
        if (rate != 4 * analysis_rate or pcm.dtype != np.int16 or pcm.ndim != 1
                or [begin, end, row['arpabet']] != alignments[uid]['phones'][row['phone_index']]
                or window[0] != expected_start or row['frame_samples'] != frames
                or not begin <= window[0] / analysis_rate < window[1] / analysis_rate <= end):
            raise ValueError(f'録音の標本位置または母音境界が登録と一致しません ({uid})')
        yield ({'kind': 'recording', 'utterance': uid, 'word': row['word'], 'center': row['center'],
                'phone_seconds': [begin, end], 'analysis_samples': list(window),
                'held_out_lpc_f2_hz': [variant['fixed_selection']['f2'][0]
                                       if variant['fixed_selection']['f2'] else None for variant in row['variants']]},
               rate, pcm)

    control = np.load(references['control_wave'], allow_pickle=False)
    expected = case['synthetic_f2_hz']
    model_poles = read(references['control_summary'])['model_poles_hz']['narrow-f2']
    if (control.ndim != 1 or not np.isfinite(control).all() or not np.max(np.abs(control))
            or model_poles[1][0] != expected):
        raise ValueError('合成対照が登録済みの波形・極と一致しません')
    center = case['synthetic_center_sample']
    yield ({'kind': 'synthetic', 'phone_seconds': case['synthetic_phone_seconds'],
            'analysis_samples': [center - frames // 2, center + frames // 2], 'known_f2_hz': expected},
           analysis_rate, control_pcm(control))


def power_spectrum(samples, rate):
    nfft = 1 << (4 * samples.shape[-1] - 1).bit_length()
    windowed = samples * np.hanning(samples.shape[-1])
    transform = np.fft.rfft(windowed, n=nfft, axis=-1)
    return np.fft.rfftfreq(nfft, 1 / rate), abs(transform)**2, windowed, transform


def relative_db(power):
    return 10 * np.log10(np.maximum(power / np.max(power), 1e-9))


def average_spectrum(samples, rate, duration, interval, hop):
    positions = np.arange(math.ceil(interval[0] * rate), math.floor(interval[1] * rate) - duration + 1, hop)
    frequencies, curves, _, _ = power_spectrum(samples[positions[:, None] + np.arange(duration)], rate)
    return frequencies, np.mean(curves, axis=0)


def render_trial(case, info, rate, pcm, wav, png):
    begin, end = info['phone_seconds']
    context = case['phone_context_ms'] / 1000
    first = max(0, math.floor((begin - context) * rate))
    stop = min(len(pcm), math.ceil((end + context) * rate))
    audio = pcm[first:stop]
    wavfile.write(wav, rate, audio)
    decoded_rate, decoded = wavfile.read(wav)
    time = np.arange(len(audio)) / rate
    x = audio.astype(np.float64) / 32768
    phone = np.array([begin, end]) - first / rate
    focus = np.array(info['analysis_samples']) / case['analysis_rate_hz'] - first / rate

    length = round(rate * case['wideband_window_ms'] / 1000)
    hop = round(rate * case['hop_ms'] / 1000)
    starts = np.arange(0, len(x) - length + 1, hop)
    f_short, p_short, _, _ = power_spectrum(x[starts[:, None] + np.arange(length)], rate)
    t_short = (starts + (length - 1) / 2) / rate
    focus_start, focus_end = np.rint(focus * rate).astype(int)
    f_long, p_long, windowed, transform = power_spectrum(x[focus_start:focus_end], rate)
    nfft = (len(f_long) - 1) * 2
    bins = np.searchsorted(f_long, (250, 1000, case['synthetic_f2_hz'], 3500))
    direct = np.exp(-2j * np.pi * bins[:, None] * np.arange(len(windowed)) / nfft) @ windowed
    dft_error = float(np.max(abs(transform[bins] - direct)) / np.sum(abs(windowed)))
    peak = None
    if info['kind'] == 'synthetic':
        # 窓と周期インパルスの相対位置による凹凸を平均してから帯域ピークを読む。
        frequency, power = average_spectrum(x, rate, focus_end - focus_start, phone, hop)
        band = (frequency >= case['synthetic_peak_search_hz'][0]) & (frequency <= case['synthetic_peak_search_hz'][1])
        peak = float(frequency[band][np.argmax(power[band])])

    fig = plt.figure(figsize=(9.8, 4.6), layout='constrained')
    grid = fig.add_gridspec(2, 2, width_ratios=(3, 1.25), height_ratios=(1, 3))
    wave = fig.add_subplot(grid[0, 0])
    spectrogram = fig.add_subplot(grid[1, 0], sharex=wave)
    spectrum = fig.add_subplot(grid[1, 1], sharey=spectrogram)
    ms = 1000
    wave.plot(time * ms, x, color='#234b61', linewidth=.7)
    heat = spectrogram.pcolormesh(t_short * ms, f_short, relative_db(p_short).T, vmin=-55,
                                  vmax=0, cmap='magma', shading='nearest')
    for axis in (wave, spectrogram):
        axis.axvspan(focus[0] * ms, focus[1] * ms, color='#74d9e5', alpha=.23, linewidth=0)
        for boundary in phone:
            axis.axvline(boundary * ms, color='#637477' if axis == wave else '#eeeeee', linestyle='--', linewidth=.8)
    spectrum.plot(relative_db(p_long), f_long, color='#234b61')
    spectrum.grid(alpha=.25)
    wave.set_ylabel('PCM')
    spectrogram.set(xlabel='t [ms]', ylabel='f [Hz]', xlim=(0, len(x) * ms / rate), ylim=case['visible_range_hz'])
    spectrum.set(xlabel='dB (relative)', xlim=(-55, 2))
    fig.colorbar(heat, ax=[wave, spectrogram], label='dB (relative)')
    fig.savefig(png, dpi=150)
    plt.close(fig)

    return {'clip_start_sample': first, 'clip_frames': len(audio), 'sample_rate_hz': rate,
            'focus_ms': (focus * ms).tolist(), 'decoded_pcm_equal': decoded_rate == rate and np.array_equal(decoded, audio),
            'dft_scaled_error': dft_error, 'control_peak_hz': peak}


def panel(trial, focus, limits):
    return f'''<section data-trial="{trial}">
    <h2>{trial}　{focus[0]:.1f}–{focus[1]:.1f} ms</h2>
    <audio controls preload="metadata" src="{trial}.wav" aria-label="{trial}の音声"></audio>
    <a href="{trial}.png" target="_blank" aria-label="{trial}の図を拡大"><img src="{trial}.png"
      alt="波形、スペクトログラム、25ミリ秒区間のスペクトル。破線は母音区間の境界。"></a>
    <div class="fields"><label>判定 <select><option value="">未回答</option>
      <option value="measured">測定できる</option><option value="ambiguous">判断困難</option>
      <option value="unusable">音声・区間が不適</option></select></label>
      <label>F2 (Hz) <input type="number" min="{limits[0]}" max="{limits[1]}" step="any" disabled></label></div>
    <label>根拠・判定できなかった理由<textarea></textarea></label>
  </section>'''


def encode_csv(rows):
    buffer = io.StringIO(newline='')
    writer = csv.writer(buffer)
    writer.writerow(COLUMNS)
    writer.writerows(rows)
    return buffer.getvalue().encode('utf-8-sig')


def parse_response(blob, key, limits):
    reader = csv.reader(io.StringIO(blob.decode('utf-8-sig'), newline=''), strict=True)
    if tuple(next(reader, ())) != COLUMNS:
        raise ValueError('CSVの列名が注釈資料の形式と一致しません')
    rows = {}
    for row in reader:
        if len(row) != len(COLUMNS):
            raise ValueError('CSVの列数が一致しません')
        packet, trial, status, frequency, note = row
        if packet != key['packet_id'] or trial not in key['trials'] or trial in rows:
            raise ValueError('資料IDまたは観測窓IDが不明、または観測窓が重複しています')
        if status and (status not in STATUSES[:-1] or not note.strip()):
            raise ValueError('判定状態または判定理由が不正です')
        value = float(frequency) if status == 'measured' else None
        if ((value is None and frequency)
                or (value is not None and not (math.isfinite(value) and limits[0] <= value <= limits[1]))):
            raise ValueError('F2は測定できたときにだけ、有効な周波数を記録してください')
        rows[trial] = {'status': status or 'unanswered', 'f2_hz': value, 'note': note}
    return rows


def summarize(key, responses, tolerance):
    result = {}
    for trial in key['trials']:
        counts = dict.fromkeys(STATUSES, 0)
        frequencies = []
        for response in responses.values():
            row = response.get(trial)
            counts[row['status'] if row else 'unanswered'] += 1
            if row and row['status'] == 'measured':
                frequencies.append(row['f2_hz'])
        spread = max(frequencies) - min(frequencies) if len(frequencies) >= 2 else None
        result[trial] = {'counts': counts, 'median_hz': median(frequencies) if frequencies else None,
                         'range_hz': spread, 'within_rater_agreement': None if spread is None else spread <= tolerance}
    return result


def validate_packet(case, key, page, template, out, execute):
    response = out / 'browser-fixture.csv'
    execute(['node', str(BROWSER), str(page), str(response)], stdout=out / 'browser-checks.json')
    ids = list(key['trials'])
    packet = key['packet_id']
    second = encode_csv([(packet, ids[0], 'measured', 2070, '同じ帯を追跡'),
                         (packet, ids[3], 'measured', 1900, '上の帯から読んだ')])
    (out / 'second-fixture.csv').write_bytes(second)
    limits = case['f2_range_hz']
    first = parse_response(response.read_bytes(), key, limits)
    other = parse_response(second, key, limits)
    fixture = summarize(key, {'browser': first, 'second': other}, case['rater_agreement_hz'])
    save_json(out / 'synthetic-consensus.json', {'data_kind': 'synthetic', 'trials': fixture})
    blank = parse_response(template.read_bytes(), key, limits)
    good = (packet, ids[0], 'measured', 2000, '帯が見える')
    rejects = {'duplicate': [good, good], 'wrong_packet': [('elsewhere', *good[1:])],
               'nonfinite': [(*good[:3], 'NaN', good[4])]}
    rejected = []
    for reason, rows in rejects.items():
        try:
            parse_response(encode_csv(rows), key, limits)
        except ValueError:
            rejected.append(reason)
    return {
        'browser_and_export': all(read(out / 'browser-checks.json')['checks'].values())
        and first[ids[0]]['note'] == '帯の連続, "比較"\n中央窓',
        'synthetic_agreement_and_disagreement': fixture[ids[0]]['range_hz'] == 70
        and fixture[ids[0]]['within_rater_agreement'] is True and fixture[ids[0]]['median_hz'] == 2035
        and fixture[ids[3]]['range_hz'] == 200 and fixture[ids[3]]['within_rater_agreement'] is False,
        'synthetic_missing_and_uncertain': fixture[ids[1]]['counts']['ambiguous'] == 1
        and fixture[ids[2]]['counts']['unusable'] == 1 and fixture[ids[-1]]['counts']['unanswered'] == 2
        and all(row['status'] == 'unanswered' for row in blank.values()),
        'invalid_responses_are_rejected': rejected == list(rejects),
    }


def prepare(case, references, out, execute):
    folder = out / 'review'
    folder.mkdir()
    trials = list(make_trials(case, references))
    random.Random(case['shuffle_seed']).shuffle(trials)
    key, panels = {}, []
    for index, (info, rate, audio) in enumerate(trials, start=1):
        trial = f'W{index:02}'
        wav, png = folder / f'{trial}.wav', folder / f'{trial}.png'
        observed = render_trial(case, info, rate, audio, wav, png)
        key[trial] = {**info, **observed, 'wave_sha256': sha256(wav), 'plot_sha256': sha256(png)}
        panels.append(panel(trial, observed['focus_ms'], case['f2_range_hz']))
    packet = hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()
    private = {'packet_id': packet, 'trials': key}
    save_json(out / 'reference.json', private)
    page = folder / 'index.html'
    page.write_text(PAGE.read_text().replace('<!--TRIALS-->', '\n'.join(panels)).replace('__PACKET_ID__', packet))
    template = folder / 'observations.csv'
    template.write_bytes(encode_csv((packet, trial, '', '', '') for trial in key))

    peak, = (row['control_peak_hz'] for row in key.values() if row['kind'] == 'synthetic')
    peak_error = abs(peak - case['synthetic_f2_hz'])
    dft_peak = max(row['dft_scaled_error'] for row in key.values())
    expected_public_files = {'index.html', 'observations.csv'} | {f'{tid}.{suffix}' for tid in key for suffix in ('wav', 'png')}
    checks = {'recording_window_and_pcm': len(key) == case['recording_windows'] + 1
              and all(row['decoded_pcm_equal'] and abs(row['focus_ms'][1] - row['focus_ms'][0] - 25) < 1e-8
                      for row in key.values()),
              'dft_matches_display_fft': dft_peak <= case['direct_dft_scaled_error'],
              'synthetic_control_peak': peak_error <= case['synthetic_peak_tolerance_hz'],
              'review_only_has_blind_material': {path.name for path in folder.iterdir()} == expected_public_files
              and all(name not in page.read_text() for name in ('seems', 'again', 'narrow-f2', 'held_out_lpc_f2_hz'))}
    checks.update(validate_packet(case, private, page, template, out, execute))
    return {'checks': checks, 'packet_id': packet, 'review_windows': len(key), 'human_responses': 0,
            'max_dft_scaled_error': dft_peak, 'control_peak_hz': peak, 'control_peak_error_hz': peak_error,
            'matplotlib': matplotlib.__version__}


def answered_rows(response):
    # 空欄行の有無やCSVの行順と切り離して、判定内容を比較する。
    return {trial: (row['status'], row['f2_hz'], row['note'].replace('\r\n', '\n').replace('\r', '\n').strip())
            for trial, row in response.items() if row['status'] != 'unanswered'}


def validate_human_responses(parsed, fixtures):
    known = [answered_rows(response) for response in fixtures]
    for name, response in parsed.items():
        answers = answered_rows(response)
        if not answers:
            raise ValueError(f'{name} に記入済みの注釈がありません')
        if answers in known:
            raise ValueError(f'{name} は試験用回答と一致するため、人の注釈として登録できません')


def collect(case, key, blobs, data_kind, out, fixture_paths=()):
    limits = case['f2_range_hz']
    try:
        parsed = {name: parse_response(blob, key, limits) for name, blob in blobs.items()}
        if data_kind == 'human':
            fixtures = [parse_response(path.read_bytes(), key, limits) for path in fixture_paths]
            validate_human_responses(parsed, fixtures)
    except (csv.Error, UnicodeError, ValueError) as error:
        raise ValueError(f'注釈CSVを読み込めません ({error})') from error
    originals = out / 'responses'
    originals.mkdir()
    for name, blob in blobs.items():
        (originals / f'{name}.csv').write_bytes(blob)
    result = summarize(key, parsed, case['rater_agreement_hz'])
    matched = {trial: {**row, 'reference': key['trials'][trial]} for trial, row in result.items()}
    recorded = dict.fromkeys(STATUSES[:-1], 0)
    for row in matched.values():
        if row['reference']['kind'] == 'recording':
            for status in recorded:
                recorded[status] += row['counts'][status]
    save_json(out / 'responses.json', parsed)
    return {'checks': {'responses_have_valid_packet_and_values': bool(parsed)}, 'data_kind': data_kind,
            'packet_id': key['packet_id'], 'rater_count': len(parsed), 'recording_judgments': recorded, 'trials': matched}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    commands.add_parser('prepare').add_argument('run_id')
    collect_parser = commands.add_parser('collect')
    collect_parser.add_argument('run_id')
    collect_parser.add_argument('--packet', required=True)
    collect_parser.add_argument('--kind', required=True, choices=('human', 'synthetic'))
    collect_parser.add_argument('--response', action='append', required=True, metavar='ID=CSV')
    args = parser.parse_args()
    case = read(CASE)
    rev = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if rev != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    inputs = [CASE, Path(__file__).resolve(), WORKSPACE / 'tools/measure_uniform_tube.py',
              WORKSPACE / 'tools/measure_tsp_stressed_vowel_formants.py', WORKSPACE / 'tools/measure_fan_crossing_allocations.py',
              WORKSPACE / 'tools/upstream_baseline.py']
    metadata = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': rev, 'action': args.action,
                'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    if args.action == 'prepare':
        runs = {name: open_run(case[name], rev) for name in ('windows', 'alignment', 'control')}
        references = {name: verified_path(run, 'summary.json') for name, run in runs.items()}
        for uid in sorted({row['utterance'] for row in read(references['windows'])['windows']}):
            references[uid] = verified_path(runs['alignment'], f'artifacts/corpus/recording/{uid}/{uid}.wav')
        references['control_wave'] = verified_path(runs['control'], 'artifacts/narrow-f2.npy')
        references['control_summary'] = references.pop('control')
        inputs.extend([PAGE, BROWSER, *references.values(), *(run[0] / 'manifest.json' for run in runs.values())])

        def run(out, execute):
            execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'golden_analysis'],
                    cwd=UPSTREAM, stdout=out / 'upstream-golden-analysis.log')
            return prepare(case, references, out, execute)
    else:
        packet = run_manifest(args.packet, case['id'], rev)
        if packet[1]['status'] != 'pass' or packet[1].get('action') != 'prepare':
            parser.error('検証に合格した注釈資料の実行IDを指定してください')
        key_path = verified_path(packet, 'artifacts/reference.json')
        key = read(key_path)
        data = {}
        for response in args.response:
            name, separator, path = response.partition('=')
            if not separator or not path or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', name) or name in data:
                parser.error('重複しない判定者IDとCSVをID=CSVの形式で指定してください')
            source = Path(path).resolve(strict=True)
            if not source.is_file() or source in data.values():
                parser.error('各判定者に異なるCSVファイルを指定してください')
            data[name] = source
        inputs.extend((packet[0] / 'manifest.json', key_path))
        fixture_paths = []
        if args.kind == 'human':
            fixture_paths = [verified_path(packet, f'artifacts/{name}-fixture.csv') for name in ('browser', 'second')]
            inputs.extend(fixture_paths)
        blobs = {name: path.read_bytes() for name, path in data.items()}
        metadata.update(packet_run=args.packet, packet_id=key['packet_id'], data_kind=args.kind, response_files={
            name: {'bytes': len(blob), 'sha256': hashlib.sha256(blob).hexdigest()} for name, blob in blobs.items()})

        def run(out, _execute):
            return collect(case, key, blobs, args.kind, out, fixture_paths)

    return record_measurement(args.run_id, CASE, inputs, metadata, run, command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
