"""既知入力でゼロ残差と共通オフセットの波形厳密一致を検査する。"""
import hashlib
import sys
import numpy as np
from campaign import LocalBudget, ROOT, RESULT, BUNDLE, save, digest
sys.path.insert(0, str(BUNDLE))
from japanese_frontend import analyze
from hts_core import render_hts
sys.path.insert(0, str(ROOT))
from local_renderer import StateEngine
from local_control import deltas
from centered_projection import tests

def sha(audio):
    return hashlib.sha256(audio.astype('<f8').tobytes()).hexdigest()

def main():
    b = LocalBudget()
    out = RESULT/'entry-audit'; out.mkdir(exist_ok=False)
    fixtures = [{'text': '赤い傘。', 'speed': 1.}, {'text': '新しい地図を机に広げた。', 'speed': .85}]
    save(out/'contract.json', {'tests': fixtures, 'planned_render_calls': 8,
        'exact_wave_match_required': True, 'offset': 4., 'source_hashes': {n: digest(ROOT/n) for n in ('entry_audit.py','local_control.py','centered_projection.py')}})
    results = []
    for index, test in enumerate(fixtures):
        row = analyze(test['text']); cases = {}
        for case in ('native','zero','shape','shape_plus4'):
            with b.job('render', f'射影入口/{index}/{case}', 2_000_000):
                if case == 'native':
                    audio = render_hts(row, BUNDLE/'mei_normal.htsvoice', test['speed'], 0.)
                    record = {'wave_sha256_float64': sha(audio)}
                else:
                    with StateEngine(row, BUNDLE/'mei_normal.htsvoice', test['speed']) as engine:
                        before = engine.snapshot()
                        if case == 'zero':
                            correction = np.zeros(engine.count); phones = []
                        else:
                            offset = 4. if case == 'shape_plus4' else 0.
                            correction, phones = deltas(row, before, lambda x: np.arange(len(x), dtype=float)+offset)
                        engine.modify(correction); after = engine.snapshot()
                        assert before['duration'] == after['duration'] and before['msd'] == after['msd']
                        assert before['means'][0] == after['means'][0] and before['means'][2] == after['means'][2]
                        assert all(a[1:] == z[1:] for a,z in zip(before['means'][1],after['means'][1]))
                        assert all(before['means'][1][j] == after['means'][1][j] for j in range(engine.count) if correction[j] == 0)
                        rejected = 0
                        if case == 'zero':
                            assert before == after
                            for bad in (np.full(engine.count,np.nan),np.full(engine.count,3.01),np.zeros(engine.count-1)):
                                try: engine.modify(bad)
                                except ValueError: rejected += 1
                            assert rejected == 3 and engine.snapshot() == before
                        audio, lf0 = engine.generate()
                    record = {'wave_sha256_float64': sha(audio), 'snapshot_before': before, 'snapshot_after': after,
                        'deltas': correction.tolist(), 'phones': phones, 'rejected': rejected}
                assert np.isfinite(audio).all() and np.max(abs(audio)) > 1e-5
                np.save(out/f'{index}-{case}.npy', audio, allow_pickle=False)
                save(out/f'{index}-{case}.json', record); cases[case] = record
        result = {'text': test['text'], 'zero_exact_match': cases['native']['wave_sha256_float64'] == cases['zero']['wave_sha256_float64'],
            'offset_exact_match': cases['shape']['wave_sha256_float64'] == cases['shape_plus4']['wave_sha256_float64'],
            'shape_changed_wave': cases['shape']['wave_sha256_float64'] != cases['native']['wave_sha256_float64'],
            'offset_exact_state_residuals': cases['shape']['deltas'] == cases['shape_plus4']['deltas']}
        results.append(result); print(result, flush=True)
        assert all(v for k,v in result.items() if k != 'text')
    save(RESULT/'entry-audit.json', {'passed': True, 'rows': results, 'actual_render_calls': 8,
        'invalid_residual_rejections': 6, 'projection_tests': tests(), 'quality_certified': False})

if __name__ == '__main__':
    main()
