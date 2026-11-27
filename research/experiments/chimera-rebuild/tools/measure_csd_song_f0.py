"""CSDの同じ音符窓で録音と両合成のF0を測る。"""

import argparse
from collections import Counter
import csv
import math
import os
from pathlib import Path
import subprocess
import wave

import numpy as np

from measure_csd_continuous_song import delta, pcm_bits_equal, samples
import measure_speech_timing as timing
import measure_uniform_tube as shared
from measure_vowel_voice import independent_yin
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/csd-acoustic-f0-en001a.json'
SOURCE = WORKSPACE / 'cases/csd-song-planning.json'
LABELS = ('recording', 'upstream', 'candidate')


def midi_to_hz(midi):
    return 440 * math.exp2((midi - 69) / 12)


def gate_level(pcm, rate, config):
    n = math.floor(rate * config['envelope_seconds'] + .5)
    complete = len(pcm) // n * n
    energy = np.mean(pcm[:complete].reshape(-1, n)**2, axis=1)
    if complete < len(pcm):
        energy = np.r_[energy, np.mean(pcm[complete:]**2)]
    db = np.maximum(10 * np.log10(energy + 1e-30), config['envelope_floor_db'])
    k = len(db) * config['gate_percentile'] // 100
    return 10 ** ((float(np.partition(db, k)[k]) - config['gate_drop_db']) / 10)


class NotePitch:
    def __init__(self, pcm, rate, piece_min_midi, config):
        self.pcm = pcm.astype(float, copy=False)
        self.rate = rate
        self.gate = gate_level(self.pcm, rate, config)
        self.search_range = math.exp2(config['search_half_width_semitones'] / 12)
        self.width = math.floor(config['yin_minimum_periods'] * rate / midi_to_hz(
            piece_min_midi - config['search_half_width_semitones']) + .5)
        self.threshold = config['yin_threshold']

    def at(self, t, target, *, upper_ratio=None, include_gated_aperiodicity=False):
        first = int(t * self.rate) - self.width // 2
        last = first + self.width
        if first < 0 or last > len(self.pcm):
            return 'outside_wave', None, None, 1.0 if include_gated_aperiodicity else None
        window = self.pcm[first:last]
        power = float(np.mean(window**2))
        below_gate = power < self.gate
        if below_gate and not include_gated_aperiodicity:
            return 'below_energy_gate', None, power, None
        upper = self.search_range if upper_ratio is None else upper_ratio
        hz, aperiodicity = independent_yin(window, self.rate, {
            'pitch_min_hz': target / self.search_range, 'pitch_max_hz': target * upper,
            'yin_threshold': self.threshold,
        })
        if below_gate:
            return 'below_energy_gate', None, power, aperiodicity
        return ('unvoiced_period' if hz is None else 'voiced'), hz, power, aperiodicity


def measurement_windows(note, config):
    left, right = config['melisma_window'] if note['melisma'] else config['regular_window']
    length = note['end'] - note['start']
    a = note['start'] + left * length
    b = note['end'] - right * length
    hop = config['hop_seconds']
    return (a, b), [a + i * hop for i in range(math.floor((b-a)/hop) + 1)]


def measure_notes(annotations, estimators, config, output):
    notes = []
    fields = ('note_index', 'time_seconds', 'signal', 'status', 'f0_hz', 'mean_square', 'aperiodicity')
    with output.open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(fields)
        for i, note in enumerate(annotations):
            target = midi_to_hz(note['midi'])
            bounds, centers = measurement_windows(note, config)
            record = {'note_index': i, 'midi': note['midi'], 'target_hz': target, 'annotation_seconds':
                      [note['start'], note['end']], 'ipa': note['ipa'], 'window_seconds': bounds,
                      'frame_count': len(centers), 'signals': {}}
            for label, estimator in estimators.items():
                values = []
                counts = Counter()
                for t in centers:
                    status, hz, power, aper = estimator.at(t, target)
                    writer.writerow((i, t, label, status, hz, power, aper))
                    counts[status] += 1
                    if hz is not None:
                        values.append(hz)
                cents = [1200 * math.log2(hz / target) for hz in values]
                record['signals'][label] = {'median_f0_hz': float(np.median(values)) if values else None,
                                            'median_cents_vs_score': float(np.median(cents)) if cents else None,
                                            'voiced_share': len(values) / len(centers),
                                            'frames_by_status': dict(sorted(counts.items()))}
            notes.append(record)
    return notes


def reference_error(notes, official, config):
    report = {}
    for label, key in [('recording', 'human'), ('upstream', 'synth')]:
        absent, cents_diff, voiced_diff = [], [], []
        for row, original in zip(notes, official, strict=True):
            actual, saved = row['signals'][label], original[key]
            a, b = actual['median_cents_vs_score'], saved['cents']
            if (a is None) != (b is None):
                absent.append(row['note_index'])
            elif a is not None:
                cents_diff.append(abs(a-b))
            voiced_diff.append(abs(actual['voiced_share'] - saved['voiced']))
        report[label] = {'missing_note_mismatches': absent, 'maximum_cents_error': max(cents_diff, default=None),
                         'maximum_voiced_share_error': max(voiced_diff)}
    available = all(not r['missing_note_mismatches'] and r['maximum_cents_error'] is not None
                    and r['maximum_cents_error'] <= config['published_cents_tolerance']
                    and r['maximum_voiced_share_error'] <= config['published_voiced_share_tolerance'] for r in report.values())
    return available, report


def known_periods(config, rates):
    f0 = config['known_tone_hz']
    controls = {}
    for rate in sorted(set(rates)):
        wave_data = .2 * np.sin(2 * np.pi * f0 * np.arange(rate) / rate)
        wave_data[:rate//4] = 0
        midi = 69 + 12 * math.log2(f0 / 440)
        estimator = NotePitch(wave_data, rate, midi, config)
        status, hz, _, _ = estimator.at(.5, f0)
        quiet, _, _, _ = estimator.at(.1, f0)
        outside, _, _, _ = estimator.at(0, f0)
        controls[rate] = {'tone_f0_hz': hz, 'silence_status': quiet, 'beginning_status': outside,
                          'passed': status == 'voiced' and abs(hz-f0) <= config['known_tone_tolerance_hz']
                                    and quiet == 'below_energy_gate' and outside == 'outside_wave'}
    return controls


def song_statistics(notes):
    summaries = {}
    for name in LABELS:
        all_values = [row['signals'][name]['median_cents_vs_score'] for row in notes]
        finite = [v for v in all_values if v is not None]
        counts = Counter()
        for row in notes:
            counts.update(row['signals'][name]['frames_by_status'])
        summaries[name] = {'notes_with_f0': len(finite), 'frames_by_status': dict(sorted(counts.items())),
                           'median_signed_cents_vs_score': float(np.median(finite)) if finite else None,
                           'median_abs_cents_vs_score': float(np.median(np.abs(finite))) if finite else None}
    scored = [row for row in notes if all(row['signals'][label]['median_cents_vs_score'] is not None for label in LABELS)]
    summaries['common_notes'] = len(scored)
    pairs = [('upstream', 'recording'), ('candidate', 'recording'), ('candidate', 'upstream')]
    for a, b in pairs:
        differences = [row['signals'][a]['median_cents_vs_score'] - row['signals'][b]['median_cents_vs_score']
                       for row in scored]
        summaries[f'{a}_vs_{b}'] = {'median_signed_cents': float(np.median(differences)) if differences else None,
                                   'median_abs_cents': float(np.median(np.abs(differences))) if differences else None,
                                   'max_abs_cents': max(map(abs, differences), default=None)}
    return summaries


def render_song(case, sources, out, execute):
    config = case['render']
    original = timing.read(sources['prefix_case'])
    scores = timing.read(sources['song_inputs'])['song_plan']['scores']
    scores = [row for row in scores if row['id'].rsplit('-', 1)[0] == case['song']]
    if len(scores) != config['phrases'] or sum(len(p['notes']) for p in scores) != config['notes']:
        raise ValueError('登録した曲の句数または音符数が一致しません')
    prepared = out / 'candidate-case.json'
    timing.write(prepared, {'song_voice': {**original['song_voice'], 'scores': scores,
                                           'render_end_seconds': config['output_frames']/config['sample_rate_hz']}})
    execute(['cargo', 'build', '--locked', '--offline', '--release', '-p', 'vocal-cli'])
    cli = str(WORKSPACE / 'target/release/vocal-cli')
    inspect = out / 'candidate-inspect.json'
    execute([cli, 'inspect', str(prepared)], stdout=inspect)
    prim, alt = (out / 'candidate.wav', out.parent / 'tmp' / 'candidate-alternate.wav')
    for path, block in zip((prim, alt), config['host_block_frames'], strict=True):
        execute([cli, 'render-pcm', str(prepared), str(path), '--no-trace', str(block)], cwd=out)
    short = out.parent / 'tmp' / 'candidate-no-trace-short.wav'
    execute([cli, 'render-pcm', str(sources['prefix_case']), str(short), '--no-trace',
             str(config['host_block_frames'][0])], cwd=out)
    wav_hashes = {'candidate': sha256(prim), 'alternate': sha256(alt),
                  'short_no_trace': sha256(short), 'short_before': sha256(sources['prefix_pcm'])}
    for path, a, b in ((alt, 'candidate', 'alternate'), (short, 'short_no_trace', 'short_before')):
        if wav_hashes[a] == wav_hashes[b]:
            path.unlink()
        else:
            path.rename(out / path.name)
    prefix_wave, prefix_frames = sources['prefix_pcm'], sources['prefix_frames']
    if config.get('prefix_from_current_score'):
        prefix_frames = config['same_prefix_frames']
        prefix_case = out / 'candidate-timed-prefix.json'
        prefix_wave = out / 'candidate-timed-prefix.wav'
        payload = timing.read(prepared)
        payload['song_voice']['render_end_seconds'] = prefix_frames / config['sample_rate_hz']
        timing.write(prefix_case, payload)
        execute([cli, 'render-pcm', str(prefix_case), str(prefix_wave), '--no-trace',
                 str(config['host_block_frames'][0])], cwd=out)
    return prim, timing.read(inspect), wav_hashes, prefix_wave, prefix_frames


def plot_notes(song, notes, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import fontManager

    font = Path('/Library/Fonts/Arial Unicode.ttf')
    if font.is_file():
        fontManager.addfont(font)
        plt.rcParams['font.family'] = ['Arial Unicode MS', 'DejaVu Sans']
    fig, (top, detail, bottom) = plt.subplots(3, 1, sharex=True, figsize=(10.5, 7.6), layout='constrained')
    x = [row['annotation_seconds'][0] for row in notes]
    for key, label, color, mark in zip(LABELS, ('録音', '固定上流', '再実装'),
                                      ('#66646b', '#174b9e', '#a22d32'), ('o', '+', 'x'), strict=True):
        values = np.asarray([row['signals'][key]['median_cents_vs_score'] for row in notes], dtype=float)
        for axis in (top, detail):
            axis.scatter(x, values, label=label, color=color, s=18, marker=mark)
        bottom.scatter(x, [100 * row['signals'][key]['voiced_share'] for row in notes],
                       color=color, s=15, marker=mark)
    top.axhline(0, color='#8f8b90', lw=.7)
    top.set_ylabel('譜面とのF0差 (セント)')
    top.legend(loc='upper right', frameon=False)
    detail.axhline(0, color='#8f8b90', lw=.7)
    detail.set_ylim(-125, 125)
    detail.set_ylabel('中央部の拡大 (セント)')
    bottom.set_ylabel('窓内の有声フレーム (%)')
    bottom.set_xlabel('注釈の音符開始時刻 (秒)')
    fig.suptitle(f'CSD {song}  音符ごとの実測F0と有声率')
    fig.savefig(output, dpi=145)
    plt.close(fig)


def measurement(case, sources, recording, out, execute):
    config = case['measurement']
    capture = case['render']
    f0_file, inspect, wav_hashes, prefix_file, prefix_frames = render_song(case, sources, out, execute)
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::'],
            cwd=UPSTREAM, stdout=out / 'fixed-compare-tests.log')
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'golden_analysis'],
            cwd=UPSTREAM, stdout=out / 'fixed-analysis-tests.log')
    rate, total = capture['sample_rate_hz'], capture['output_frames']
    synth = samples(f0_file, rate, total)
    upper = samples(sources['reference_pcm'], rate, total)
    prefix = samples(prefix_file, rate, prefix_frames)
    n = capture['same_prefix_frames']
    normal_delta = delta(synth, upper, tolerance=config['pcm_diagnostic_tolerance'])
    with wave.open(str(recording), 'rb') as audio:
        recording_rate, recording_count = audio.getframerate(), audio.getnframes()
        if (audio.getnchannels(), audio.getsampwidth()) != (2, 2):
            raise ValueError('録音の2チャンネル・PCM16条件が一致しません')
        pcm = np.frombuffer(audio.readframes(recording_count), dtype='<i2').reshape(-1, 2)
    mono = pcm.astype(float).mean(axis=1) / 32768
    report, = [x for x in timing.read(sources['reference_report'])['songs']
               if x['summary']['id'] == case['song']]
    annotation = report['notes']
    nominal = [n for p in inspect['song']['scores'] for n in p['plan']['notes']]
    measured_mask = [abs(x['nucleus_start_seconds']-row['start']) <= config['alignment_tolerance_seconds']
                     for x, row in zip(nominal, annotation, strict=True)]
    comparison = {key: NotePitch(signal, fs, min(x['midi'] for x in annotation), config)
                  for key, signal, fs in zip(LABELS, (mono, upper, synth), (recording_rate, rate, rate), strict=True)}
    notes = measure_notes(annotation, comparison, config, out / 'note-f0-frames.csv')
    for row, aligned in zip(notes, measured_mask, strict=True):
        row['included_in_summary'] = aligned
    plot_notes(case['song'], notes, out / 'note-f0.png')
    agrees, reference_deltas = reference_error(notes, annotation, config)
    statistics = song_statistics([row for row in notes if row['included_in_summary']])
    controls = known_periods(config, (rate, recording_rate))
    return {
        'checks': {
            'recording_and_render_frames': (recording_rate, recording_count, len(mono)) ==
                                           (capture['recording_rate_hz'], capture['recording_frames'], capture['recording_frames'])
                                           and inspect['output_frames'] == total,
            'all_registered_notes_and_alignment': len(notes) == capture['notes']
                and measured_mask == [row['aligned'] for row in annotation]
                and all(abs(x['beat_seconds'] - row['start']) <= 1e-10 and x['note']['midi'] == row['midi']
                        for x, row in zip(nominal, annotation, strict=True)),
            'host_block_pcm_exact': wav_hashes['candidate'] == wav_hashes['alternate'],
            'csv_omission_pcm_exact': wav_hashes['short_no_trace'] == wav_hashes['short_before']
                                      and not (out / '--no-trace').exists(),
            'same_registered_prefix': pcm_bits_equal(synth[:n], prefix[:n]),
            'known_tone_and_missing_windows': all(x['passed'] for x in controls.values()),
            'matches_published_reference_f0_and_coverage': agrees,
            'candidate_coverage': statistics['candidate']['notes_with_f0'] >= config['minimum_candidate_notes_with_f0'],
        },
        'song': case['song'], 'split': case['split'],
        'phrases': len(inspect['song']['scores']), 'frames': total, 'wave_hashes': wav_hashes,
        'gates': {k: {'power': x.gate, 'window_frames': x.width} for k, x in comparison.items()},
        'pcm_first_difference_candidate_vs_upstream': normal_delta,
        'published_reference_differences': reference_deltas,
        'controls': controls,
        'statistics': statistics,
        'notes': notes,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case', type=Path, default=CASE)
    args = parser.parse_args()
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('計測は作業用ディスクを指定してください')
    case_path = args.case.resolve()
    case = timing.read(case_path)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('差分のない固定上流版を用意してください')
    source, prefix = (WORKSPACE / 'runs' / case[key] for key in ('source_run', 'prefix_run'))
    relative = {
        'song_inputs': (source, 'artifacts/song-inputs.json'),
        'reference_report': (source, 'artifacts/csd/report.json'),
        'reference_pcm': (source, f"artifacts/csd/{case['song']}-synth.wav"),
        'prefix_case': (prefix, 'artifacts/candidate-short-128.json'),
        'prefix_pcm': (prefix, 'artifacts/candidate-short-128.wav'),
    }
    manifests = {run: timing.read(run / 'manifest.json') for run in (source, prefix)}
    sources = {}
    for key, (run, name) in relative.items():
        path = run / name
        row, = [r for r in manifests[run]['outputs'] if r['path'] == name]
        if sha256(path) != row['sha256']:
            parser.error(f'基準成果が先行実行と一致しません ({name})')
        sources[key] = path
        if key == 'prefix_pcm':
            sources['prefix_frames'] = row['frames']
    selection = timing.read(SOURCE)
    if {'id': case['song'], 'split': case['split']} not in selection['songs']:
        parser.error('計測曲と調整用・確認用の区分が登録と一致しません')
    name = f"CSD/english/wav/{case['song']}.wav"
    recording = Path(selection['dataset']['work_root']) / name
    registered = manifests[source]['dataset']['files'][name]
    if sha256(recording) != registered['sha256']:
        parser.error('録音が先行実行の記録と一致しません')
    python = [Path(__file__).resolve(), *(WORKSPACE / 'tools' / name for name in
              ('measure_csd_continuous_song.py', 'measure_vowel_voice.py', 'measure_speech_timing.py', 'measure_uniform_tube.py'))]
    inputs = [case_path, SOURCE, *python, *(run / 'manifest.json' for run in manifests),
              *(path for path in sources.values() if isinstance(path, Path)), *shared.candidate_sources()]
    return shared.record_measurement(args.run_id, case_path, inputs,
        {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
         'recording': {'path': str(recording), **registered}},
        lambda out, execute: measurement(case, sources, recording, out, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
