"""局所制御入口の無変更・一定シフト・内部不変・負例を検査する。"""
import hashlib
import re
import sys
import numpy as np
from campaign import LocalBudget, ROOT, RESULT, BUNDLE, save, digest
sys.path.insert(0, str(BUNDLE))
from hts_core import render_hts
from japanese_frontend import analyze
sys.path.insert(0, str(ROOT))
from local_renderer import StateEngine


def sha(audio):
    return hashlib.sha256(audio.astype('<f8').tobytes()).hexdigest()


def main():
    b = LocalBudget()
    out = RESULT/'entry-audit'
    out.mkdir(exist_ok=False)
    tests = [{'text': '赤い傘。', 'speed': 1.}, {'text': '新しい地図を机に広げた。', 'speed': .85}]
    save(out/'contract.json', {'tests': tests, 'planned_render_calls': 10,
        'constant_shift_half_tone': 2., 'exact_wave_match_required': True,
        'source_hashes': {n: digest(ROOT/n) for n in ('shim.c', 'local_renderer.py', 'entry_audit.py', 'local_hts.dylib')},
        'constant_shift_scope': '既存add_half_toneの内部変更と同じ全状態を変更する入口対照。実験用局所残差では休止・無声を除外する。'})
    rows = []
    for index, test in enumerate(tests):
        row = analyze(test['text'])
        cases = {}
        for case in ('native', 'zero', 'native_plus2', 'constant_plus2', 'local'):
            with b.job('render', '入口照合/'+str(index)+'/'+case, 2_000_000):
                shift = 2. if case == 'native_plus2' else 0.
                if case.startswith('native'):
                    audio = render_hts(row, BUNDLE/'mei_normal.htsvoice', test['speed'], shift)
                    record = {'wave_sha256_float64': sha(audio), 'samples': len(audio)}
                else:
                    with StateEngine(row, BUNDLE/'mei_normal.htsvoice', test['speed']) as engine:
                        before = engine.snapshot()
                        deltas = np.zeros(engine.count)
                        if case == 'constant_plus2':
                            deltas[:] = 2.
                        elif case == 'local':
                            for i, label in enumerate(row['full_context_labels']):
                                phone = re.search(r'\-([^+]+)\+', label).group(1)
                                for state in range(i*5, (i+1)*5):
                                    if phone in ('a', 'i', 'u', 'e', 'o', 'N', 'm', 'n') and before['msd'][state] > .5:
                                        deltas[state] = .5 if i % 2 else -.5
                        engine.modify(deltas)
                        after = engine.snapshot()
                        assert before['duration'] == after['duration'] and before['msd'] == after['msd']
                        assert before['means'][0] == after['means'][0] and before['means'][2] == after['means'][2]
                        assert all(a[1:] == z[1:] for a, z in zip(before['means'][1], after['means'][1]))
                        if case == 'zero':
                            assert before == after
                        if case == 'local':
                            assert any(deltas != 0)
                            assert all(before['means'][1][i] == after['means'][1][i] for i in range(engine.count) if deltas[i] == 0)
                        rejected = 0
                        if case == 'zero':
                            for bad in (np.full(engine.count, float('nan')), np.full(engine.count, 3.01), np.zeros(engine.count-1)):
                                try:
                                    engine.modify(bad)
                                except ValueError:
                                    rejected += 1
                            assert rejected == 3 and engine.snapshot() == before
                        audio, lf0 = engine.generate()
                        assert len(lf0) == sum(before['duration']) and len(audio) == len(lf0)*120
                        record = {'wave_sha256_float64': sha(audio), 'samples': len(audio), 'frames': len(lf0),
                            'snapshot_before': before, 'snapshot_after': after, 'deltas': deltas.tolist(),
                            'rejected_invalid_residuals': rejected, 'unchanged_duration_msd_other_streams': True}
                assert np.isfinite(audio).all() and np.max(abs(audio)) > 1e-5
                cases[case] = record
                np.save(out/f'{index}-{case}.npy', audio, allow_pickle=False)
                save(out/f'{index}-{case}.json', record)
        zero_match = cases['native']['wave_sha256_float64'] == cases['zero']['wave_sha256_float64']
        constant_match = cases['native_plus2']['wave_sha256_float64'] == cases['constant_plus2']['wave_sha256_float64']
        record = {'text': test['text'], 'zero_exact_match': zero_match, 'constant_exact_match': constant_match,
                  'local_changed_wave': cases['native']['wave_sha256_float64'] != cases['local']['wave_sha256_float64']}
        rows.append(record)
        print(record, flush=True)
        if not zero_match or not constant_match or not record['local_changed_wave']:
            save(out/'failure.json', {'row': record, 'action': '一致幅を変更せず入口検査で停止', 'training_and_asr_started': False})
            raise ValueError('入口の実波形一致に不通過')
    rejected = 0
    for speed, shift in [(float('nan'), 0.), (0., 0.), (1., 13.)]:
        try:
            StateEngine(analyze(tests[0]['text']), BUNDLE/'mei_normal.htsvoice', speed, shift)
        except ValueError:
            rejected += 1
    assert rejected == 3
    save(RESULT/'entry-audit.json', {'passed': True, 'rows': rows, 'actual_render_calls': 10,
        'invalid_request_rejections': rejected, 'invalid_residual_rejections': 6,
        'quality_certified': False, 'scope': '既存HMMとの入口一致。内容・自然さの認定ではない'})


if __name__ == '__main__':
    main()
